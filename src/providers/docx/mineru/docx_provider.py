import json
import mimetypes
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union
from zipfile import ZipFile

import requests
from requests.adapters import HTTPAdapter, Retry

from src.core.types import (Artifact, ArtifactType, ProcessOptions,
                            ProcessResult)
from src.providers.pdf.mineru.pdf_provider import PDFMinerUProvider
from src.providers.pdf.mineru.utils.draw_bbox import (draw_layout_bbox,
                                                      draw_span_bbox)
from src.providers.utils import \
    libreoffice_files_to_pdf  # 用於 ppt/docx 轉 pdf 的工具函式


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


class DocxMinerUProvider(PDFMinerUProvider):
    """
    用法：
        client = DocxMinerUProvider(base_url="http://10.204.245.170:8962/", output_root="./test_outputs")
        docx_files = ["./docs/demo2.docx", "./docs/demo3.docx"]
        result = client.convert_files(docx_files, draw_layout_bbox=True, draw_span_bbox_=True)

    或者：
        with DocxMinerUProvider(base_url="http://localhost:8000") as client:
            r1 = client.convert_files(["/path/a.docx", "/path/b.docx"], draw_layout_bbox=True, draw_span_bbox_=True)
            r2 = client.convert_files(["/path/b.docx"], draw_layout_bbox=False, draw_span_bbox_=True)
    """
    
    def __init__(
        self,
        *args,
        _soffice_path: str = "soffice",
        _extra_soffice_args: Optional[List[str]] = None,
        tmp_dir: Optional[Path] = Path("./tmp"),
        **kwargs,
    ):
        # 把所有父類需要的參數原封不動轉給 super
        super().__init__(*args, **kwargs)

        # 自己類別需要的屬性
        self.soffice_path = _soffice_path
        self.extra_soffice_args = _extra_soffice_args or []
        self.tmp_dir = Path(tmp_dir) if tmp_dir is not None else None
        if self.tmp_dir:
            self.tmp_dir.mkdir(parents=True, exist_ok=True)

    # ---------- public API -----------
    def convert_files(
        self,
        file_paths: Sequence[Path],
        *,
        output_root: Path = None,
        options: Optional[ProcessOptions] = None,
    ) -> Dict[str, ProcessResult]:
        options = options or ProcessOptions()

        # 1. 先把 docx 轉成 pdf
        self.logger.info(f"Converting {len(file_paths)} files to PDF using LibreOffice...")
        pdf_paths: List[Path] = []
        for p in file_paths:
            if isinstance(p, str):
                p = Path(p)
            if p.suffix.lower() in {".docx", ".doc"}:
                pdf_path = self.tmp_dir / (p.stem + ".pdf")
                libreoffice_files_to_pdf(
                    input_file=str(p),
                    out_dir=str(self.tmp_dir),
                    soffice_path=self.soffice_path,
                    extra_args=self.extra_soffice_args,
                    logger=self.logger if self.verbose else None,
                )
                pdf_paths.append(pdf_path)
            elif p.suffix.lower() == ".pdf":
                pdf_paths.append(p)
            else:
                self.logger.warning(f"Unsupported file type, skipping: {p}")

        pdfs = [Path(p) for p in pdf_paths]
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
        )

        # delete temp pdf files
        for p in pdf_paths:
            try:
                p.unlink()
            except Exception as e:
                self.logger.warning(f"Failed to delete temp PDF {p}: {e}")

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