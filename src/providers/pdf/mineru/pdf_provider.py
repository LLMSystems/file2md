import json
import mimetypes
import asyncio
import re
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union
from zipfile import ZipFile

import requests
from requests.adapters import HTTPAdapter, Retry

from src.core.types import (Artifact, ArtifactType, ProcessOptions,
                            ProcessResult)
from src.providers.base import BaseProvider
from src.providers.pdf.mineru.utils.draw_bbox import (draw_layout_bbox,
                                                      draw_span_bbox)
from src.core.client.llm_client import AsyncLLMChat

class PDFProcessError(Exception):
    """Raised when the PDF processing pipeline fails."""


@dataclass
class MinerUProcessResult:
    extract_dir: Optional[Path]
    md_content: Optional[str]
    md_path: Optional[Path]
    middle_json: Optional[Dict[str, Any]]
    middle_json_path: Optional[Path]
    layout_pdf: Optional[Path]
    span_pdf: Optional[Path]


class PDFMinerUProvider(BaseProvider):
    """
    用法：
        client = PDFMinerUProvider(base_url="http://10.204.245.170:8962/", output_root="./test_outputs")
        pdfs = ["./pdfs/demo2.pdf", "./pdfs/demo3.pdf"]
        result = client.convert_files(pdfs, draw_layout_bbox=True, draw_span_bbox_=True)

    或者：
        with PDFMinerUProvider(base_url="http://localhost:8000") as client:
            r1 = client.convert_files(["/path/a.pdf", "/path/b.pdf"], draw_layout_bbox=True, draw_span_bbox_=True)
            r2 = client.convert_files(["/path/b.pdf"], draw_layout_bbox=False, draw_span_bbox_=True)
    """
    name = "mineru"

    _FALLBACK_MIME: Dict[str, str] = {
            ".pdf":  "application/pdf",
            ".doc":  "application/msword",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".ppt":  "application/vnd.ms-powerpoint",
            ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            ".xls":  "application/vnd.ms-excel",
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".html": "text/html",
            ".htm":  "text/html",
            ".md":   "text/markdown",
            ".txt":  "text/plain",
            ".png":  "image/png",
            ".jpg":  "image/jpeg",
            ".jpeg": "image/jpeg",
            ".tif":  "image/tiff",
            ".tiff": "image/tiff",
            ".gif":  "image/gif",
            ".bmp":  "image/bmp",
            ".svg":  "image/svg+xml",
        }
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
        default_llm_model: Optional[str] = None,
        default_llm_config_path: Optional[str] = None,
        default_llm_params: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__()

        self.base_url = base_url.rstrip("/")
        self.api_url = f"{self.base_url}{api_path}"
        self.output_root = Path(output_root)

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

        # llm 相關預設（目前沒用到，先放這）
        self.default_llm_model = default_llm_model
        self.default_llm_config_path = default_llm_config_path
        self.default_llm_params = default_llm_params or {}
        self.llm_client: Optional[AsyncLLMChat] = None

        if self.default_llm_model and self.default_llm_config_path and self.default_llm_params:
            self.llm_client = AsyncLLMChat(
                model=self.default_llm_model,
                config_path=self.default_llm_config_path
            )
            if self.verbose:
                self.logger.info(f"Initialized LLM client with model: {self.default_llm_model}")
        else:
            if self.verbose:
                self.logger.info("No default LLM model specified for MinerUProvider.")
        self._session = self._build_session(retries, backoff_factor, status_forcelist)

    # ---------- context manager -----------
    def __enter__(self) -> "PDFMinerUProvider":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        try:
            self._session.close()
        except Exception:
            pass

    # ---------- public API -----------
    def convert_files(
        self,
        file_paths: Sequence[Path],
        *,
        output_root: Path = None,
        options: Optional[ProcessOptions] = None,
    ) -> Dict[str, ProcessResult]:
        options = options or ProcessOptions()
        pdfs = [Path(p) for p in file_paths]
        if not pdfs:
            return {}

        self.output_root = output_root or self.output_root

        if isinstance(self.output_root, str):
            self.output_root = Path(self.output_root)
            self.output_root.mkdir(parents=True, exist_ok=True)

        backend             = options.extra.get("backend", self.default_backend)
        parse_method        = options.extra.get("parse_method", self.default_parse_method)
        keep_unzipped       = bool(options.extra.get("keep_unzipped", True))
        return_images       = options.extra.get("return_images",        self.default_return_images)
        return_middle_json  = options.extra.get("return_middle_json",   self.default_return_middle_json)
        return_model_output = options.extra.get("return_model_output",  self.default_return_model_output)
        return_content_list = options.extra.get("return_content_list",  self.default_return_content_list)
        response_format_zip = options.extra.get("response_format_zip",  self.default_response_format_zip)
        draw_layout_bbox    = options.extra.get("draw_layout_bbox",     True)
        draw_span_bbox      = options.extra.get("draw_span_bbox",       True)

        # parse image
        parse_image = options.extra.get("parse_image", False)

        old_map = self.convert_pdfs(
            pdf_paths=pdfs,
            backend=backend,
            return_images=return_images,
            return_middle_json=return_middle_json,
            return_model_output=return_model_output,
            return_content_list=return_content_list,
            response_format_zip=response_format_zip,
            parse_method=parse_method,
            draw_layout_bbox=draw_layout_bbox,
            draw_span_bbox_=draw_span_bbox,
            keep_unzipped=keep_unzipped,
            parse_image=parse_image,
        )

        out: Dict[str, ProcessResult] = {}
        for src in pdfs:
            stem = src.stem
            r = old_map.get(stem)
            if not r:
                out[str(src)] = ProcessResult(
                    source=src,
                    extract_dir=output_root / stem,
                    meta={"error": "missing result from MinerU"}
                )
                continue

            artifacts: List[Artifact] = []
            if r.middle_json_path:
                artifacts.append(Artifact(
                    name="middle_json",
                    type=ArtifactType.JSON,
                    path=r.middle_json_path,
                    mime="application/json"
                ))
            if r.layout_pdf:
                artifacts.append(Artifact(
                    name="layout_pdf",
                    type=ArtifactType.ANNOTATED_PDF,
                    path=r.layout_pdf,
                    mime="application/pdf"
                ))
            if r.span_pdf:
                artifacts.append(Artifact(
                    name="span_pdf",
                    type=ArtifactType.ANNOTATED_PDF,
                    path=r.span_pdf,
                    mime="application/pdf"
                ))

            assets_dir = None
            if r.md_path:
                assets_dir = r.md_path.parent / "images"
            else:
                assets_dir = (output_root / stem / "images")

            if assets_dir.exists():
                for img in sorted(assets_dir.glob("*")):
                    if img.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}:
                        artifacts.append(Artifact(
                            name=img.name,
                            type=ArtifactType.IMAGE,
                            path=img
                        ))

            out[str(src)] = ProcessResult(
                source=src,
                md_text=r.md_content,
                md_path=r.md_path,
                ir=r.middle_json,
                ir_path=r.middle_json_path,
                artifacts=artifacts,
                extract_dir=r.extract_dir or (output_root / stem),
                meta={
                    "provider": self.name,
                    "backend": backend,
                    "parse_method": parse_method,
                },
            )

        return out

    def convert_pdfs(
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
        parse_image: bool = False,
    ) -> Dict[str, MinerUProcessResult]:
        """
        一次上傳多份 PDF 並處理結果。
        回傳 dict：key 為 pdf 檔名（不含副檔名），value 為該檔的 MinerUProcessResult。
        """
        # 正規化路徑
        pdf_paths_p: List[Path] = [Path(p) for p in pdf_paths]
        for p in pdf_paths_p:
            if not p.exists():
                raise PDFProcessError(f"PDF not found: {p}")

        extract_dir = (self.output_root).resolve()
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
            names = ", ".join([p.name for p in pdf_paths_p])
            self.logger.info(f"Uploading {len(pdf_paths_p)} PDFs → {self.api_url} :: {names}")

        resp = self._post_files(self.api_url, pdf_paths_p, form)
        zip_bytes = self._expect_zip_response(resp, strict_content_type=self.strict_zip_content_type)

        with ZipFile(zip_bytes, "r") as zf:
            self._safe_extractall(zf, extract_dir)
        if self.verbose:
            self.logger.info(f"Extracted batch → {extract_dir}")
        
        results: Dict[str, MinerUProcessResult] = {}
        for p in pdf_paths_p:
            name = p.stem
            doc_dir = extract_dir / name
            md_path = doc_dir / f"{name}.md"
            middle_json_path = doc_dir / f"{name}_middle.json"

            md_content = self._read_text_if_exists(md_path)
            middle_json = self._read_json_if_exists(middle_json_path)

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

            results[name] = MinerUProcessResult(
                extract_dir=extract_dir if keep_unzipped else None,
                md_content=md_content,
                md_path=md_path if md_path.exists() else None,
                middle_json=middle_json,
                middle_json_path=middle_json_path if middle_json_path.exists() else None,
                layout_pdf=layout_pdf_path,
                span_pdf=span_pdf_path,
            )

        results = self.parse_images(results, parse_image)

        if not keep_unzipped:
            self._safe_remove_dir(extract_dir)

        return results
    
    def parse_images(self, results: Dict[str, MinerUProcessResult], parse_image: bool) -> Dict[str, MinerUProcessResult]:
        if not parse_image:
            return results
        # Implement the image parsing logic here
        if not self.llm_client:
            if self.verbose:
                self.logger.warning("LLM client not initialized; skipping image parsing.")
            return results
        # step 1: collect all images from the results
        image_tasks = []
        for name, res in results.items():
            content_list_path = res.extract_dir / name /f"{name}_content_list.json"
            # read content list if exists
            content_list = self._read_json_if_exists(content_list_path)
            if not content_list:
                if self.verbose:
                    self.logger.warning(f"No content list found for {name}; skipping image parsing.")
                continue
            for item in content_list:
                if item.get("type") == "image" and "img_path" in item:
                    image_path = res.extract_dir / name / item["img_path"]
                    image_caption = item.get("image_caption", "") # list
                    image_caption_str = "\n".join(image_caption) if isinstance(image_caption, list) else str(image_caption)
                    if image_path.exists():
                        image_tasks.append((name, image_caption_str, image_path))
        if len(image_tasks) == 0:
            if self.verbose:
                self.logger.info("No images found for parsing.")
            return results
        
        # step 2: parse each image with LLM
        self.logger.info(f"Parsing {len(image_tasks)} images with LLM...")
        parsed_results = self.parse_image_tasks(image_tasks)

        # step 3: integrate parsed results back into the original results
        for name, img_path, parsed in parsed_results:
            if parsed is None:
                continue
            value = results.get(name)
            md_content = value.md_content if value else None
            if not md_content:
                if self.verbose:
                    self.logger.warning(f"No markdown content found for {name}; cannot integrate parsed image results.")
                continue
            """
            replace the original image reference in md_content with the parsed result (this is just a placeholder logic, you can customize it based on how you want to integrate the parsed results)
            ex : 
                ![](images/b8e32d9cc62e2ffa0977d6cf98ff9d67d4cb5b151ff14961f0b15261e1e3066e.jpg)  
            -->
                ![](images/b8e32d9cc62e2ffa0977d6cf98ff9d67d4cb5b151ff14961f0b15261e1e3066e.jpg)  
                **Parsed Above Image Content**: parsed_content
            """
            new_md_content = md_content.replace(f"![](images/{img_path.name})", f"![](images/{img_path.name})\n\n**Parsed Above Image Content**:\n\n{parsed}\n\n")
            results[name].md_content = new_md_content
            # update md_path content as well
            if value.md_path and value.md_path.exists():
                value.md_path.write_text(new_md_content, encoding="utf-8")

        return results
    
    def parse_image_tasks(self, image_tasks: List[Tuple[str, str, Path]], batch_size: int = 5) -> None:
        prompt = """
你是一個專業的圖片數據解析助手。
我將提供一張圖片與圖片標題，請你從圖片中擷取可辨識的數據與文字資訊。

【請務必遵守以下規則】
1. 僅根據圖片中「實際可見且清晰」的內容回答。
2. 不可臆測、不推測、不補完任何圖片中沒有明確顯示的資訊。
3. 若內容不清楚或無法辨識，請標記為「不確定」，不要給出猜測。
4. 若圖片中沒有有效數據、沒有清楚文字、或沒有可用資訊，請直接回覆：「無」。
5. 如果能讀取到數據，請盡可能精確擷取並結構化整理(請用表格呈現)。
6. 如果是圖表，請分析趨勢但不要過度解讀。

【輸出格式】
- 【圖片整體描述】
- 【可擷取的所有數據列表，請用表格呈現】（若無則寫「無」）
- 【表格或圖表數據&趨勢分析】（若圖片非圖表則略過）
- 【不確定或模糊區域】（若無則寫「無」）

以下是圖片標題：
圖片標題：{image_caption}

請開始解析圖片中的數據。
    """
        async def run():
            results = []
            tasks = []

            for i, (name, caption, img_path) in enumerate(image_tasks):
                # 創建異步任務
                task = asyncio.create_task(self.llm_client.vision_chat(
                    query=prompt.format(image_caption=caption),
                    image_path=img_path,
                    params=self.default_llm_params,
                ))
                tasks.append((name, img_path, task))

                # 當達到批次大小時，執行並收集結果
                if len(tasks) >= batch_size:
                    if self.verbose:
                        self.logger.info(f"Processing batch of {len(tasks)} images...")
                    results.extend(await self._process_tasks(tasks))
                    tasks = []

            # 處理剩餘的任務
            if tasks:
                results.extend(await self._process_tasks(tasks))

            return results

        # 啟動事件迴圈執行
        return asyncio.run(run())

    async def _process_tasks(self, tasks: List[Tuple[str, Path, asyncio.Task]]) -> List[Tuple[str, Path, Any]]:
        results = []
        for name, img_path, task in tasks:
            try:
                # 等待任務完成並收集結果
                result, _ = await task
                results.append((name, img_path, result))
            except Exception as e:
                # 單獨處理每個任務的異常，避免影響其他任務
                if self.verbose:
                    self.logger.warning(f"Failed to process image {img_path}: {e}")
                results.append((name, img_path, None))
        return results
    
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
    
    def _post_files(
        self,
        url: str,
        file_paths: Union[Path, Iterable[Path]],
        form_data: Dict[str, Any],
    ) -> requests.Response:
        """
        上傳一或多份 PDF 檔案到後端。

        Parameters
        ----------
        file_paths : Path or Iterable[Path]
            可傳單一 Path 或多個 Path。
        """
        # 正規化成 list[Path]
        if isinstance(file_paths, Path):
            file_list: List[Path] = [file_paths]
        else:
            file_list = list(file_paths)

        # 檢查存在性
        for p in file_list:
            if not p.exists():
                raise PDFProcessError(f"PDF not found: {p}")

        # 重要：同一個 key "files" 可以重複多次以傳多檔
        files = []
        # 我們需要保持檔案物件存活直到 post 完成，因此先開啟所有 fp
        fps = [p.open("rb") for p in file_list]      
        try:
            for p, fp in zip(file_list, fps):
                mime = self._detect_mime(p)
                files.append(("files", (p.name, fp, mime)))
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

    def _detect_mime(self, path: Path) -> str:
            # 先用 mimetypes 猜，猜不到再用 fallback
            mime, _ = mimetypes.guess_type(path.name)
            if not mime:
                mime = self._FALLBACK_MIME.get(path.suffix.lower(), "application/octet-stream")
            return mime