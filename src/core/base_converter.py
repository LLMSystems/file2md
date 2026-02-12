from abc import ABC, abstractmethod
import logging
from pathlib import Path
from typing import Any, Iterable, Sequence, Set, Optional, Dict

from .types import ProcessResult, ProcessOptions

class BaseConverter(ABC):
    name: str   # ex: "pdf", "docx"
    suffixes: Set[str]  # ex: {".pdf"}, {".docx", ".doc"}

    def __init__(self) -> None:
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
        input_paths: Sequence[Path],
        *,
        output_root: Path,
        options: Optional[ProcessOptions] = None
    ) -> Dict[Path, ProcessResult]:
        
        raise NotImplementedError

    def supports(self, path: Path) -> bool:
        return path.suffix.lower() in self.suffixes
    
    def result_map_to_plain_dict(
        self,
        res_map: Dict[str, ProcessResult]
    ) -> Dict[str, Dict[str, Any]]:
        out: Dict[str, Any] = {}
        for src, res in res_map.items():
            out[str(src)] = res.to_dict()
        return out

