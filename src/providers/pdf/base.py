# src/your_package/providers/pdf/base.py
from __future__ import annotations
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Sequence, Optional
from src.core.types import ProcessOptions, ProcessResult

class IPdfProvider(ABC):
    """
    PDF 解析的提供者介面：任何 PDF 引擎（MinerU、LocalOCR、其他雲端）
    只要實作這個介面，就能被 PdfConverter 使用。
    """

    name: str  # 例如 "mineru" / "local_ocr" / "cloud_x"
    @abstractmethod
    def convert_pdfs(
        self,
        pdf_paths: Sequence[Path],
        *,
        output_root: Path,
        options: Optional[ProcessOptions] = None,
    ) -> Dict[str, ProcessResult]:
        raise NotImplementedError
