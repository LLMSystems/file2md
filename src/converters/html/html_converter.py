from pathlib import Path
from typing import Dict, List, Optional, Sequence

from src.converters.base_converter import BaseConverter
from src.core.errors import ConverterError
from src.core.types import ProcessOptions, ProcessResult
from src.providers.html.html_provider import HTMLBeautifulSoupProvider


class HTMLConverter(BaseConverter):
    """
    HTML 轉換器協調器，管理多個 HTML 解析提供者。
    
    用法：
        converter = HTMLConverter(
            providers=[HTMLBeautifulSoupProvider()],
            prefer="beautifulsoup"
        )
        results = converter.convert_files(
            input_paths=[Path("sample.html"), Path("test.html")],
            output_root=Path("/output"),
            options=ProcessOptions()
        )
    """
    name = "html"
    suffixes = {".html"}

    def __init__(
        self,
        providers: Sequence[HTMLBeautifulSoupProvider],
        prefer: Optional[str] = "beautifulsoup",
    ):
        """
        初始化 HTML 轉換器。

        Parameters
        ----------
        providers : Sequence[IHtmlProvider]
            HTML 解析提供者列表（例如 BeautifulSoupProvider）。
        prefer : Optional[str]
            優先使用的 provider 名稱（例如 "beautifulsoup"）。
        """
        super().__init__()
        self._providers = providers
        assert providers, "至少需要一個 HTML 解析提供者"
        self.logger.info(f"Initialized HTMLConverter with providers: {[p.name for p in providers]}")
        self._prefer = prefer

    def convert_files(
        self,
        input_paths: Sequence[Path],
        *,
        output_root: Path,
        options: Optional[ProcessOptions] = None
    ) -> Dict[Path, ProcessResult]:
        """
        轉換多個 HTML 文檔為 Markdown。

        Parameters
        ----------
        input_paths : Sequence[Path]
            輸入 HTML 檔案路徑列表。
        output_root : Path
            輸出根目錄。
        options : Optional[ProcessOptions]
            處理選項，可包含：
            - html_provider: 指定使用的 provider
            - extract_images: 是否提取圖片
            - keep_output: 是否保留輸出目錄
            - download_remote_images: 是否下載遠端圖片
            - convert_image_format: 圖片輸出格式
            - return_dict: 是否返回字典格式（預設 True）

        Returns
        -------
        Dict[Path, ProcessResult]
            以檔案路徑為 key 的處理結果字典。
        """
        options = options or ProcessOptions()
        
        # 統一轉換為 Path 物件
        if isinstance(input_paths, list):
            input_paths = [Path(p) for p in input_paths]

        # 過濾出支援的 HTML 檔案
        html_files = [p for p in input_paths if self.supports(p)]
        if not html_files:
            self.logger.warning("No supported HTML files found in input.")
            return {}

        # 選擇 provider
        provider_name = (options.extra.get("provider") if options else None) or self._prefer
        candidates = self._select_providers(provider_name)
        
        self.logger.info(
            "HTML converting %d files to %s using providers: %s",
            len(html_files), output_root, [p.name for p in candidates]
        )

        # 嘗試用每個 provider 轉換（容錯機制）
        last_err: Optional[Exception] = None
        for provider in candidates:
            try:
                # 呼叫 provider 的 convert_files 方法
                res = provider.convert_files(
                    html_paths=html_files,
                    output_root=output_root,
                    options=options
                )
                
                # 檢查是否所有檔案都有結果
                missing = []
                for p in html_files:
                    file_name = p.stem
                    if file_name not in [Path(k).stem for k in res.keys()]:
                        missing.append(str(p))
                        
                if missing:
                    self.logger.warning(
                        f"Provider {provider.name} did not return results for: {missing}"
                    )
                else:
                    self.logger.info(
                        f"Provider {provider.name} successfully processed all HTML files."
                    )

                # 轉換結果格式（str key → Path key）
                return_dict = options.extra.get("return_dict", False)
                if return_dict:
                    # 將 str key 轉換為 Path key
                    res = {Path(k): v for k, v in res.items()}
                    res = self.result_map_to_plain_dict(res)
                
                return res
                
            except Exception as e:
                self.logger.error(f"Provider {provider.name} failed with error: {e}")
                last_err = e
                continue

        # 所有 provider 都失敗
        raise ConverterError(f"All HTML providers failed. Last error: {last_err}")