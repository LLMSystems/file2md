import json
import mimetypes
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union
from zipfile import ZipFile

import requests
from markitdown import MarkItDown
from requests.adapters import HTTPAdapter, Retry

from src.core.types import (ProcessOptions,
                            ProcessResult)
from src.providers.base import BaseProvider


class ExcelProcessError(Exception):
    """Raised when the Excel processing pipeline fails."""


@dataclass
class ExcelProcessResult:
    extract_dir: Optional[Path]
    md_content: Optional[str]
    md_path: Optional[Path]


class ExcelProvider(BaseProvider):
    """
    用法：
        client = ExcelProvider(output_root="./test_outputs")
        excel_files = ["./excel/demo2.xlsx", "./excel/demo3.xlsx"]
        result = client.convert_files(excel_files)

    或者：
        with ExcelProvider(output_root="./test_outputs") as client:
            r1 = client.convert_files(["/path/a.xlsx", "/path/b.xlsx"])
            r2 = client.convert_files(["/path/b.xlsx"])
    """
    name = "excel"
    
    def __init__(
        self,
        output_root: str = "/test"
    ) -> None:
        super().__init__()

        self.output_root = Path(output_root)
        self.md_converter = MarkItDown()

    # ---------- context manager -----------
    def __enter__(self) -> "ExcelProvider":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        try:
            pass
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
        excels = [Path(p) for p in file_paths]
        if not excels:
            return {}

        self.output_root = output_root or self.output_root

        if isinstance(self.output_root, str):
            self.output_root = Path(self.output_root)
            self.output_root.mkdir(parents=True, exist_ok=True)

        old_map = self.convert_excels(
            excel_paths=excels
        )

        out: Dict[str, ProcessResult] = {}
        for src in excels:
            stem = src.stem
            r = old_map.get(stem)
            if not r:
                out[str(src)] = ProcessResult(
                    source=src,
                    extract_dir=output_root / stem,
                    meta={"error": "missing result"}
                )
                continue

            out[str(src)] = ProcessResult(
                source=src,
                md_text=r.md_content,
                md_path=r.md_path,
                extract_dir=r.extract_dir or (output_root / stem),
                meta={
                    "provider": self.name,
                    "backend": "markitdown"
                },
            )

        return out

    def convert_excels(
        self,
        excel_paths: List[str | Path]
    ) -> Dict[str, ExcelProcessResult]:
        """
        一次上傳多份 Excel 並處理結果。
        回傳 dict：key 為 Excel 檔名（不含副檔名），value 為該檔的 ExcelProcessResult。
        """
        # 正規化路徑
        excel_paths_p: List[Path] = [Path(p) for p in excel_paths]
        for p in excel_paths_p:
            if not p.exists():
                raise ExcelProcessError(f"Excel not found: {p}")

        extract_dir = (self.output_root).resolve()
        extract_dir.mkdir(parents=True, exist_ok=True)
        
        results: Dict[str, ExcelProcessResult] = {}
        for p in excel_paths_p:
            name = p.stem
            doc_dir = extract_dir / name
            md_content = self.md_converter.convert(p).markdown
            md_path = doc_dir / f"{name}.md"
            # save markdown to file
            doc_dir.mkdir(parents=True, exist_ok=True)
            md_path.write_text(md_content, encoding="utf-8")

            results[name] = ExcelProcessResult(
                extract_dir=extract_dir,
                md_content=md_content,
                md_path=md_path if md_path.exists() else None,
            )

        return results