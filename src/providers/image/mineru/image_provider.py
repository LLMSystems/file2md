from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
from zipfile import ZipFile


from src.core.types import (Artifact, ArtifactType, ProcessOptions,
                            ProcessResult)
from src.providers.pdf.mineru.pdf_provider import PDFMinerUProvider


class ImageProcessError(Exception):
    """Raised when the PDF processing pipeline fails."""


@dataclass
class MinerUProcessResult:
    extract_dir: Optional[Path]
    md_content: Optional[str]
    md_path: Optional[Path]
    middle_json: Optional[Dict[str, Any]]
    middle_json_path: Optional[Path]
    layout_pdf: Optional[Path] = None
    span_pdf: Optional[Path] = None


class ImageMinerUProvider(PDFMinerUProvider):
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
        
        # parse image
        parse_image = options.extra.get("parse_image", False)

        old_map = self.convert_images(
            image_paths=pdfs,
            backend=backend,
            return_images=return_images,
            return_middle_json=return_middle_json,
            return_model_output=return_model_output,
            return_content_list=return_content_list,
            response_format_zip=response_format_zip,
            parse_method=parse_method,
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

    def convert_images(
        self,
        image_paths: List[str | Path],
        *,
        backend: Optional[str] = None,
        return_images: Optional[bool] = None,
        return_middle_json: Optional[bool] = None,
        return_model_output: Optional[bool] = None,
        return_content_list: Optional[bool] = None,
        response_format_zip: Optional[bool] = None,
        parse_method: Optional[str] = None,
        keep_unzipped: bool = True,
        parse_image: bool = False,
    ) -> Dict[str, MinerUProcessResult]:
        """
        一次上傳多份圖片並處理結果。
        回傳 dict：key 為圖片檔名（不含副檔名），value 為該檔的 MinerUProcessResult。
        """
        # 正規化路徑
        image_paths_p: List[Path] = [Path(p) for p in image_paths]
        for p in image_paths_p:
            if not p.exists():
                raise ImageProcessError(f"Image not found: {p}")

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
            names = ", ".join([p.name for p in image_paths_p])
            self.logger.info(f"Uploading {len(image_paths_p)} images → {self.api_url} :: {names}")

        resp = self._post_files(self.api_url, image_paths_p, form)
        zip_bytes = self._expect_zip_response(resp, strict_content_type=self.strict_zip_content_type)

        with ZipFile(zip_bytes, "r") as zf:
            self._safe_extractall(zf, extract_dir)
        if self.verbose:
            self.logger.info(f"Extracted batch → {extract_dir}")

        results: Dict[str, MinerUProcessResult] = {}
        for p in image_paths_p:
            name = p.stem
            doc_dir = extract_dir / name
            md_path = doc_dir / f"{name}.md"
            middle_json_path = doc_dir / f"{name}_middle.json"

            md_content = self._read_text_if_exists(md_path)
            middle_json = self._read_json_if_exists(middle_json_path)

            results[name] = MinerUProcessResult(
                extract_dir=extract_dir if keep_unzipped else None,
                md_content=md_content,
                md_path=md_path if md_path.exists() else None,
                middle_json=middle_json,
                middle_json_path=middle_json_path if middle_json_path.exists() else None,
            )

        if not keep_unzipped:
            self._safe_remove_dir(extract_dir)

        return results