"""
HTML Provider - 使用 BeautifulSoup 將 HTML 轉換為 Markdown
"""
import json
import logging
import base64
import hashlib
import uuid
import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Any
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup

from src.core.types import ProcessOptions, ProcessResult, Artifact, ArtifactType
from src.core.errors import ConverterError


class HTMLProviderError(Exception):
    """HTML Provider 專用錯誤"""


class HTMLBeautifulSoupProvider:
    """
    使用 BeautifulSoup 將 HTML 轉換為 Markdown 的 Provider。
    
    Features:
    - 支援表格、列表、圖片等常見 HTML 元素
    - 支援 base64 圖片提取
    - 支援遠端圖片下載
    - 支援本地圖片複製
    - 提取 HTML meta 資訊
    
    用法:
        provider = HTMLBeautifulSoupProvider(
            output_root="/tmp/html_output",
            default_extract_images=True,
            default_download_remote_images=False
        )
        results = provider.convert_html(
            html_paths=["sample.html", "test.html"],
            output_root=Path("/output"),
            options=ProcessOptions()
        )
    """
    
    name = "beautifulsoup"
    
    def __init__(
        self,
        output_root: str = "/tmp/html_output",
        *,
        verbose: bool = True,
        default_extract_images: bool = True,
        default_keep_output: bool = True,
        default_convert_image_format: str = "png",
        default_download_remote_images: bool = False,
    ):
        """
        初始化 HTML Provider。

        Parameters
        ----------
        output_root : str
            輸出根目錄。
        verbose : bool
            是否顯示詳細日誌。
        default_extract_images : bool
            預設是否提取圖片。
        default_keep_output : bool
            預設是否保留輸出目錄。
        default_convert_image_format : str
            預設圖片輸出格式（png/jpg）。
        default_download_remote_images : bool
            預設是否下載遠端圖片。
        """
        self.logger = self._setup_logger()
        self.output_root = Path(output_root)
        self.verbose = verbose
        
        # 預設值
        self.default_extract_images = default_extract_images
        self.default_keep_output = default_keep_output
        self.default_convert_image_format = default_convert_image_format
        self.default_download_remote_images = default_download_remote_images
        
        if self.verbose:
            self.logger.info(
                f"HTMLBeautifulSoupProvider initialized "
                f"(extract_images={default_extract_images}, "
                f"download_remote={default_download_remote_images})"
            )

    def _setup_logger(self) -> logging.Logger:
        """設定日誌記錄器"""
        logger = logging.getLogger(self.__class__.__name__)
        if not logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            ))
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        return logger

    def convert_html(
        self,
        html_paths: Sequence[Path],
        *,
        output_root: Path,
        options: Optional[ProcessOptions] = None,
    ) -> Dict[str, ProcessResult]:
        """
        轉換多個 HTML 文檔為 Markdown。

        Parameters
        ----------
        html_paths : Sequence[Path]
            HTML 文檔路徑列表。
        output_root : Path
            輸出根目錄。
        options : Optional[ProcessOptions]
            處理選項，可包含：
            - extract_images: 是否提取圖片
            - keep_output: 是否保留輸出目錄
            - download_remote_images: 是否下載遠端圖片
            - convert_image_format: 圖片輸出格式
            - image_alt_text: 圖片替代文字

        Returns
        -------
        Dict[str, ProcessResult]
            以檔案路徑為 key 的處理結果字典。
        """
        options = options or ProcessOptions()
        htmls = [Path(p) for p in html_paths]
        if not htmls:
            return {}

        if isinstance(output_root, str):
            output_root = Path(output_root)
        self.output_root = output_root
        self.output_root.mkdir(parents=True, exist_ok=True)

        # 從 options 中提取參數
        extract_images = options.extra.get("extract_images", self.default_extract_images)
        keep_output = options.extra.get("keep_output", self.default_keep_output)
        convert_image_format = options.extra.get("convert_image_format", self.default_convert_image_format)
        download_remote_images = options.extra.get("download_remote_images", self.default_download_remote_images)

        # 處理文檔
        results: Dict[str, ProcessResult] = {}
        
        for html_path in htmls:
            if not html_path.exists():
                self.logger.error(f"HTML file not found: {html_path}")
                results[str(html_path)] = ProcessResult(
                    source=html_path,
                    extract_dir=output_root / html_path.stem,
                    meta={"error": f"File not found: {html_path}"}
                )
                continue

            try:
                result = self._process_single_html(
                    html_path=html_path,
                    output_root=output_root,
                    extract_images=extract_images,
                    keep_output=keep_output,
                    convert_image_format=convert_image_format,
                    download_remote_images=download_remote_images,
                )
                results[str(html_path)] = result
                
            except Exception as e:
                self.logger.error(f"Failed to process {html_path.name}: {e}")
                results[str(html_path)] = ProcessResult(
                    source=html_path,
                    extract_dir=output_root / html_path.stem,
                    meta={"error": str(e)}
                )

        return results

    def _process_single_html(
        self,
        html_path: Path,
        output_root: Path,
        extract_images: bool,
        keep_output: bool,
        convert_image_format: str,
        download_remote_images: bool,
    ) -> ProcessResult:
        """
        處理單一 HTML 文件。

        Returns
        -------
        ProcessResult
            處理結果。
        """
        html_name = html_path.stem
        extract_dir = output_root / html_name
        extract_dir.mkdir(parents=True, exist_ok=True)

        if self.verbose:
            self.logger.info(f"Processing '{html_path.name}' → {extract_dir}")

        # 1. 讀取並解析 HTML
        html_content = html_path.read_text(encoding="utf-8")
        soup = BeautifulSoup(html_content, 'html.parser')

        # 2. 提取圖片
        images_dir = extract_dir / "images"
        images_dir.mkdir(exist_ok=True)
        extracted_images: List[Path] = []

        if extract_images:
            extracted_images = self._extract_images(
                soup=soup,
                images_dir=images_dir,
                html_path=html_path,
                download_remote=download_remote_images,
                image_format=convert_image_format,
            )

        # 3. 轉換為 Markdown
        body = soup.find('body')
        html_to_convert = str(body) if body else str(soup)
        md_content = self._html_to_markdown(html_to_convert)

        # 4. 保存 Markdown
        md_path = extract_dir / f"{html_name}.md"
        md_path.write_text(md_content, encoding="utf-8")

        if self.verbose:
            self.logger.info(f"MD saved: {md_path}")
            if extracted_images:
                self.logger.info(f"Images extracted: {len(extracted_images)} files")

        # 5. 提取元數據
        metadata = self._extract_metadata(html_path, soup)

        # 6. 構建 artifacts
        artifacts: List[Artifact] = []

        # 添加元數據
        if metadata:
            metadata_path = extract_dir / f"{html_name}_metadata.json"
            metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))
            artifacts.append(Artifact(
                name="metadata",
                type=ArtifactType.JSON,
                path=metadata_path,
                mime="application/json"
            ))

        # 添加圖片
        if extracted_images:
            for img in extracted_images:
                artifacts.append(Artifact(
                    name=img.name,
                    type=ArtifactType.IMAGE,
                    path=img
                ))

        # 7. 清理輸出目錄（如果需要）
        if not keep_output:
            self._safe_remove_dir(extract_dir)
            extract_dir = None

        return ProcessResult(
            source=html_path,
            md_text=md_content,
            md_path=md_path,
            ir=metadata,
            artifacts=artifacts,
            extract_dir=extract_dir,
            meta={
                "provider": self.name,
                "extract_images": extract_images,
                "image_count": len(extracted_images) if extracted_images else 0,
                "download_remote_images": download_remote_images,
            },
        )

    # ==================== 圖片處理 ====================

    def _extract_images(
        self,
        soup: BeautifulSoup,
        images_dir: Path,
        html_path: Path,
        download_remote: bool,
        image_format: str,
    ) -> List[Path]:
        """
        提取並保存圖片。

        Returns
        -------
        List[Path]
            已保存的圖片路徑列表。
        """
        extracted_images: List[Path] = []
        img_tags = soup.find_all('img')

        for img in img_tags:
            src = img.get('src')
            if not src:
                continue

            try:
                image_path = None

                # Base64 圖片
                if src.startswith('data:image'):
                    image_path = self._save_base64_image(src, images_dir, image_format)

                # 遠端圖片
                elif src.startswith(('http://', 'https://')):
                    if download_remote:
                        image_path = self._download_image(src, images_dir, image_format)
                    else:
                        if self.verbose:
                            self.logger.debug(f"Skipping remote image: {src}")
                        continue

                # 本地圖片
                else:
                    image_path = self._copy_local_image(src, images_dir, html_path, image_format)

                # 更新 img 標籤
                if image_path:
                    extracted_images.append(image_path)
                    img['src'] = f"images/{image_path.name}"
                    if self.verbose:
                        self.logger.debug(f"Processed image: {src} -> images/{image_path.name}")

            except Exception as e:
                self.logger.warning(f"Failed to process image {src}: {e}")

        return extracted_images

    def _save_base64_image(
        self,
        data_uri: str,
        images_dir: Path,
        image_format: str
    ) -> Optional[Path]:
        """保存 base64 編碼的圖片"""
        try:
            header, encoded = data_uri.split(',', 1)
            image_data = base64.b64decode(encoded)

            # 解析圖片類型
            mime_match = re.search(r'data:image/(\w+)', header)
            ext = mime_match.group(1) if mime_match else image_format

            # 生成檔名
            image_hash = self._generate_image_hash(image_data)
            image_filename = f"image_{image_hash}.{ext}"
            image_path = images_dir / image_filename

            # 保存圖片
            if not image_path.exists():
                image_path.write_bytes(image_data)

            return image_path

        except Exception as e:
            self.logger.warning(f"Failed to save base64 image: {e}")
            return None

    def _download_image(
        self,
        url: str,
        images_dir: Path,
        image_format: str
    ) -> Optional[Path]:
        """下載遠端圖片"""
        try:
            if self.verbose:
                self.logger.info(f"Downloading remote image: {url}")

            response = requests.get(url, timeout=10, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            response.raise_for_status()

            image_data = response.content

            # 判斷圖片類型
            content_type = response.headers.get('Content-Type', '')
            ext = self._get_image_extension(content_type, image_format)

            # 從 URL 取得副檔名
            if ext == image_format:
                url_ext = Path(urlparse(url).path).suffix.lstrip('.')
                if url_ext in ['png', 'jpg', 'jpeg', 'gif', 'bmp', 'svg']:
                    ext = url_ext

            # 生成檔名
            image_hash = self._generate_image_hash(image_data)
            image_filename = f"image_{image_hash}.{ext}"
            image_path = images_dir / image_filename

            # 保存圖片
            if not image_path.exists():
                image_path.write_bytes(image_data)

            if self.verbose:
                self.logger.debug(f"Downloaded: {url} -> {image_filename}")

            return image_path

        except Exception as e:
            self.logger.warning(f"Failed to download image {url}: {e}")
            return None

    def _copy_local_image(
        self,
        src: str,
        images_dir: Path,
        html_path: Path,
        image_format: str
    ) -> Optional[Path]:
        """複製本地圖片"""
        try:
            html_dir = html_path.parent
            image_src_path = None

            # 處理絕對路徑
            if src.startswith('/'):
                image_src_path = Path(src)
            else:
                image_src_path = (html_dir / src).resolve()

            # 檢查文件是否存在
            if not image_src_path.exists():
                if src.startswith('/'):
                    relative_src = src.lstrip('/')
                    image_src_path = (html_dir / relative_src).resolve()

                    if not image_src_path.exists():
                        self.logger.warning(f"Local image not found: {src}")
                        return None
                else:
                    self.logger.warning(f"Local image not found: {image_src_path}")
                    return None

            # 讀取圖片
            image_data = image_src_path.read_bytes()

            # 取得副檔名
            ext = image_src_path.suffix.lstrip('.') or image_format

            # 生成檔名
            image_hash = self._generate_image_hash(image_data)
            image_filename = f"image_{image_hash}.{ext}"
            image_path = images_dir / image_filename

            # 保存圖片
            if not image_path.exists():
                image_path.write_bytes(image_data)

            if self.verbose:
                self.logger.debug(f"Copied local image: {image_src_path} -> {image_filename}")

            return image_path

        except Exception as e:
            self.logger.warning(f"Failed to copy local image {src}: {e}")
            return None

    def _generate_image_hash(self, image_data: bytes) -> str:
        """生成圖片的唯一識別碼（FIPS 兼容）"""
        try:
            return hashlib.sha256(image_data).hexdigest()[:12]
        except Exception as e:
            self.logger.warning(f"Hash generation failed, using UUID: {e}")
            return str(uuid.uuid4()).replace("-", "")[:12]

    def _get_image_extension(self, content_type: str, default_format: str) -> str:
        """根據 MIME 類型返回檔案副檔名"""
        mime_map = {
            "image/png": "png",
            "image/jpeg": "jpg",
            "image/jpg": "jpg",
            "image/gif": "gif",
            "image/bmp": "bmp",
            "image/svg+xml": "svg",
        }
        return mime_map.get(content_type.lower(), default_format)

    # ==================== HTML 轉 Markdown ====================

    def _html_to_markdown(self, html: str) -> str:
        """將 HTML 轉換為 Markdown"""
        # 處理表格
        html = self._convert_tables_to_markdown(html)

        # 處理圖片
        html = self._convert_images_to_markdown(html)

        # 處理程式碼區塊
        html = self._convert_code_blocks_to_markdown(html)

        # 處理標題
        for i in range(6, 0, -1):
            html = re.sub(
                f'<h{i}[^>]*>(.*?)</h{i}>',
                lambda m: f"\n{'#' * i} {m.group(1).strip()}\n",
                html,
                flags=re.DOTALL
            )

        # 處理粗體
        html = re.sub(r'<strong[^>]*>(.*?)</strong>', r'**\1**', html, flags=re.DOTALL)
        html = re.sub(r'<b[^>]*>(.*?)</b>', r'**\1**', html, flags=re.DOTALL)

        # 處理斜體
        html = re.sub(r'<em[^>]*>(.*?)</em>', r'*\1*', html, flags=re.DOTALL)
        html = re.sub(r'<i[^>]*>(.*?)</i>', r'*\1*', html, flags=re.DOTALL)

        # 處理連結
        html = re.sub(
            r'<a[^>]*href=["\']([^"\']*)["\'][^>]*>(.*?)</a>',
            r'[\2](\1)',
            html,
            flags=re.DOTALL
        )

        # 處理段落
        html = re.sub(r'<p[^>]*>(.*?)</p>', r'\n\1\n', html, flags=re.DOTALL)

        # 處理換行
        html = re.sub(r'<br\s*/?>', '\n', html)

        # 處理水平線
        html = re.sub(r'<hr\s*/?>', '\n---\n', html)

        # 處理引用
        html = re.sub(
            r'<blockquote[^>]*>(.*?)</blockquote>',
            lambda m: '\n' + '\n'.join('> ' + line for line in m.group(1).strip().split('\n')) + '\n',
            html,
            flags=re.DOTALL
        )

        # 處理列表
        html = self._convert_lists_to_markdown(html)

        # 移除剩餘的 HTML 標籤
        html = re.sub(r'<[^>]+>', '', html)

        # 清理多餘的空行
        html = re.sub(r'\n{3,}', '\n\n', html)

        return html.strip()

    def _convert_tables_to_markdown(self, html: str) -> str:
        """將 HTML 表格轉換為 Markdown 表格"""
        def table_replacer(match):
            table_html = match.group(0)
            rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table_html, re.DOTALL)
            if not rows:
                return ""

            markdown_rows = []
            is_first_row = True
            max_cols = 0

            # 找出最大欄數
            for row in rows:
                cells = re.findall(r'<t[hd][^>]*>(.*?)</t[hd]>', row, re.DOTALL)
                max_cols = max(max_cols, len(cells))

            # 建立表格
            for row in rows:
                cells = re.findall(r'<t[hd][^>]*>(.*?)</t[hd]>', row, re.DOTALL)

                cleaned_cells = []
                for cell in cells:
                    cell_text = re.sub(r'<[^>]+>', '', cell).strip()
                    cell_text = re.sub(r'\s+', ' ', cell_text)
                    cleaned_cells.append(cell_text)

                # 補齊欄數
                while len(cleaned_cells) < max_cols:
                    cleaned_cells.append("")

                if cleaned_cells:
                    markdown_row = "| " + " | ".join(cleaned_cells) + " |"
                    markdown_rows.append(markdown_row)

                    if is_first_row:
                        separator = "| " + " | ".join(["---"] * max_cols) + " |"
                        markdown_rows.append(separator)
                        is_first_row = False

            return "\n" + "\n".join(markdown_rows) + "\n"

        return re.sub(r'<table[^>]*>.*?</table>', table_replacer, html, flags=re.DOTALL)

    def _convert_images_to_markdown(self, html: str) -> str:
        """將 HTML 圖片標籤轉換為 Markdown"""
        def image_replacer(match):
            img_tag = match.group(0)

            src_match = re.search(r'src=["\']([^"\']*)["\']', img_tag)
            src = src_match.group(1) if src_match else ""

            alt_match = re.search(r'alt=["\']([^"\']*)["\']', img_tag)
            alt = alt_match.group(1) if alt_match else ""

            return f"![{alt}]({src})"

        return re.sub(r'<img[^>]*>', image_replacer, html)

    def _convert_code_blocks_to_markdown(self, html: str) -> str:
        """將 HTML 程式碼區塊轉換為 Markdown"""
        def code_block_replacer(match):
            code_content = match.group(1)
            code_content = re.sub(r'<[^>]+>', '', code_content)
            return f"\n```\n{code_content.strip()}\n```\n"

        html = re.sub(
            r'<pre[^>]*><code[^>]*>(.*?)</code></pre>',
            code_block_replacer,
            html,
            flags=re.DOTALL
        )
        html = re.sub(r'<pre[^>]*>(.*?)</pre>', code_block_replacer, html, flags=re.DOTALL)
        html = re.sub(r'<code[^>]*>(.*?)</code>', r'`\1`', html, flags=re.DOTALL)

        return html

    def _convert_lists_to_markdown(self, html: str) -> str:
        """將 HTML 列表轉換為 Markdown"""
        html = re.sub(
            r'<ol[^>]*>(.*?)</ol>',
            lambda m: self._process_ordered_list(m.group(1)),
            html,
            flags=re.DOTALL
        )
        html = re.sub(
            r'<ul[^>]*>(.*?)</ul>',
            lambda m: self._process_unordered_list(m.group(1)),
            html,
            flags=re.DOTALL
        )
        return html

    def _process_ordered_list(self, list_content: str) -> str:
        """處理有序列表"""
        items = re.findall(r'<li[^>]*>(.*?)</li>', list_content, re.DOTALL)
        result = "\n"
        for i, item in enumerate(items, 1):
            item_text = re.sub(r'<[^>]+>', '', item).strip()
            result += f"{i}. {item_text}\n"
        return result

    def _process_unordered_list(self, list_content: str) -> str:
        """處理無序列表"""
        items = re.findall(r'<li[^>]*>(.*?)</li>', list_content, re.DOTALL)
        result = "\n"
        for item in items:
            item_text = re.sub(r'<[^>]+>', '', item).strip()
            result += f"- {item_text}\n"
        return result

    # ==================== 元數據處理 ====================

    def _extract_metadata(self, html_path: Path, soup: BeautifulSoup) -> Dict[str, Any]:
        """提取 HTML 文件的元數據"""
        metadata = {
            "filename": html_path.name,
            "file_size": html_path.stat().st_size,
            "extension": html_path.suffix,
        }

        try:
            # 提取 title
            title_tag = soup.find('title')
            if title_tag:
                metadata["title"] = title_tag.get_text().strip()

            # 提取 meta 標籤
            meta_description = soup.find('meta', attrs={'name': 'description'})
            if meta_description:
                metadata["description"] = meta_description.get('content', '')

            meta_author = soup.find('meta', attrs={'name': 'author'})
            if meta_author:
                metadata["author"] = meta_author.get('content', '')

            meta_keywords = soup.find('meta', attrs={'name': 'keywords'})
            if meta_keywords:
                metadata["keywords"] = meta_keywords.get('content', '')

        except Exception as e:
            self.logger.warning(f"Failed to extract metadata: {e}")

        return metadata

    # ==================== 工具方法 ====================

    def _safe_remove_dir(self, root: Path) -> None:
        """安全移除輸出資料夾"""
        try:
            for p in sorted(root.glob("**/*"), reverse=True):
                if p.is_file():
                    p.unlink(missing_ok=True)
                elif p.is_dir():
                    p.rmdir()
            root.rmdir()
            if self.verbose:
                self.logger.info(f"Removed output folder: {root}")
        except Exception as e:
            if self.verbose:
                self.logger.warning(f"Cleanup failed for {root}: {e}")