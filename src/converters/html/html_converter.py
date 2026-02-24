import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, Any, List, Union
import base64
import hashlib
import uuid
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup


class HTMLProcessError(Exception):
    """Raised when the HTML processing pipeline fails."""


@dataclass
class ProcessResult:
    """處理結果資料結構"""
    output_dir: Optional[Path]
    md_content: Optional[str]
    md_path: Optional[Path]
    images: Optional[List[Path]]
    metadata: Optional[Dict[str, Any]]


class HTMLConverter:
    """
    將 HTML 文件轉換為 Markdown 的轉換器。

    用法：
        converter = HTMLConverter(output_root="/tmp/html_output")
        result = converter.process_html("/path/a.html")
        result2 = converter.process_html("/path/b.html")
        converter.close()

    或者：
        with HTMLConverter(output_root="/tmp/html_output") as converter:
            r1 = converter.process_html("/path/a.html")
            r2 = converter.process_html("/path/b.html")
    """

    def __init__(
        self,
        *,
        output_root: str = "/tmp/html_output",
        verbose: bool = True,
        extract_images: bool = True,
        keep_output: bool = True,
        convert_image_format: str = "png",
        download_remote_images: bool = False,
    ) -> None:
        """
        初始化 HTMLConverter。

        Parameters
        ----------
        output_root : str
            輸出根目錄路徑。
        verbose : bool
            是否顯示詳細日誌。
        extract_images : bool
            是否提取並保存圖片。
        keep_output : bool
            是否保留輸出目錄。
        convert_image_format : str
            圖片輸出格式（png/jpg）。
        download_remote_images : bool
            是否下載遠端圖片（HTTP/HTTPS）。
        """
        self.logger = self._setup_logger()
        self.output_root = Path(output_root)
        self.output_root.mkdir(parents=True, exist_ok=True)
        
        self.verbose = verbose
        self.extract_images = extract_images
        self.keep_output = keep_output
        self.convert_image_format = convert_image_format
        self.download_remote_images = download_remote_images
        
        if self.verbose:
            self.logger.info(f"HTMLConverter initialized (extract_images={extract_images}, download_remote={download_remote_images})")

    # ---------- context manager -----------
    def __enter__(self) -> "HTMLConverter":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        """清理資源（如有需要）"""
        if self.verbose:
            self.logger.info("HTMLConverter closed.")

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

    # ---------- public API -----------
    def process_html(
        self,
        html_path: str | Path,
        *,
        extract_images: Optional[bool] = None,
        keep_output: Optional[bool] = None,
        download_remote_images: Optional[bool] = None,
    ) -> ProcessResult:
        """
        處理單一 HTML 文件，轉換為 Markdown。

        Parameters
        ----------
        html_path : str | Path
            HTML 文件路徑。
        extract_images : Optional[bool]
            是否提取圖片，不指定則使用初始化時的設定。
        keep_output : Optional[bool]
            是否保留輸出目錄，不指定則使用初始化時的設定。
        download_remote_images : Optional[bool]
            是否下載遠端圖片，不指定則使用初始化時的設定。

        Returns
        -------
        ProcessResult
            包含 markdown 內容、圖片路徑等的處理結果。
        """
        html_path = Path(html_path)
        if not html_path.exists():
            raise HTMLProcessError(f"HTML file not found: {html_path}")

        # 參數合併
        extract_images = self.extract_images if extract_images is None else extract_images
        keep_output = self.keep_output if keep_output is None else keep_output
        download_remote_images = self.download_remote_images if download_remote_images is None else download_remote_images

        html_name = html_path.stem
        output_dir = self._create_output_structure(html_name)

        if self.verbose:
            self.logger.info(f"Processing '{html_path.name}' → {output_dir}")

        # 1) 轉換為 Markdown
        try:
            md_content, images = self._convert_to_markdown(
                html_path,
                output_dir,
                extract_images=extract_images,
                download_remote_images=download_remote_images,
            )
        except Exception as e:
            raise HTMLProcessError(f"Conversion failed for {html_path.name}: {e}") from e

        # 2) 保存 Markdown                                                                  
        md_path = output_dir / f"{html_name}.md"
        self._save_markdown(md_content, md_path)

        if self.verbose:
            self.logger.info(f"MD saved: {md_path}")
            if images:
                self.logger.info(f"Images extracted: {len(images)} files")

        # 3) 提取元數據
        metadata = self._extract_metadata(html_path)

        # 4) 清理（可選）
        if not keep_output:
            self._safe_remove_dir(output_dir)
            output_dir = None

        return ProcessResult(
            output_dir=output_dir,
            md_content=md_content,
            md_path=md_path if md_path.exists() else None,
            images=images if images else None,
            metadata=metadata,
        )

    def process_htmls(
        self,
        html_paths: List[str | Path],
        *,
        extract_images: Optional[bool] = None,
        keep_output: Optional[bool] = None,
        download_remote_images: Optional[bool] = None,
    ) -> Dict[str, ProcessResult]:
        """
        批次處理多個 HTML 文件。

        Parameters
        ----------
        html_paths : List[str | Path]
            HTML 文件路徑列表。
        extract_images : Optional[bool]
            是否提取圖片。
        keep_output : Optional[bool]
            是否保留輸出目錄。
        download_remote_images : Optional[bool]
            是否下載遠端圖片。

        Returns
        -------
        Dict[str, ProcessResult]
            以檔名（不含副檔名）為 key 的結果字典。
        """
        html_paths_p: List[Path] = [Path(p) for p in html_paths]
        for p in html_paths_p:
            if not p.exists():
                raise HTMLProcessError(f"HTML file not found: {p}")

        if self.verbose:
            names = ", ".join([p.name for p in html_paths_p])
            self.logger.info(f"Batch processing {len(html_paths_p)} files: {names}")

        results: Dict[str, ProcessResult] = {}
        for p in html_paths_p:
            name = p.stem
            try:
                result = self.process_html(
                    p,
                    extract_images=extract_images,
                    keep_output=keep_output,
                    download_remote_images=download_remote_images,
                )
                results[name] = result
            except HTMLProcessError as e:
                self.logger.error(f"Failed to process {p.name}: {e}")
                results[name] = ProcessResult(
                    output_dir=None,
                    md_content=None,
                    md_path=None,
                    images=None,
                    metadata={"error": str(e)},
                )

        return results

    # ---------- internals -----------
    def _convert_to_markdown(
        self,
        html_path: Path,
        output_dir: Path,
        *,
        extract_images: bool,
        download_remote_images: bool,
    ) -> tuple[str, List[Path]]:
        """
        將 HTML 轉換為 Markdown。

        Returns
        -------
        tuple[str, List[Path]]
            (markdown 內容, 圖片路徑列表)
        """
        # 讀取 HTML 內容
        html_content = html_path.read_text(encoding="utf-8")
        
        # 使用 BeautifulSoup 解析
        soup = BeautifulSoup(html_content, 'html.parser')
        
        images_dir = output_dir / "images"
        images_dir.mkdir(exist_ok=True)
        extracted_images: List[Path] = []

        # 處理圖片
        if extract_images:
            extracted_images = self._extract_images(
                soup, 
                images_dir, 
                html_path,
                download_remote_images
            )

        # 取得 body 內容，如果沒有 body 就用整個文件
        body = soup.find('body')
        if body:
            html_to_convert = str(body)
        else:
            html_to_convert = str(soup)

        # 將 HTML 轉換為 Markdown
        md_content = self._html_to_markdown(html_to_convert)

        return md_content, extracted_images

    def _extract_images(
        self,
        soup: BeautifulSoup,
        images_dir: Path,
        html_path: Path,
        download_remote: bool,
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
                
                # 判斷是否為 base64 圖片
                if src.startswith('data:image'):
                    image_path = self._save_base64_image(src, images_dir)
                
                # 判斷是否為遠端圖片
                elif src.startswith(('http://', 'https://')):
                    if download_remote:
                        image_path = self._download_image(src, images_dir)
                    else:
                        # 如果不下載遠端圖片，保留原始 URL
                        if self.verbose:
                            self.logger.info(f"Skipping remote image: {src}")
                        continue
                
                # 本地路徑圖片（相對路徑或絕對路徑）
                else:
                    image_path = self._copy_local_image(src, images_dir, html_path)
                
                # 如果成功處理圖片，更新 src 路徑並記錄
                if image_path:
                    extracted_images.append(image_path)
                    # 更新 img 標籤的 src 為相對於 markdown 文件的路徑
                    img['src'] = f"images/{image_path.name}"
                    if self.verbose:
                        self.logger.debug(f"Processed image: {src} -> images/{image_path.name}")
                        
            except Exception as e:
                self.logger.warning(f"Failed to process image {src}: {e}")

        return extracted_images

    def _save_base64_image(self, data_uri: str, images_dir: Path) -> Optional[Path]:
        """保存 base64 編碼的圖片"""
        try:
            # 解析 data URI
            header, encoded = data_uri.split(',', 1)
            image_data = base64.b64decode(encoded)
            
            # 解析圖片類型
            mime_match = re.search(r'data:image/(\w+)', header)
            ext = mime_match.group(1) if mime_match else self.convert_image_format
            
            # 生成檔名
            image_hash = self._generate_image_hash(image_data)
            image_filename = f"image_{image_hash}.{ext}"
            image_path = images_dir / image_filename
            
            # 保存圖片
            image_path.write_bytes(image_data)
            return image_path
            
        except Exception as e:
            self.logger.warning(f"Failed to save base64 image: {e}")
            return None

    def _download_image(self, url: str, images_dir: Path) -> Optional[Path]:
        """下載遠端圖片"""
        try:
            if self.verbose:
                self.logger.info(f"Downloading remote image: {url}")
            
            response = requests.get(url, timeout=10, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            response.raise_for_status()
            
            image_data = response.content
            
            # 從 URL 或 Content-Type 判斷圖片類型
            content_type = response.headers.get('Content-Type', '')
            ext = self._get_image_extension(content_type)
            
            # 如果無法從 Content-Type 判斷，嘗試從 URL 取得
            if ext == self.convert_image_format:
                url_ext = Path(urlparse(url).path).suffix.lstrip('.')
                if url_ext in ['png', 'jpg', 'jpeg', 'gif', 'bmp', 'svg']:
                    ext = url_ext
            
            # 生成檔名
            image_hash = self._generate_image_hash(image_data)
            image_filename = f"image_{image_hash}.{ext}"
            image_path = images_dir / image_filename
            
            # 避免重複下載相同圖片
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
        html_path: Path
    ) -> Optional[Path]:
        """複製本地圖片"""
        try:
            html_dir = html_path.parent
            image_src_path = None
            
            # 處理絕對路徑（以 / 開頭）
            if src.startswith('/'):
                image_src_path = Path(src)
            # 處理相對路徑
            else:
                # 嘗試相對於 HTML 文件的路徑
                image_src_path = (html_dir / src).resolve()
            
            # 檢查文件是否存在
            if not image_src_path.exists():
                # 如果絕對路徑不存在，嘗試相對路徑
                if src.startswith('/'):
                    # 移除開頭的 /，嘗試作為相對路徑
                    relative_src = src.lstrip('/')
                    image_src_path = (html_dir / relative_src).resolve()
                    
                    if not image_src_path.exists():
                        self.logger.warning(f"Local image not found: {src} (tried absolute and relative paths)")
                        return None
                else:
                    self.logger.warning(f"Local image not found: {image_src_path}")
                    return None
            
            # 讀取圖片數據
            image_data = image_src_path.read_bytes()
            
            # 取得副檔名
            ext = image_src_path.suffix.lstrip('.') or self.convert_image_format
            
            # 生成檔名
            image_hash = self._generate_image_hash(image_data)
            image_filename = f"image_{image_hash}.{ext}"
            image_path = images_dir / image_filename
            
            # 避免重複保存相同圖片
            if not image_path.exists():
                image_path.write_bytes(image_data)
            
            if self.verbose:
                self.logger.debug(f"Copied local image: {image_src_path} -> {image_filename}")
            
            return image_path
            
        except Exception as e:
            self.logger.warning(f"Failed to copy local image {src}: {e}")
            return None

    def _html_to_markdown(self, html: str) -> str:
        """
        將 HTML 轉換為 Markdown，特別處理表格。
        
        Parameters
        ----------
        html : str
            HTML 內容。
            
        Returns
        -------
        str
            Markdown 內容。
        """
        # 處理表格
        html = self._convert_tables_to_markdown(html)
        
        # 處理圖片（必須在移除 HTML 標籤之前）
        html = self._convert_images_to_markdown(html)
        
        # 處理程式碼區塊
        html = self._convert_code_blocks_to_markdown(html)
        
        # 處理標題
        for i in range(6, 0, -1):
            html = re.sub(f'<h{i}[^>]*>(.*?)</h{i}>', 
                         lambda m: f"\n{'#' * i} {m.group(1).strip()}\n", 
                         html, flags=re.DOTALL)
        
        # 處理粗體
        html = re.sub(r'<strong[^>]*>(.*?)</strong>', r'**\1**', html, flags=re.DOTALL)
        html = re.sub(r'<b[^>]*>(.*?)</b>', r'**\1**', html, flags=re.DOTALL)
        
        # 處理斜體
        html = re.sub(r'<em[^>]*>(.*?)</em>', r'*\1*', html, flags=re.DOTALL)
        html = re.sub(r'<i[^>]*>(.*?)</i>', r'*\1*', html, flags=re.DOTALL)
        
        # 處理連結
        html = re.sub(r'<a[^>]*href=["\']([^"\']*)["\'][^>]*>(.*?)</a>', 
                     r'[\2](\1)', html, flags=re.DOTALL)
        
        # 處理段落
        html = re.sub(r'<p[^>]*>(.*?)</p>', r'\n\1\n', html, flags=re.DOTALL)
        
        # 處理換行
        html = re.sub(r'<br\s*/?>', '\n', html)
        
        # 處理水平線
        html = re.sub(r'<hr\s*/?>', '\n---\n', html)
        
        # 處理引用
        html = re.sub(r'<blockquote[^>]*>(.*?)</blockquote>', 
                     lambda m: '\n' + '\n'.join('> ' + line for line in m.group(1).strip().split('\n')) + '\n',
                     html, flags=re.DOTALL)
        
        # 處理列表
        html = self._convert_lists_to_markdown(html)
        
        # 移除剩餘的 HTML 標籤
        html = re.sub(r'<[^>]+>', '', html)
        
        # 清理多餘的空行
        html = re.sub(r'\n{3,}', '\n\n', html)
        
        return html.strip()

    def _convert_tables_to_markdown(self, html: str) -> str:
        """
        將 HTML 表格轉換為 Markdown 表格格式。
        
        Parameters
        ----------
        html : str
            包含 HTML 表格的內容。
            
        Returns
        -------
        str
            轉換後的內容（表格為 Markdown 格式）。
        """
        def table_replacer(match):
            table_html = match.group(0)
            
            # 提取所有行
            rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table_html, re.DOTALL)
            if not rows:
                return ""
            
            markdown_rows = []
            is_first_row = True
            max_cols = 0
            
            # 第一遍：找出最大欄數
            for row in rows:
                cells = re.findall(r'<t[hd][^>]*>(.*?)</t[hd]>', row, re.DOTALL)
                max_cols = max(max_cols, len(cells))
            
            # 第二遍：建立表格
            for row in rows:
                # 提取單元格（th 或 td）
                cells = re.findall(r'<t[hd][^>]*>(.*?)</t[hd]>', row, re.DOTALL)
                
                # 清理單元格內容
                cleaned_cells = []
                for cell in cells:
                    # 移除 HTML 標籤，保留文字
                    cell_text = re.sub(r'<[^>]+>', '', cell).strip()
                    # 移除單元格內的換行，用空格替換
                    cell_text = re.sub(r'\s+', ' ', cell_text)
                    cleaned_cells.append(cell_text)
                
                # 補齊欄數（如果某行欄數較少）
                while len(cleaned_cells) < max_cols:
                    cleaned_cells.append("")
                
                if cleaned_cells:
                    # 建立表格行
                    markdown_row = "| " + " | ".join(cleaned_cells) + " |"
                    markdown_rows.append(markdown_row)
                    
                    # 如果是第一行，添加分隔線
                    if is_first_row:
                        separator = "| " + " | ".join(["---"] * max_cols) + " |"
                        markdown_rows.append(separator)
                        is_first_row = False
            
            return "\n" + "\n".join(markdown_rows) + "\n"
        
        # 替換所有表格
        result = re.sub(r'<table[^>]*>.*?</table>', table_replacer, html, flags=re.DOTALL)
        return result

    def _convert_images_to_markdown(self, html: str) -> str:
        """
        將 HTML 圖片標籤轉換為 Markdown 圖片格式。
        
        Parameters
        ----------
        html : str
            包含 HTML 圖片標籤的內容。
            
        Returns
        -------
        str
            轉換後的內容（圖片為 Markdown 格式）。
        """
        def image_replacer(match):
            img_tag = match.group(0)
            
            # 提取 src 屬性
            src_match = re.search(r'src=["\']([^"\']*)["\']', img_tag)
            src = src_match.group(1) if src_match else ""
            
            # 提取 alt 屬性
            alt_match = re.search(r'alt=["\']([^"\']*)["\']', img_tag)
            alt = alt_match.group(1) if alt_match else ""
            
            # 返回 Markdown 格式
            return f"![{alt}]({src})"
        
        # 替換所有圖片標籤
        result = re.sub(r'<img[^>]*>', image_replacer, html)
        return result

    def _convert_code_blocks_to_markdown(self, html: str) -> str:
        """
        將 HTML 程式碼區塊轉換為 Markdown 格式。
        
        Parameters
        ----------
        html : str
            包含 HTML 程式碼區塊的內容。
            
        Returns
        -------
        str
            轉換後的內容（程式碼為 Markdown 格式）。
        """
        # 處理 <pre><code> 區塊
        def code_block_replacer(match):
            code_content = match.group(1)
            # 移除 HTML 標籤但保留內容
            code_content = re.sub(r'<[^>]+>', '', code_content)
            return f"\n```\n{code_content.strip()}\n```\n"
        
        html = re.sub(r'<pre[^>]*><code[^>]*>(.*?)</code></pre>', 
                     code_block_replacer, html, flags=re.DOTALL)
        html = re.sub(r'<pre[^>]*>(.*?)</pre>', 
                     code_block_replacer, html, flags=re.DOTALL)
        
        # 處理行內程式碼
        html = re.sub(r'<code[^>]*>(.*?)</code>', r'`\1`', html, flags=re.DOTALL)
        
        return html

    def _convert_lists_to_markdown(self, html: str) -> str:
        """
        將 HTML 列表轉換為 Markdown 列表格式。
        
        Parameters
        ----------
        html : str
            包含 HTML 列表的內容。
            
        Returns
        -------
        str
            轉換後的內容（列表為 Markdown 格式）。
        """
        # 處理有序列表項
        html = re.sub(r'<ol[^>]*>(.*?)</ol>', 
                     lambda m: self._process_ordered_list(m.group(1)), 
                     html, flags=re.DOTALL)
        
        # 處理無序列表項
        html = re.sub(r'<ul[^>]*>(.*?)</ul>', 
                     lambda m: self._process_unordered_list(m.group(1)), 
                     html, flags=re.DOTALL)
        
        return html

    def _process_ordered_list(self, list_content: str) -> str:
        """處理有序列表"""
        items = re.findall(r'<li[^>]*>(.*?)</li>', list_content, re.DOTALL)
        result = "\n"
        for i, item in enumerate(items, 1):
            # 移除內部 HTML 標籤
            item_text = re.sub(r'<[^>]+>', '', item).strip()
            result += f"{i}. {item_text}\n"
        return result

    def _process_unordered_list(self, list_content: str) -> str:
        """處理無序列表"""
        items = re.findall(r'<li[^>]*>(.*?)</li>', list_content, re.DOTALL)
        result = "\n"
        for item in items:
            # 移除內部 HTML 標籤
            item_text = re.sub(r'<[^>]+>', '', item).strip()
            result += f"- {item_text}\n"
        return result

    def _generate_image_hash(self, image_data: bytes) -> str:
        """
        生成圖片的唯一識別碼（FIPS 兼容）。
        優先使用 SHA256，如果失敗則使用 UUID。

        Parameters
        ----------
        image_data : bytes
            圖片的二進制數據。

        Returns
        -------
        str
            12 字元的唯一識別碼。
        """
        try:
            # 嘗試使用 SHA256（FIPS 兼容）
            return hashlib.sha256(image_data).hexdigest()[:12]
        except Exception as e:
            # 如果 SHA256 也失敗（極少見），使用 UUID
            self.logger.warning(f"Hash generation failed, using UUID: {e}")
            return str(uuid.uuid4()).replace("-", "")[:12]

    def _get_image_extension(self, content_type: str) -> str:
        """根據 MIME 類型返回檔案副檔名"""
        mime_map = {
            "image/png": "png",
            "image/jpeg": "jpg",
            "image/jpg": "jpg",
            "image/gif": "gif",
            "image/bmp": "bmp",
            "image/svg+xml": "svg",
        }
        return mime_map.get(content_type.lower(), self.convert_image_format)

    def _save_markdown(self, content: str, output_path: Path) -> None:
        """保存 Markdown 內容到檔案"""
        output_path.write_text(content, encoding="utf-8")

    def _create_output_structure(self, html_name: str) -> Path:
        """
        建立輸出目錄結構。

        Returns
        -------
        Path
            文檔專屬的輸出目錄。
        """
        output_dir = (self.output_root / html_name).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir

    def _extract_metadata(self, html_path: Path) -> Dict[str, Any]:
        """
        提取 HTML 文件的元數據。

        Returns
        -------
        Dict[str, Any]
            包含文檔基本資訊的字典。
        """
        metadata = {
            "filename": html_path.name,
            "file_size": html_path.stat().st_size,
            "extension": html_path.suffix,
        }

        try:
            html_content = html_path.read_text(encoding="utf-8")
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # 提取 title
            title_tag = soup.find('title')
            if title_tag:
                metadata["title"] = title_tag.get_text().strip()
            
            # 提取 meta 標籤資訊
            meta_description = soup.find('meta', attrs={'name': 'description'})
            if meta_description:
                metadata["description"] = meta_description.get('content', '')
            
            meta_author = soup.find('meta', attrs={'name': 'author'})
            if meta_author:
                metadata["author"] = meta_author.get('content', '')
                
        except Exception as e:
            self.logger.warning(f"Failed to extract metadata: {e}")

        return metadata

    def _safe_remove_dir(self, root: Path) -> None:
        """
        安全移除輸出資料夾。
        """
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
                self.logger.warning(f"Warn: cleanup failed for {root}: {e}")