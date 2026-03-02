from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import requests

from src.app.config import (File2MDConfig, build_process_extra,
                            get_llm_config_path, get_llm_default_model,
                            get_llm_default_params, get_mineru_base_url,
                            get_mineru_retry, get_mineru_timeout,
                            load_config_from_env, load_config_from_yaml,
                            resolve_output_root, resolve_prefer_provider)
from src.app.http import build_llm_chat, build_session
from src.core.client.llm_client import AsyncLLMChat
from src.core.types import ProcessOptions, ProcessResult


class UnsupportedFormatError(Exception):
    pass


class ProviderNotConfiguredError(Exception):
    pass


class ProviderNotSupportedError(Exception):
    pass


# ---------------------------
# Format detection
# ---------------------------

_EXT_TO_FMT: Dict[str, str] = {
    ".txt": "txt",
    ".md": "txt",
    ".log": "txt",

    ".docx": "docx",
    ".doc": "docx",

    ".xlsx": "excel",
    ".csv": "excel",

    ".html": "html",
    ".htm": "html",

    ".pdf": "pdf",

    ".pptx": "pptx",

    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".webp": "image",
    ".bmp": "image",
    ".tiff": "image",
}


def detect_format(path: str | Path) -> str:
    p = Path(path)
    ext = p.suffix.lower()
    if ext in _EXT_TO_FMT:
        return _EXT_TO_FMT[ext]

    mt, _ = mimetypes.guess_type(str(p))
    if mt:
        if mt.startswith("text/"):
            return "txt"
        if mt in ("application/pdf",):
            return "pdf"
        if mt in ("text/html",):
            return "html"
        if mt.startswith("image/"):
            return "image"

    raise UnsupportedFormatError(f"Unsupported file type: {p.name} (ext={ext}, mime={mt})")


# ---------------------------
# Provider factory
# ---------------------------

def _build_provider(fmt: str, provider_name: str, cfg: File2MDConfig, mineru_session: Optional[requests.Session] = None, llm_client: Optional[AsyncLLMChat] = None):
    """
    Instantiate provider instance based on (format, provider_name).
    No fallback here.
    """
    provider_name = provider_name.lower().strip()
    fmt = fmt.lower().strip()

    if fmt == "txt":
        if provider_name != "txt":
            raise ProviderNotSupportedError(f"fmt=txt does not support provider={provider_name}")
        from src.providers.txt.txt_provider import TxtProvider
        return TxtProvider()

    if fmt == "excel":
        if provider_name != "excel":
            raise ProviderNotSupportedError(f"fmt=excel does not support provider={provider_name}")
        from src.providers.excel.excel_provider import ExcelProvider
        return ExcelProvider()

    if fmt == "html":
        if provider_name != "beautifulsoup":
            raise ProviderNotSupportedError(f"fmt=html does not support provider={provider_name}")
        from src.providers.html.html_provider import HTMLBeautifulSoupProvider
        return HTMLBeautifulSoupProvider()

    if fmt == "docx":
        if provider_name == "mammoth":
            from src.providers.docx.mammoth.docx_provider import \
                DOCXMammothProvider
            return DOCXMammothProvider(
                default_llm_model=get_llm_default_model(cfg),
                default_llm_params=get_llm_default_params(cfg),
                default_llm_config_path=get_llm_config_path(cfg),
                llm_client=llm_client,
            )
        if provider_name == "mineru":
            from src.providers.docx.mineru.docx_provider import \
                DocxMinerUProvider
            return DocxMinerUProvider(
                base_url=get_mineru_base_url(cfg),
                timeout=get_mineru_timeout(cfg),
                retries=get_mineru_retry(cfg),
                default_llm_model=get_llm_default_model(cfg),
                default_llm_params=get_llm_default_params(cfg),
                default_llm_config_path=get_llm_config_path(cfg),
                llm_client=llm_client,
                session=mineru_session,
            )
        raise ProviderNotSupportedError(f"fmt=docx does not support provider={provider_name}")

    if fmt == "pdf":
        if provider_name != "mineru":
            raise ProviderNotSupportedError(f"fmt=pdf does not support provider={provider_name}")
        from src.providers.pdf.mineru.pdf_provider import PDFMinerUProvider
        return PDFMinerUProvider(
            base_url=get_mineru_base_url(cfg),
            timeout=get_mineru_timeout(cfg),
            retries=get_mineru_retry(cfg),
            default_llm_model=get_llm_default_model(cfg),
            default_llm_params=get_llm_default_params(cfg),
            default_llm_config_path=get_llm_config_path(cfg),
            llm_client=llm_client,
            session=mineru_session,
        )

    if fmt == "pptx":
        if provider_name != "mineru":
            raise ProviderNotSupportedError(f"fmt=pptx does not support provider={provider_name}")
        from src.providers.pptx.mineru.pptx_provider import PPTXMinerUProvider
        return PPTXMinerUProvider(
            base_url=get_mineru_base_url(cfg),
            timeout=get_mineru_timeout(cfg),
            retries=get_mineru_retry(cfg),
            default_llm_model=get_llm_default_model(cfg),
            default_llm_params=get_llm_default_params(cfg),
            default_llm_config_path=get_llm_config_path(cfg),
            llm_client=llm_client,
            session=mineru_session,
        )

    if fmt == "image":
        if provider_name != "mineru":
            raise ProviderNotSupportedError(f"fmt=image does not support provider={provider_name}")
        from src.providers.image.mineru.image_provider import \
            ImageMinerUProvider
        return ImageMinerUProvider(
            base_url=get_mineru_base_url(cfg),
            timeout=get_mineru_timeout(cfg),
            retries=get_mineru_retry(cfg),
            default_llm_model=get_llm_default_model(cfg),
            default_llm_params=get_llm_default_params(cfg),
            default_llm_config_path=get_llm_config_path(cfg),
            llm_client=llm_client,
            session=mineru_session,
        )

    raise ProviderNotSupportedError(f"Unknown format: {fmt}")


