from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Optional, Sequence

from src.core.types import ProcessOptions, ProcessResult


class BaseProvider(ABC):
    name: str  # 例如 "mineru" / "local_ocr" / "cloud_x"

    def __init__(self):
        self.logger = self._setup_logger()

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
    
    @abstractmethod
    def convert_files(
        self,
        file_paths: Sequence[Path],
        *,
        output_root: Path,
        options: Optional[ProcessOptions] = None,
    ) -> Dict[str, ProcessResult]:
        raise NotImplementedError

    
