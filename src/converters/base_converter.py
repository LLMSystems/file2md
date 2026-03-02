import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set

from src.core.types import ProcessOptions, ProcessResult
from src.providers.base import BaseProvider


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

    def _select_providers(self, preferred: Optional[str]) -> List[BaseProvider]:
        if preferred:
            ordered = [p for p in self.providers if p.name == preferred] + \
                      [p for p in self.providers if p.name != preferred]
        else:
            ordered = list(self.providers)
        return ordered