# ---------------------------
# Converter factory
# ---------------------------

def _build_converter(fmt: str, provider_name: str, provider_instance):
    """
    Instantiate converter and set prefer to provider_name (mammoth/mineru/...).
    This matches your converter design: one converter can coordinate multiple providers.
    """
    fmt = fmt.lower().strip()
    provider_name = provider_name.lower().strip()

    if fmt == "txt":
        from src.converters import TXTConverter
        return TXTConverter(providers=[provider_instance], prefer=provider_name)

    if fmt == "excel":
        from src.converters import ExcelConverter
        return ExcelConverter(providers=[provider_instance], prefer=provider_name)

    if fmt == "docx":
        from src.converters import DOCXConverter
        return DOCXConverter(providers=[provider_instance], prefer=provider_name)

    if fmt == "html":
        from src.converters.html.html_converter import HTMLConverter
        return HTMLConverter(providers=[provider_instance], prefer=provider_name)

    if fmt == "pdf":
        from src.converters.pdf.pdf_converter import PDFConverter
        return PDFConverter(providers=[provider_instance], prefer=provider_name)

    if fmt == "pptx":
        from src.converters import PPTXConverter
        return PPTXConverter(providers=[provider_instance], prefer=provider_name)

    if fmt == "image":
        from src.converters import ImageConverter
        return ImageConverter(providers=[provider_instance], prefer=provider_name)

    raise UnsupportedFormatError(f"Unsupported format: {fmt}")


def _normalize_process_options(options: Optional[ProcessOptions], extra: Dict[str, Any]) -> ProcessOptions:
    """
    Ensure ProcessOptions.extra includes merged 'extra'.
    Assumes ProcessOptions has an 'extra' attribute (per your examples).
    """
    if options is None:
        return ProcessOptions(extra=extra)

    existing_extra = getattr(options, "extra", None)
    if isinstance(existing_extra, dict):
        merged = dict(existing_extra)
        merged.update(extra)
        setattr(options, "extra", merged)
        return options

    setattr(options, "extra", extra)
    return options


# ---------------------------
# Public API
# ---------------------------

@dataclass
class ConvertItemResult:
    input_path: str
    fmt: str
    provider: str
    result: ProcessResult


