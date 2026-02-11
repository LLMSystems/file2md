import json
import logging
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, Iterable, List, Union

import requests
from requests.adapters import HTTPAdapter, Retry
from zipfile import ZipFile

from .utils.draw_bbox import draw_layout_bbox, draw_span_bbox

class PDFProcessError(Exception):
    """Raised when the PDF processing pipeline fails."""


@dataclass
class ProcessResult:
    extract_dir: Optional[Path]
    md_content: Optional[str]
    md_path: Optional[Path]
    middle_json: Optional[Dict[str, Any]]
    middle_json_path: Optional[Path]
    layout_pdf: Optional[Path]
    span_pdf: Optional[Path]


class PDFMinerUClient:
    """
    可重用 session 的 MinerU PDF 上傳與解析客戶端。

    用法：
        client = PDFMinerUClient(base_url="http://localhost:8000", output_root="/tmp/mineru_out")
        result = client.process_pdf("/path/a.pdf")
        result2 = client.process_pdf("/path/b.pdf")
        client.close()

    或者：
        with PDFMinerUClient(base_url="http://localhost:8000") as client:
            r1 = client.process_pdf("/path/a.pdf")
            r2 = client.process_pdf("/path/b.pdf")
    """

    def __init__(
        self,
        base_url: str,
        *,
        output_root: str = "/test",
        api_path: str = "/file_parse",
        timeout: Tuple[float, float] = (10, 180),
        retries: int = 3,
        backoff_factor: float = 0.5,
        status_forcelist: Tuple[int, ...] = (429, 500, 502, 503, 504),
        strict_zip_content_type: bool = False,
        verbose: bool = True,
        default_backend: str = "pipeline",
        default_return_images: bool = True,
        default_return_middle_json: bool = True,
        default_return_model_output: bool = True,
        default_return_content_list: bool = True,
        default_response_format_zip: bool = True,
        default_parse_method: str = "auto",
    ) -> None:
        self.logger = self._setup_logger()
        self.base_url = base_url.rstrip("/")
        self.api_url = f"{self.base_url}{api_path}"
        self.output_root = Path(output_root)
        self.output_root.mkdir(parents=True, exist_ok=True)

        self.timeout = timeout
        self.strict_zip_content_type = strict_zip_content_type
        self.verbose = verbose

        self.default_backend = default_backend
        self.default_return_images = default_return_images
        self.default_return_middle_json = default_return_middle_json
        self.default_return_model_output = default_return_model_output
        self.default_return_content_list = default_return_content_list
        self.default_response_format_zip = default_response_format_zip
        self.default_parse_method = default_parse_method

        self._session = self._build_session(retries, backoff_factor, status_forcelist)

    # ---------- context manager -----------
    def __enter__(self) -> "PDFMinerUClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        try:
            self._session.close()
        except Exception:
            pass

    def _setup_logger(self) -> logging.Logger:
        logger = logging.getLogger(self.__class__.__name__)
        if not logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            ))
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        return logger

    # ---------- public API -----------
    def process_pdf(
        self,
        pdf_path: str | Path,
        *,
        backend: Optional[str] = None,
        return_images: Optional[bool] = None,
        return_middle_json: Optional[bool] = None,
        return_model_output: Optional[bool] = None,
        return_content_list: Optional[bool] = None,
        response_format_zip: Optional[bool] = None,
        parse_method: Optional[str] = None,
        draw_layout_bbox: bool = True,
        draw_span_bbox_: bool = True,
        keep_unzipped: bool = True,
    ) -> ProcessResult:
        """
        上傳並解析單一 PDF，回傳 Markdown 與（可選）bbox PDF。

        Parameters
        ----------
        pdf_path : str | Path
            本機 PDF 路徑。
        backend, return_images, return_middle_json, return_model_output, return_content_list,
        response_format_zip, parse_method : Optional
            若不指定則使用 __init__ 設定的 default 值。
        draw_layout_bbox : bool
            是否輸出 layout bbox PDF。
        draw_span_bbox_ : bool
            是否輸出 span bbox PDF。
        keep_unzipped : bool
            是否保留解壓資料夾。
        """
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise PDFProcessError(f"PDF not found: {pdf_path}")

        pdf_name = pdf_path.stem
        extract_dir = (self.output_root / f"{pdf_name}_unzipped").resolve()
        extract_dir.mkdir(parents=True, exist_ok=True)

        form = self._build_form_data(
            backend=backend,
            return_images=return_images,
            return_middle_json=return_middle_json,
            return_model_output=return_model_output,
            return_content_list=return_content_list,
            response_format_zip=response_format_zip,
            parse_method=parse_method,
        )

        if self.verbose:
            self.logger.info(f"Uploading '{pdf_path.name}' → {self.api_url}")

        # 1) 呼叫 API
        resp = self._post_pdf(self.api_url, pdf_path, form)
        zip_bytes = self._expect_zip_response(resp, strict_content_type=self.strict_zip_content_type)

        # 2) 解壓
        with ZipFile(zip_bytes, "r") as zf:
            self._safe_extractall(zf, extract_dir)
        if self.verbose:
            self.logger.info(f"Extracted → {extract_dir}")

        # 3) 讀 md 與 middle.json
        doc_dir = extract_dir / pdf_name
        md_path = doc_dir / f"{pdf_name}.md"
        middle_json_path = doc_dir / f"{pdf_name}_middle.json"

        md_content = self._read_text_if_exists(md_path)
        middle_json = self._read_json_if_exists(middle_json_path)

        if self.verbose:
            self.logger.info(f"MD: {'OK' if md_content else 'Missing'}  |  middle.json: {'OK' if middle_json else 'Missing'}")

        # 4) bbox（可選）
        layout_pdf_path: Optional[Path] = None
        span_pdf_path: Optional[Path] = None

        if middle_json and (draw_layout_bbox or draw_span_bbox_):
            pdf_bytes = pdf_path.read_bytes()
            res = self._draw_bboxes(
                middle_json=middle_json,
                source_pdf_bytes=pdf_bytes,
                out_dir=doc_dir,
                pdf_basename=pdf_name,
                draw_layout=draw_layout_bbox,
                draw_span=draw_span_bbox_,
            )
            layout_pdf_path = res["layout_pdf"]
            span_pdf_path = res["span_pdf"]

        # 5) 清理（可選）
        if not keep_unzipped:
            self._safe_remove_dir(extract_dir)

        return ProcessResult(
            extract_dir=extract_dir if keep_unzipped else None,
            md_content=md_content,
            md_path=md_path if md_path.exists() else None,
            middle_json=middle_json,
            middle_json_path=middle_json_path if middle_json_path.exists() else None,
            layout_pdf=layout_pdf_path,
            span_pdf=span_pdf_path,
        )
    
    def process_pdfs(
        self,
        pdf_paths: List[str | Path],
        *,
        backend: Optional[str] = None,
        return_images: Optional[bool] = None,
        return_middle_json: Optional[bool] = None,
        return_model_output: Optional[bool] = None,
        return_content_list: Optional[bool] = None,
        response_format_zip: Optional[bool] = None,
        parse_method: Optional[str] = None,
        draw_layout_bbox: bool = True,
        draw_span_bbox_: bool = True,
        keep_unzipped: bool = True,
    ) -> Dict[str, ProcessResult]:
        """
        一次上傳多份 PDF 並處理結果。
        回傳 dict：key 為 pdf 檔名（不含副檔名），value 為該檔的 ProcessResult。
        """
        # 正規化路徑
        pdf_paths_p: List[Path] = [Path(p) for p in pdf_paths]
        for p in pdf_paths_p:
            if not p.exists():
                raise PDFProcessError(f"PDF not found: {p}")

        # 將輸出資料夾以「批次」為單位，避免不同批次相互覆蓋
        extract_dir = (self.output_root).resolve()
        extract_dir.mkdir(parents=True, exist_ok=True)

        # 表單參數
        form = self._build_form_data(
            backend=backend,
            return_images=return_images,
            return_middle_json=return_middle_json,
            return_model_output=return_model_output,
            return_content_list=return_content_list,
            response_format_zip=response_format_zip,
            parse_method=parse_method,
        )

        if self.verbose:
            names = ", ".join([p.name for p in pdf_paths_p])
            print(f"[MinerU] Uploading {len(pdf_paths_p)} PDFs → {self.api_url} :: {names}")

        # 1) 一次上傳多檔
        resp = self._post_pdf(self.api_url, pdf_paths_p, form)
        zip_bytes = self._expect_zip_response(resp, strict_content_type=self.strict_zip_content_type)

        # 2) 解壓
        with ZipFile(zip_bytes, "r") as zf:
            self._safe_extractall(zf, extract_dir)
        if self.verbose:
            print(f"[MinerU] Extracted batch → {extract_dir}")

        # 3) 逐檔掃描結果
        results: Dict[str, ProcessResult] = {}
        for p in pdf_paths_p:
            name = p.stem
            doc_dir = extract_dir / name
            md_path = doc_dir / f"{name}.md"
            middle_json_path = doc_dir / f"{name}_middle.json"

            # read md & json
            md_content = self._read_text_if_exists(md_path)
            middle_json = self._read_json_if_exists(middle_json_path)

            # bbox（可選）
            layout_pdf_path: Optional[Path] = None
            span_pdf_path: Optional[Path] = None
            if middle_json and (draw_layout_bbox or draw_span_bbox_):
                pdf_bytes = p.read_bytes()
                res = self._draw_bboxes(
                    middle_json=middle_json,
                    source_pdf_bytes=pdf_bytes,
                    out_dir=doc_dir,
                    pdf_basename=name,
                    draw_layout=draw_layout_bbox,
                    draw_span=draw_span_bbox_,
                )
                layout_pdf_path = res["layout_pdf"]
                span_pdf_path = res["span_pdf"]

            results[name] = ProcessResult(
                extract_dir=extract_dir if keep_unzipped else None,
                md_content=md_content,
                md_path=md_path if md_path.exists() else None,
                middle_json=middle_json,
                middle_json_path=middle_json_path if middle_json_path.exists() else None,
                layout_pdf=layout_pdf_path,
                span_pdf=span_pdf_path,
            )

        # 4) 清理（可選）
        if not keep_unzipped:
            self._safe_remove_dir(extract_dir)

        return results

    # ---------- internals -----------
    @staticmethod
    def _build_session(
        retries: int,
        backoff_factor: float,
        status_forcelist: Tuple[int, ...],
    ) -> requests.Session:
        session = requests.Session()
        retry = Retry(
            total=retries,
            read=retries,
            connect=retries,
            backoff_factor=backoff_factor,
            status_forcelist=status_forcelist,
            allowed_methods=frozenset(["POST", "GET"]),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def _build_form_data(
        self,
        *,
        backend: Optional[str],
        return_images: Optional[bool],
        return_middle_json: Optional[bool],
        return_model_output: Optional[bool],
        return_content_list: Optional[bool],
        response_format_zip: Optional[bool],
        parse_method: Optional[str],
    ) -> Dict[str, Any]:
        """
        將布林轉成 'true'/'false'（許多後端以字串判讀）。
        """
        def b(v: Optional[bool], default: bool) -> str:
            return str((default if v is None else v)).lower()

        return {
            "output_dir": str(self.output_root),
            "backend": backend or self.default_backend,
            "return_images": b(return_images, self.default_return_images),
            "return_middle_json": b(return_middle_json, self.default_return_middle_json),
            "return_model_output": b(return_model_output, self.default_return_model_output),
            "return_content_list": b(return_content_list, self.default_return_content_list),
            "response_format_zip": b(response_format_zip, self.default_response_format_zip),
            "parse_method": (parse_method or self.default_parse_method),
        }
    
    def _post_pdf(
        self,
        url: str,
        pdf_paths: Union[Path, Iterable[Path]],
        form_data: Dict[str, Any],
    ) -> requests.Response:
        """
        上傳一或多份 PDF 檔案到後端。

        Parameters
        ----------
        pdf_paths : Path or Iterable[Path]
            可傳單一 Path 或多個 Path。
        """
        # 正規化成 list[Path]
        if isinstance(pdf_paths, Path):
            pdf_list: List[Path] = [pdf_paths]
        else:
            pdf_list = list(pdf_paths)

        # 檢查存在性
        for p in pdf_list:
            if not p.exists():
                raise PDFProcessError(f"PDF not found: {p}")

        # 重要：同一個 key "files" 可以重複多次以傳多檔
        files = []
        # 我們需要保持檔案物件存活直到 post 完成，因此先開啟所有 fp
        fps = [p.open("rb") for p in pdf_list]
        try:
            for p, fp in zip(pdf_list, fps):
                files.append(("files", (p.name, fp, "application/pdf")))
            resp = self._session.post(url, files=files, data=form_data, timeout=self.timeout)
        finally:
            for fp in fps:
                try:
                    fp.close()
                except Exception:
                    pass

        return resp


    def _expect_zip_response(self, resp: requests.Response, *, strict_content_type: bool) -> BytesIO:
        if resp.status_code != 200:
            try:
                detail = resp.json()
            except Exception:
                detail = (resp.text or "")[:2000]
            raise PDFProcessError(f"Server returned {resp.status_code}: {detail}")

        ctype = (resp.headers.get("Content-Type") or "").lower()
        if strict_content_type and "zip" not in ctype:
            raise PDFProcessError(f"Unexpected Content-Type: {ctype} (expect zip)")

        return BytesIO(resp.content)

    @staticmethod
    def _safe_extractall(zf: ZipFile, target_dir: Path) -> None:
        target_dir = target_dir.resolve()
        for member in zf.infolist():
            dest = (target_dir / member.filename).resolve()
            if not str(dest).startswith(str(target_dir)):
                raise PDFProcessError(f"Unsafe zip entry detected: {member.filename}")
        zf.extractall(target_dir)

    @staticmethod
    def _read_text_if_exists(path: Path, encoding: str = "utf-8") -> Optional[str]:
        return path.read_text(encoding=encoding) if path.exists() else None

    @staticmethod
    def _read_json_if_exists(path: Path, encoding: str = "utf-8") -> Optional[Dict[str, Any]]:
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding=encoding))
        except json.JSONDecodeError as e:
            raise PDFProcessError(f"JSON decode error at {path}: {e}") from e

    def _draw_bboxes(
        self,
        *,
        middle_json: Dict[str, Any],
        source_pdf_bytes: bytes,
        out_dir: Path,
        pdf_basename: str,
        draw_layout: bool,
        draw_span: bool,
    ) -> Dict[str, Optional[Path]]:
        results: Dict[str, Optional[Path]] = {"layout_pdf": None, "span_pdf": None}
        pdf_info = middle_json.get("pdf_info", {})
        if not pdf_info:
            if self.verbose:
                self.logger.warning("Warn: 'pdf_info' missing; skip bbox drawing")
            return results

        if draw_layout:
            name = f"{pdf_basename}_layout.pdf"
            draw_layout_bbox(pdf_info, source_pdf_bytes, out_dir, name)
            results["layout_pdf"] = out_dir / name
            if self.verbose:
                self.logger.info(f"Layout bbox → {results['layout_pdf']}")

        if draw_span:
            name = f"{pdf_basename}_span.pdf"
            draw_span_bbox(pdf_info, source_pdf_bytes, out_dir, name)
            results["span_pdf"] = out_dir / name
            if self.verbose:
                self.logger.info(f"Span bbox → {results['span_pdf']}")

        return results

    def _safe_remove_dir(self, root: Path) -> None:
        """
        安全移除解壓資料夾，不影響主流程。
        """
        try:
            for p in sorted(root.glob("**/*"), reverse=True):
                if p.is_file():
                    p.unlink(missing_ok=True)
                elif p.is_dir():
                    p.rmdir()
            root.rmdir()
            if self.verbose:
                self.logger.info(f"Removed temp folder: {root}")
        except Exception as e:
            if self.verbose:
                self.logger.warning(f"Warn: cleanup failed for {root}: {e}")

if __name__ == "__main__":
    client = PDFMinerUClient(base_url="http://10.204.245.170:8962/", output_root="./test_outputs")
    pdfs = ["./pdfs/demo2.pdf", "./pdfs/demo3.pdf"]
    result = client.process_pdfs(pdfs, draw_layout_bbox=True, draw_span_bbox_=True)
