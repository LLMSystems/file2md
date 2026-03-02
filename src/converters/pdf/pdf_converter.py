from pathlib import Path
from typing import Dict, Optional, Sequence

from src.converters.base_converter import BaseConverter
from src.core.errors import ConverterError
from src.core.types import ProcessOptions, ProcessResult
from src.providers.base import BaseProvider


class PDFConverter(BaseConverter):
    name = "pdf"
    suffixes = {".pdf"}

    def __init__(
        self,
        providers: Sequence[BaseProvider],
        prefer: Optional[str] = "mineru",
    ):
        super().__init__()
        self.providers = providers
        assert providers, "至少需要一個 PDF 解析提供者"
        self.logger.info(f"Initialized PDFConverter with providers: {[p.name for p in providers]}")
        self._prefer = prefer # provider.name

    def convert_files(
            self,
            input_paths: Sequence[Path],
            *,
            output_root: Path,
            options: Optional[ProcessOptions] = None
        ) -> Dict[Path, ProcessResult]:
        options = options or ProcessOptions()
        if isinstance(input_paths, list):
            input_paths = [Path(p) for p in input_paths]

        pdfs = [p for p in input_paths if self.supports(p)]
        if not pdfs:
            self.logger.warning("No supported PDF files found in input.")
            return {}

        provider_name = (options.extra.get("provider") if options else None) or self._prefer
        candidates = self._select_providers(provider_name)
        self.logger.info(
                    "PDF converting %d files to %s using providers: %s",
                    len(pdfs), output_root, [p.name for p in candidates]
                )
        
        last_err: Optional[Exception] = None
        for provider in candidates:
            try:
                res = provider.convert_files(pdfs, output_root=output_root, options=options)
                missing = []
                for p in pdfs:
                    file_name = p.stem
                    if file_name not in [Path(k).stem for k in res.keys()]:
                        missing.append(str(p))
                if missing:
                    self.logger.warning(f"Provider {provider.name} did not return results for: {missing}")
                else:
                    self.logger.info(f"Provider {provider.name} successfully processed all PDFs.")

                return_dict = options.extra.get("return_dict", False)
                if return_dict:
                    res = self.result_map_to_plain_dict(res)
                return res
            except Exception as e:
                self.logger.error(f"Provider {provider.name} failed with error: {e}")
                last_err = e
                continue
        raise ConverterError(f"All PDF providers failed. Last error: {last_err}")
