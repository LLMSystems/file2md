from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from src.core.types import ProcessOptions, ProcessResult
from src.providers.base import BaseProvider


class TxtProcessError(Exception):
    """Raised when the TXT processing pipeline fails."""


@dataclass
class TxtProcessResult:
    extract_dir: Optional[Path]
    md_content: Optional[str]
    md_path: Optional[Path]


class TxtProvider(BaseProvider):
    """
    用法：
        client = TxtProvider(output_root="./test_outputs")
        txt_files = ["./txt/a.txt", "./txt/b.txt"]
        result = client.convert_files(txt_files)

    或者：
        with TxtProvider(output_root="./test_outputs") as client:
            r1 = client.convert_files(["/path/a.txt", "/path/b.txt"])
            r2 = client.convert_files(["/path/b.txt"])
    """
    name = "txt"

    def __init__(self, output_root: str = "/test") -> None:
        super().__init__()
        self.output_root = Path(output_root)

    # ---------- context manager -----------
    def __enter__(self) -> "TxtProvider":
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
        txts = [Path(p) for p in file_paths]
        if not txts:
            return {}

        self.output_root = output_root or self.output_root

        if isinstance(self.output_root, str):
            self.output_root = Path(self.output_root)

        self.output_root.mkdir(parents=True, exist_ok=True)

        old_map = self.convert_txts(txt_paths=txts, options=options)

        out: Dict[str, ProcessResult] = {}
        for src in txts:
            stem = src.stem
            r = old_map.get(stem)
            if not r:
                out[str(src)] = ProcessResult(
                    source=src,
                    extract_dir=self.output_root / stem,
                    meta={"error": "missing result"},
                )
                continue

            out[str(src)] = ProcessResult(
                source=src,
                md_text=r.md_content,
                md_path=r.md_path,
                extract_dir=r.extract_dir or (self.output_root / stem),
                meta={
                    "provider": self.name,
                    "backend": "txt",
                },
            )

        return out

    def convert_txts(
        self,
        txt_paths: List[str | Path],
        *,
        options: Optional[ProcessOptions] = None,
    ) -> Dict[str, TxtProcessResult]:
        """
        一次處理多份 TXT。
        回傳 dict：key 為檔名（不含副檔名），value 為 TxtProcessResult。
        """
        options = options or ProcessOptions()

        txt_paths_p: List[Path] = [Path(p) for p in txt_paths]
        for p in txt_paths_p:
            if not p.exists():
                raise TxtProcessError(f"TXT not found: {p}")
            if p.is_dir():
                raise TxtProcessError(f"TXT path is a directory: {p}")

        extract_dir = self.output_root.resolve()
        extract_dir.mkdir(parents=True, exist_ok=True)

        # ---- options (safe getattr) ----
        wrap_in_codeblock = bool(getattr(options, "wrap_in_codeblock", False))
        smart_format = bool(getattr(options, "smart_format", True))
        normalize_line_endings = bool(getattr(options, "normalize_line_endings", True))
        strip_trailing_spaces = bool(getattr(options, "strip_trailing_spaces", True))

        results: Dict[str, TxtProcessResult] = {}
        for p in txt_paths_p:
            name = p.stem
            doc_dir = extract_dir / name
            doc_dir.mkdir(parents=True, exist_ok=True)

            try:
                txt = p.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                # fallback：遇到非 utf-8 的 txt，先用 replace 保住流程
                txt = p.read_text(encoding="utf-8", errors="replace")

            md_content = self._txt_to_markdown(
                txt,
                wrap_in_codeblock=wrap_in_codeblock,
                smart_format=smart_format,
                normalize_line_endings=normalize_line_endings,
                strip_trailing_spaces=strip_trailing_spaces,
            )

            md_path = doc_dir / f"{name}.md"
            md_path.write_text(md_content, encoding="utf-8")

            results[name] = TxtProcessResult(
                extract_dir=extract_dir,
                md_content=md_content,
                md_path=md_path if md_path.exists() else None,
            )

        return results

    # ---------- core conversion -----------
    def _txt_to_markdown(
        self,
        txt: str,
        *,
        wrap_in_codeblock: bool,
        smart_format: bool,
        normalize_line_endings: bool,
        strip_trailing_spaces: bool,
    ) -> str:
        if normalize_line_endings:
            txt = txt.replace("\r\n", "\n").replace("\r", "\n")

        if strip_trailing_spaces:
            txt = "\n".join(line.rstrip() for line in txt.split("\n"))

        if wrap_in_codeblock:
            # 最穩：完全保留 txt 長相
            return f"```text\n{txt}\n```"

        if not smart_format:
            # 原樣輸出（但已做換行/trim）
            return txt

        # smart_format: 輕量轉換一些常見結構
        lines = txt.split("\n")
        out: List[str] = []
        i = 0
        while i < len(lines):
            line = lines[i]

            # 偵測 setext 標題：
            # Title
            # =====
            if i + 1 < len(lines):
                underline = lines[i + 1].strip()
                if underline and set(underline) <= {"="} and len(underline) >= 3:
                    out.append(f"# {line.strip()}")
                    i += 2
                    continue
                if underline and set(underline) <= {"-"} and len(underline) >= 3:
                    out.append(f"## {line.strip()}")
                    i += 2
                    continue

            # 偵測 "ALL CAPS:" 當作小標（保守一點）
            if line.strip().endswith(":") and line.strip()[:-1].isupper():
                out.append(f"### {line.strip()[:-1].title()}")
                i += 1
                continue

            # 其他就原樣放（保留列表、段落、空行）
            out.append(line)
            i += 1

        return "\n".join(out)