class File2MD:
    """
    Unified entrypoint (no fallback):
      - detect format
      - resolve prefer provider from YAML
      - build ProcessOptions.extra
      - instantiate provider + converter
      - run convert_files
    """

    def __init__(
        self, 
        cfg: File2MDConfig,
        *,
        mineru_session: Optional[requests.Session] = None,
        owns_mineru_session: Optional[bool] = None,
        llm_client: Optional[AsyncLLMChat] = None,
        owns_llm_client: Optional[bool] = None,
    ):
        self.cfg = cfg
        if mineru_session is None:
            mineru_session = build_session(
                retries=get_mineru_retry(cfg),
            )
            self._owns_mineru_session = True if owns_mineru_session is None else owns_mineru_session
        else:
            self._owns_mineru_session = False if owns_mineru_session is None else owns_mineru_session
        self._mineru_session = mineru_session
        
        if llm_client is None and get_llm_default_model(cfg) and get_llm_config_path(cfg):
            llm_client = build_llm_chat(
                model=get_llm_default_model(cfg),
                config_path=get_llm_config_path(cfg),
            )
            self._owns_llm_client = True if owns_llm_client is None else owns_llm_client
        else:
            self._owns_llm_client = False if owns_llm_client is None else owns_llm_client
        self._llm_client = llm_client
        
    def close(self) -> None:
        """Call this on API shutdown if File2MD owns the session."""
        if getattr(self, "_owns_mineru_session", False):
            try:
                self._mineru_session.close()
            except Exception:
                pass
                        
    @classmethod
    def from_env(
        cls, 
        default_path: Optional[str] = None,
        *,
        mineru_session: Optional[requests.Session] = None,
    ) -> "File2MD":
        cfg = load_config_from_env(default_path=default_path)
        return cls(cfg, mineru_session=mineru_session)

    @classmethod
    def from_yaml(
        cls, 
        path: str,
        *,
        mineru_session: Optional[requests.Session] = None,
    ) -> "File2MD":
        cfg = load_config_from_yaml(path)
        return cls(cfg, mineru_session=mineru_session)

    def convert(
        self,
        input_paths: Sequence[str],
        output_root: Optional[str] = None,
        options: Optional[ProcessOptions] = None,
        runtime_extra: Optional[Dict[str, Any]] = None,
    ) -> List[ConvertItemResult]:
        out_root = resolve_output_root(self.cfg, output_root)

        # Group by (fmt, provider) so same converter/provider can batch-run together
        groups: Dict[Tuple[str, str], List[str]] = {}
        for p in input_paths:
            fmt = detect_format(p)
            provider = resolve_prefer_provider(self.cfg, fmt)
            if not provider:
                raise ProviderNotConfiguredError(
                    f"No prefer provider configured for fmt={fmt}. "
                    f"Set file2md.prefer.{fmt} in YAML."
                )
            groups.setdefault((fmt, provider), []).append(p)

        results: List[ConvertItemResult] = []

        for (fmt, provider), paths in groups.items():
            prov = _build_provider(fmt, provider, self.cfg, mineru_session=self._mineru_session, llm_client=self._llm_client)
            conv = _build_converter(fmt, provider, prov)

            extra = build_process_extra(
                self.cfg,
                fmt=fmt,
                provider=provider,
                runtime_extra=runtime_extra,
            )
            opts = _normalize_process_options(options, extra)

            batch_result = conv.convert_files(
                input_paths=paths,
                output_root=out_root,
                options=opts,
            )

            # Defensive mapping: list / dict / single result
            if isinstance(batch_result, list):
                if len(batch_result) == len(paths):
                    for p, r in zip(paths, batch_result):
                        results.append(ConvertItemResult(p, fmt, provider, r))
                else:
                    for p in paths:
                        results.append(ConvertItemResult(p, fmt, provider, batch_result))  # type: ignore[arg-type]
            elif isinstance(batch_result, dict):
                for p in paths:
                    r = batch_result.get(p) or batch_result.get(str(Path(p)))
                    if r is None:
                        r = batch_result  # type: ignore[assignment]
                    results.append(ConvertItemResult(p, fmt, provider, r))  # type: ignore[arg-type]
            else:
                for p in paths:
                    results.append(ConvertItemResult(p, fmt, provider, batch_result))  # type: ignore[arg-type]

        return results