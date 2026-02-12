from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union
from enum import Enum, auto
from pathlib import Path


class ArtifactType(Enum):
    IMAGE = auto()
    JSON = auto()
    CSV = auto()
    ANNOTATED_PDF = auto()
    ZIP = auto()
    OTHER = auto()


@dataclass(slots=True)
class Artifact:
    """轉換過程中產生的檔案或資料，包含其類型、路徑和相關資訊。"""
    type: ArtifactType
    name: str
    path: Path
    mime: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type.name,          # Enum → 字串
            "name": self.name,
            "path": str(self.path),          # Path → 字串
            "mime": self.mime,
            "extra": self._serialize_extra(self.extra),
        }

    @staticmethod
    def _serialize_extra(extra: Dict[str, Any]) -> Dict[str, Any]:
        def ser(v):
            if isinstance(v, Path):
                return str(v)
            if isinstance(v, Enum):
                return v.name
            if isinstance(v, dict):
                return {k: ser(x) for k, x in v.items()}
            if isinstance(v, (list, tuple)):
                return [ser(x) for x in v]
            return v
        return {k: ser(v) for k, v in extra.items()}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Artifact":
        return cls(
            type=ArtifactType[data["type"]],
            name=data["name"],
            path=Path(data["path"]),
            mime=data.get("mime"),
            extra=data.get("extra") or {},
        )



@dataclass(slots=True)
class ProcessOptions:
    extra: Dict[str, Any] = field(default_factory=dict)



@dataclass(slots=True)
class ProcessResult:
    source: Path
    md_text: Optional[str] = None
    md_path: Optional[Path] = None
    ir: Optional[Dict[str, Any]] = None
    ir_path: Optional[Path] = None
    artifacts: List[Artifact] = field(default_factory=list)
    extract_dir: Optional[Path] = None
    warnings: List[str] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": str(self.source),
            "md_text": self.md_text,
            "md_path": str(self.md_path) if self.md_path else None,
            "ir": self._serialize_ir(self.ir),
            "ir_path": str(self.ir_path) if self.ir_path else None,
            "artifacts": [a.to_dict() for a in self.artifacts],
            "extract_dir": str(self.extract_dir) if self.extract_dir else None,
            "warnings": list(self.warnings),
            "meta": self._serialize_meta(self.meta),
        }

    @staticmethod
    def _serialize_ir(ir: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if ir is None:
            return None
        def ser(v):
            if isinstance(v, Path):
                return str(v)
            if isinstance(v, Enum):
                return v.name
            if isinstance(v, dict):
                return {k: ser(x) for k, x in v.items()}
            if isinstance(v, (list, tuple)):
                return [ser(x) for x in v]
            return v
        return {k: ser(v) for k, v in ir.items()}

    @staticmethod
    def _serialize_meta(meta: Dict[str, Any]) -> Dict[str, Any]:
        def ser(v):
            if isinstance(v, Path):
                return str(v)
            if isinstance(v, Enum):
                return v.name
            if isinstance(v, dict):
                return {k: ser(x) for k, x in v.items()}
            if isinstance(v, (list, tuple)):
                return [ser(x) for x in v]
            return v
        return {k: ser(v) for k, v in meta.items()}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProcessResult":
        return cls(
            source=Path(data["source"]),
            md_text=data.get("md_text"),
            md_path=Path(data["md_path"]) if data.get("md_path") else None,
            ir=data.get("ir"),
            ir_path=Path(data["ir_path"]) if data.get("ir_path") else None,
            artifacts=[Artifact.from_dict(a) for a in (data.get("artifacts") or [])],
            extract_dir=Path(data["extract_dir"]) if data.get("extract_dir") else None,
            warnings=list(data.get("warnings") or []),
            meta=data.get("meta") or {},
        )



