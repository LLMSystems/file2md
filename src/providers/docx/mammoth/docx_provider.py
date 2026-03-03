import asyncio
import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import mammoth

from src.core.client.llm_client import AsyncLLMChat
from src.core.types import (Artifact, ArtifactType, ProcessOptions,
                            ProcessResult)
from src.providers.base import BaseProvider


class DOCXProcessError(Exception):
    """Raised when the DOCX processing pipeline fails."""


@dataclass
class MammothProcessResult:
    """內部處理結果資料結構"""
    extract_dir: Optional[Path]
    md_content: Optional[str]
    md_path: Optional[Path]
    images: Optional[List[Path]]
    metadata: Optional[Dict[str, Any]]


class DOCXMammothProvider(BaseProvider):
    """
    使用 Mammoth 將 Word 文檔轉換為 Markdown 的 Provider。

    用法：
        provider = DOCXMammothProvider(output_root="./test_outputs")
        docs = ["./docs/demo.docx", "./docs/report.docx"]
        result = provider.convert_files(docs, output_root=Path("./output"))

    或者：
        with DOCXMammothProvider(output_root="./test_outputs") as provider:
            r1 = provider.convert_files(["/path/a.docx", "/path/b.docx"], output_root=Path("./output"))
    """
    name = "mammoth"

    def __init__(
        self,
        *,
        verbose: bool = True,
        default_extract_images: bool = True,
        default_keep_output: bool = True,
        default_convert_image_format: str = "png",
        default_style_map: Optional[str] = None,
        default_image_alt_text: str = "",
        default_llm_model: Optional[str] = None,
        default_llm_config_path: Optional[str] = None,
        default_llm_params: Optional[Dict[str, Any]] = None,
        llm_client: Optional[AsyncLLMChat] = None,
    ) -> None:
        """
        初始化 DOCXMammothProvider。

        Parameters
        ----------
        output_root : str
            輸出根目錄路徑。
        verbose : bool
            是否顯示詳細日誌。
        default_extract_images : bool
            預設是否提取並保存圖片。
        default_keep_output : bool
            預設是否保留輸出目錄。
        default_convert_image_format : str
            圖片輸出格式（png/jpg）。
        default_style_map : Optional[str]
            Mammoth 的樣式映射規則。
        default_image_alt_text : str
            圖片的替代文字。""=空白，其他=自定義文字。
        """
        super().__init__()
 
        self.verbose = verbose
        self.default_extract_images = default_extract_images
        self.default_keep_output = default_keep_output
        self.default_convert_image_format = default_convert_image_format
        self.default_style_map = default_style_map
        self.default_image_alt_text = default_image_alt_text

        # llm 相關預設（目前沒用到，先放這）
        self.llm_client = llm_client
        self.default_llm_model = default_llm_model
        self.default_llm_config_path = default_llm_config_path
        self.default_llm_params = default_llm_params or {}
        self.llm_client: Optional[AsyncLLMChat] = None

        if self.llm_client is None and self.default_llm_model and self.default_llm_config_path:
            self.llm_client = AsyncLLMChat(
                model=self.default_llm_model,
                config_path=self.default_llm_config_path
            )
            if self.verbose:
                self.logger.info(f"Initialized LLM client with model: {self.default_llm_model}")
        else:
            if self.verbose:
                self.logger.info("No default LLM model specified for DOCXMammothProvider.")

    # ---------- context manager -----------
    def __enter__(self) -> "DOCXMammothProvider":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        """清理資源（如有需要）"""
        if self.verbose:
            self.logger.info("DOCXMammothProvider closed.")

    # ---------- public API -----------
    def convert_files(
        self,
        docx_paths: Sequence[Path],
        *,
        output_root: Path,
        options: Optional[ProcessOptions] = None,
    ) -> Dict[str, ProcessResult]:
        """
        轉換多個 DOCX 文檔為 Markdown。

        Parameters
        ----------
        docx_paths : Sequence[Path]
            DOCX 文檔路徑列表。
        output_root : Path
            輸出根目錄。
        options : Optional[ProcessOptions]
            處理選項。

        Returns
        -------
        Dict[str, ProcessResult]
            以檔案路徑為 key 的處理結果字典。
        """
        options = options or ProcessOptions()
        docs = [Path(p) for p in docx_paths]
        if not docs:
            return {}

        if isinstance(output_root, str):
            output_root = Path(output_root)
        self.output_root = output_root
        self.output_root.mkdir(parents=True, exist_ok=True)

        # 從 options 中提取參數
        extract_images = options.extra.get("extract_images", self.default_extract_images)
        keep_output = options.extra.get("keep_output", self.default_keep_output)
        style_map = options.extra.get("style_map", self.default_style_map)
        image_alt_text = options.extra.get("image_alt_text", self.default_image_alt_text)

        # parse image
        parse_image = options.extra.get("parse_image", False)

        # 處理文檔
        old_map = self.convert_docx(
            docx_paths=docs,
            extract_images=extract_images,
            keep_output=keep_output,
            style_map=style_map,
            image_alt_text=image_alt_text,
            parse_image=parse_image,
        )

        # 轉換為標準的 ProcessResult 格式
        out: Dict[str, ProcessResult] = {}
        for src in docs:
            stem = src.stem
            r = old_map.get(stem)
            if not r:
                out[str(src)] = ProcessResult(
                    source=src,
                    extract_dir=output_root / stem,
                    meta={"error": "missing result from Mammoth"}
                )
                continue

            # 構建 artifacts 列表
            artifacts: List[Artifact] = []
            
            # 添加元數據（如果有）
            if r.metadata:
                # 保存元數據為 JSON 文件
                metadata_path = r.extract_dir / f"{stem}_metadata.json"
                metadata_path.write_text(json.dumps(r.metadata, indent=2, ensure_ascii=False))
                artifacts.append(Artifact(
                    name="metadata",
                    type=ArtifactType.JSON,
                    path=metadata_path,
                    mime="application/json"
                ))

            # 添加圖片
            if r.images:
                for img in r.images:
                    artifacts.append(Artifact(
                        name=img.name,
                        type=ArtifactType.IMAGE,
                        path=img
                    ))

            out[str(src)] = ProcessResult(
                source=src,
                md_text=r.md_content,
                md_path=r.md_path,
                ir=r.metadata,
                artifacts=artifacts,
                extract_dir=r.extract_dir,
                meta={
                    "provider": self.name,
                    "extract_images": extract_images,
                    "image_count": len(r.images) if r.images else 0,
                },
            )

        return out

    def convert_docx(
        self,
        docx_paths: List[Path],
        *,
        extract_images: Optional[bool] = None,
        keep_output: Optional[bool] = None,
        style_map: Optional[str] = None,
        image_alt_text: Optional[str] = None,
        parse_image: Optional[bool] = None,
    ) -> Dict[str, MammothProcessResult]:
        """
        批次處理多個 Word 文檔。

        Parameters
        ----------
        docx_paths : List[Path]
            Word 文檔路徑列表。
        extract_images : Optional[bool]
            是否提取圖片。
        keep_output : Optional[bool]
            是否保留輸出目錄。
        style_map : Optional[str]
            自定義樣式映射。
        image_alt_text : Optional[str]
            圖片替代文字。
        parse_image : Optional[bool]
            是否解析圖片。

        Returns
        -------
        Dict[str, MammothProcessResult]
            以檔名（不含副檔名）為 key 的結果字典。
        """
        # 使用預設值
        extract_images = self.default_extract_images if extract_images is None else extract_images
        keep_output = self.default_keep_output if keep_output is None else keep_output
        style_map = self.default_style_map if style_map is None else style_map
        image_alt_text = self.default_image_alt_text if image_alt_text is None else image_alt_text

        # 驗證文件存在
        for p in docx_paths:
            if not p.exists():
                raise DOCXProcessError(f"Document not found: {p}")

        if self.verbose:
            names = ", ".join([p.name for p in docx_paths])
            self.logger.info(f"Processing {len(docx_paths)} documents: {names}")

        results: Dict[str, MammothProcessResult] = {}
        for p in docx_paths:
            name = p.stem
            try:
                result = self._process_single_doc(
                    p,
                    extract_images=extract_images,
                    keep_output=keep_output,
                    style_map=style_map,
                    image_alt_text=image_alt_text,
                )
                results[name] = result
            except DOCXProcessError as e:
                self.logger.error(f"Failed to process {p.name}: {e}")
                results[name] = MammothProcessResult(
                    extract_dir=None,
                    md_content=None,
                    md_path=None,
                    images=None,
                    metadata={"error": str(e)},
                )

        results = self.parse_images(results, parse_image)

        return results

    # ---------- internals -----------
    def parse_images(self, results: Dict[str, MammothProcessResult], parse_image: bool) -> Dict[str, MammothProcessResult]:
        if not parse_image:
            return results
        # Implement the image parsing logic here
        if not self.llm_client:
            if self.verbose:
                self.logger.warning("LLM client not initialized; skipping image parsing.")
            return results
        # step 1: collect all images from the results
        image_tasks = []
        for name, res in results.items():
            for image_path in res.images:
                if image_path.exists():
                    image_tasks.append((name, "", image_path))
        if len(image_tasks) == 0:
            if self.verbose:
                self.logger.info("No images found for parsing.")
            return results
        
        # step 2: parse each image with LLM
        self.logger.info(f"Parsing {len(image_tasks)} images with LLM...")
        parsed_results = self.parse_image_tasks(image_tasks)

        # step 3: integrate parsed results back into the original results
        for name, img_path, parsed in parsed_results:
            if parsed is None:
                continue
            value = results.get(name)
            md_content = value.md_content if value else None
            if not md_content:
                if self.verbose:
                    self.logger.warning(f"No markdown content found for {name}; cannot integrate parsed image results.")
                continue
            """
            replace the original image reference in md_content with the parsed result (this is just a placeholder logic, you can customize it based on how you want to integrate the parsed results)
            ex : 
                ![](images/b8e32d9cc62e2ffa0977d6cf98ff9d67d4cb5b151ff14961f0b15261e1e3066e.jpg)  
            -->
                ![](images/b8e32d9cc62e2ffa0977d6cf98ff9d67d4cb5b151ff14961f0b15261e1e3066e.jpg)  
                **Parsed Above Image Content**: parsed_content
            """
            new_md_content = md_content.replace(f"![](images/{img_path.name})", f"![](images/{img_path.name})\n\n**Parsed Above Image Content**:\n\n{parsed}\n\n")
            results[name].md_content = new_md_content
            # update md_path content as well
            if value.md_path and value.md_path.exists():
                value.md_path.write_text(new_md_content, encoding="utf-8")

        return results
    
    def parse_image_tasks(self, image_tasks: List[Tuple[str, str, Path]], batch_size: int = 5) -> None:
        prompt = """
你是一個專業的圖片數據解析助手。
我將提供一張圖片與圖片標題，請你從圖片中擷取可辨識的數據與文字資訊。

【請務必遵守以下規則】
1. 僅根據圖片中「實際可見且清晰」的內容回答。
2. 不可臆測、不推測、不補完任何圖片中沒有明確顯示的資訊。
3. 若內容不清楚或無法辨識，請標記為「不確定」，不要給出猜測。
4. 若圖片中沒有有效數據、沒有清楚文字、或沒有可用資訊，請直接回覆：「無」。
5. 如果能讀取到數據，請盡可能精確擷取並結構化整理(請用表格呈現)。
6. 如果是圖表，請分析趨勢但不要過度解讀。

【輸出格式】
- 【圖片整體描述】
- 【可擷取的所有數據列表，請用表格呈現】（若無則寫「無」）
- 【表格或圖表數據&趨勢分析】（若圖片非圖表則略過）
- 【不確定或模糊區域】（若無則寫「無」）

以下是圖片標題：
圖片標題：{image_caption}

請開始解析圖片中的數據。
    """
        async def run():
            results = []
            tasks = []

            for i, (name, caption, img_path) in enumerate(image_tasks):
                # 創建異步任務
                task = asyncio.create_task(self.llm_client.vision_chat(
                    query=prompt.format(image_caption=caption),
                    image_path=img_path,
                    params=self.default_llm_params,
                ))
                tasks.append((name, img_path, task))

                # 當達到批次大小時，執行並收集結果
                if len(tasks) >= batch_size:
                    if self.verbose:
                        self.logger.info(f"Processing batch of {len(tasks)} images...")
                    results.extend(await self._process_tasks(tasks))
                    tasks = []

            # 處理剩餘的任務
            if tasks:
                results.extend(await self._process_tasks(tasks))

            return results

        # 啟動事件迴圈執行
        return asyncio.run(run())

    async def _process_tasks(self, tasks: List[Tuple[str, Path, asyncio.Task]]) -> List[Tuple[str, Path, Any]]:
        results = []
        for name, img_path, task in tasks:
            try:
                # 等待任務完成並收集結果
                result, _ = await task
                results.append((name, img_path, result))
            except Exception as e:
                # 單獨處理每個任務的異常，避免影響其他任務
                if self.verbose:
                    self.logger.warning(f"Failed to process image {img_path}: {e}")
                results.append((name, img_path, None))
        return results

    @staticmethod
    def _read_json_if_exists(path: Path, encoding: str = "utf-8") -> Optional[Dict[str, Any]]:
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding=encoding))
        except json.JSONDecodeError as e:
            raise DOCXProcessError(f"JSON decode error at {path}: {e}") from e


    def _process_single_doc(
        self,
        doc_path: Path,
        *,
        extract_images: bool,
        keep_output: bool,
        style_map: Optional[str],
        image_alt_text: str,
    ) -> MammothProcessResult:
        """
        處理單一 Word 文檔，轉換為 Markdown。

        Returns
        -------
        MammothProcessResult
            包含 markdown 內容、圖片路徑等的處理結果。
        """
        doc_name = doc_path.stem
        output_dir = self._create_output_structure(doc_name)

        if self.verbose:
            self.logger.info(f"Processing '{doc_path.name}' → {output_dir}")

        # 1) 轉換為 Markdown
        try:
            md_content, images = self._convert_to_markdown(
                doc_path,
                output_dir,
                extract_images=extract_images,
                style_map=style_map,
                image_alt_text=image_alt_text,
            )
        except Exception as e:
            raise DOCXProcessError(f"Conversion failed for {doc_path.name}: {e}") from e

        # 2) 保存 Markdown
        md_path = output_dir / f"{doc_name}.md"
        self._save_markdown(md_content, md_path)

        if self.verbose:
            self.logger.info(f"MD saved: {md_path}")
            if images:
                self.logger.info(f"Images extracted: {len(images)} files")

        # 3) 提取元數據（可選）
        metadata = self._extract_metadata(doc_path)

        # 4) 清理（可選）
        if not keep_output:
            self._safe_remove_dir(output_dir)
            output_dir = None
            md_path = None

        return MammothProcessResult(
            extract_dir=output_dir,
            md_content=md_content,
            md_path=md_path if md_path and md_path.exists() else None,
            images=images if images else None,
            metadata=metadata,
        )

    def _convert_to_markdown(
        self,
        doc_path: Path,
        output_dir: Path,
        *,
        extract_images: bool,
        style_map: Optional[str],
        image_alt_text: str,
    ) -> tuple[str, List[Path]]:
        """
        使用 Mammoth 將 Word 轉換為 Markdown。

        Returns
        -------
        tuple[str, List[Path]]
            (markdown 內容, 圖片路徑列表)
        """
        images_dir = output_dir / "images"
        images_dir.mkdir(exist_ok=True)
        extracted_images: List[Path] = []

        # 圖片轉換函數
        def convert_image(image):
            if not extract_images:
                return {}

            try:
                # 讀取圖片數據
                with image.open() as image_bytes:
                    image_data = image_bytes.read()

                # 生成唯一檔名（FIPS 兼容）
                image_hash = self._generate_image_hash(image_data)
                content_type = image.content_type or "image/png"
                ext = self._get_image_extension(content_type)
                image_filename = f"image_{image_hash}.{ext}"
                image_path = images_dir / image_filename

                # 保存圖片
                image_path.write_bytes(image_data)
                extracted_images.append(image_path)

                # 返回 Markdown 圖片連結，控制 alt text
                result = {"src": f"images/{image_filename}"}
                
                # 根據設定決定 alt text
                if image_alt_text is not None:
                    # 使用自定義文字（可為空字串）
                    result["alt"] = image_alt_text
                # 如果是 None，則不設置 alt，mammoth 會使用原始的 alt text
                
                return result
            except Exception as e:
                self.logger.warning(f"Failed to extract image: {e}")
                return {}

        # 構建 Mammoth 選項
        options = {
            "convert_image": mammoth.images.img_element(convert_image),
        }

        if style_map:
            options["style_map"] = style_map

        # 執行轉換 - 使用 HTML 格式以更好地支援表格
        with open(doc_path, "rb") as docx_file:
            result = mammoth.convert_to_html(docx_file, **options)

        html_content = result.value
        
        # 將 HTML 轉換為 Markdown（包含表格處理）
        md_content = self._html_to_markdown(html_content)

        # 記錄警告訊息
        if result.messages:
            for msg in result.messages:
                self.logger.warning(f"Mammoth: {msg}")

        return md_content, extracted_images

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
        table_store: Dict[str, str] = {}
        
        def stash_table(m: re.Match) -> str:
            key = f"__TABLE_BLOCK_{len(table_store)}__"
            table_store[key] = m.group(0)
            return key
        
        html = re.sub(
            r"<table\b[^>]*>.*?</table>",
            stash_table,
            html,
            flags=re.DOTALL | re.IGNORECASE,
        )
        
        # 處理圖片（必須在移除 HTML 標籤之前）
        html = self._convert_images_to_markdown(html)
        
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
        
        # 處理列表
        html = self._convert_lists_to_markdown(html)
        
        # 移除剩餘的 HTML 標籤
        html = re.sub(r'<[^>]+>', '', html)
        
        # 將表格內容放回 Markdown 中
        for key, table_html in table_store.items():
            html = html.replace(key, "\n\n" + table_html.strip() + "\n\n")
        
        # 清理多餘的空行
        html = re.sub(r'\n{3,}', '\n\n', html)
        
        return html.strip()

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
        # 處理無序列表項
        html = re.sub(r'<li[^>]*>(.*?)</li>', r'\n- \1', html, flags=re.DOTALL)
        
        # 移除 ul/ol 標籤
        html = re.sub(r'</?[uo]l[^>]*>', '', html)
        
        return html

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
        return mime_map.get(content_type.lower(), self.default_convert_image_format)

    def _save_markdown(self, content: str, output_path: Path) -> None:
        """保存 Markdown 內容到檔案"""
        output_path.write_text(content, encoding="utf-8")

    def _create_output_structure(self, doc_name: str) -> Path:
        """
        建立輸出目錄結構。

        Returns
        -------
        Path
            文檔專屬的輸出目錄。
        """
        output_dir = (self.output_root / doc_name).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir

    def _extract_metadata(self, doc_path: Path) -> Dict[str, Any]:
        """
        提取 Word 文檔的元數據（需要 python-docx 或其他庫）。
        目前返回基本資訊。

        Returns
        -------
        Dict[str, Any]
            包含文檔基本資訊的字典。
        """
        metadata = {
            "filename": doc_path.name,
            "file_size": doc_path.stat().st_size,
            "extension": doc_path.suffix,
        }

        # 可選：如果安裝了 python-docx，可以提取更多元數據
        try:
            from docx import Document
            doc = Document(doc_path)
            core_props = doc.core_properties
            metadata.update({
                "title": core_props.title or "",
                # "author": core_props.author or "",
                "created": str(core_props.created) if core_props.created else "",
                "modified": str(core_props.modified) if core_props.modified else "",
            })
        except ImportError:
            pass
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