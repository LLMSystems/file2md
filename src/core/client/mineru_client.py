import os
import re
from html import unescape
from typing import Iterator, List, Sequence

from mineru_vl_utils import MinerUClient
from PIL import Image, UnidentifiedImageError
from tqdm import tqdm


class MinerUMarkdownExtractor:
    def __init__(
        self,
        server_url: str,
        backend: str = "http-client",
        images_dir: str = None,
    ):  
        try:
            self.client = MinerUClient(backend=backend, server_url=server_url)
        except Exception as e:
            self.client = None
            print(f"初始化 MinerUClient 失敗：{e}")
        self.images_dir = images_dir
        if self.images_dir:
            os.makedirs(self.images_dir, exist_ok=True)

    @staticmethod
    def _sanitize_text(text: str) -> str:
        t = unescape(text or "")
        t = re.sub(r"\s+\n", "\n", t).strip()
        return t

    @staticmethod
    def _safe_open_image(path: str) -> Image.Image:
        try:
            img = Image.open(path)
            img.load()
            return img
        except FileNotFoundError:
            raise FileNotFoundError(f"找不到影像檔案：{path}")
        except UnidentifiedImageError:
            raise ValueError(f"無法辨識的影像格式：{path}")
        
    def blocks_to_markdown(self, blocks, original_image_path=None, images_dir=None):
        md_content = []
        images_dir = images_dir or self.images_dir
        if original_image_path:
            orig_img = Image.open(original_image_path)
            W, H = orig_img.size
        else:
            orig_img = None

        def sanitize_text(t):
            t = unescape(t)
            t = re.sub(r'\s+\n', '\n', t).strip()
            return t

        for b in blocks:
            btype = b.get("type", "")
            content = b.get("content", "")
            bbox = b.get("bbox")  # [xmin, ymin, xmax, ymax] in [0,1]
            if btype == "title":
                text = sanitize_text(content) if content else ""
                if text:
                    md_content.append(f"# {text}\n")
            elif btype == "text":
                text = sanitize_text(content) if content else ""
                if text:
                    md_content.append(text + "\n")
            elif btype == "equation":
                eq = content.strip() if content else ""
                if eq:
                    md_content.append(f"$$\n{eq}\n$$\n")
            elif btype == "table":
                html = content if content else ""
                if html:
                    md_content.append(html + "\n")
            elif btype == "image" and orig_img is not None and bbox:
                xmin, ymin, xmax, ymax = bbox
                left, top, right, bottom = int(xmin * W), int(ymin * H), int(xmax * W), int(ymax * H)
                crop = orig_img.crop((left, top, right, bottom))
                idx = len([name for name in os.listdir(images_dir) if name.endswith(".png")]) + 1
                img_name = f"img_{idx:03d}.png"
                img_path = os.path.join(images_dir, img_name)
                crop.save(img_path)
                rel = os.path.relpath(img_path, ".")
                md_content.append(f"![image]({rel})\n")
            else:
                text = sanitize_text(content) if content else ""
                if text:
                    md_content.append(text + "\n")

        return "\n".join(md_content)
    
    def batch_image_to_md_last_step(self, image_paths: Sequence[str]) -> List[str]:
        images: List[Image.Image] = []
        try:
            for p in image_paths:
                images.append(self._safe_open_image(p))

            results = self.client.batch_content_extract(
                images=images,
                types="table",
            )
            return results
        finally:
            for img in images:
                try:
                    img.close()
                except Exception:
                    pass

    def batch_image_to_md_two_step(self, image_paths: Sequence[str], images_dir=None) -> List[str]:
        images: List[Image.Image] = []
        try:
            for p in image_paths:
                images.append(self._safe_open_image(p))

            results = self.client.concurrent_two_step_extract(images=images)
            md_list: List[str] = []
            for blocks, path in zip(results, image_paths):
                md = self.blocks_to_markdown(blocks, original_image_path=path, images_dir=images_dir)
                md_list.append(md)
            return md_list
        finally:
            for img in images:
                try:
                    img.close()
                except Exception:
                    pass
    
    @staticmethod
    def _iter_batches(seq: Sequence[str], size: int) -> Iterator[Sequence[str]]:
        for i in range(0, len(seq), size):
            yield seq[i : i + size]

    def process_in_batches(
        self,
        image_paths: Sequence[str],
        batch_size: int = 5,
        mode: str = "two_step", # or "last_step"
        images_dir: str = None
    ):
        
        if not isinstance(batch_size, int) or batch_size <= 0:
            raise ValueError("batch_size 必須是正整數")

        mode_norm = mode.strip().lower()
        if mode_norm not in ("two_step", "last_step"):
            raise ValueError("mode 只能是 'two_step' 或 'last_step'")
        
        def _runner() -> Iterator[List[str]]:
            for batch in self._iter_batches(image_paths, batch_size):
                if mode_norm == "two_step":
                    yield self.batch_image_to_md_two_step(batch, images_dir=images_dir)
                else:
                    yield self.batch_image_to_md_last_step(batch)
        
        flattened: List[str] = []
        for part in tqdm(_runner(), total=(len(image_paths) + batch_size - 1) // batch_size):
            flattened.extend(part)
        return flattened

if __name__ == "__main__":
    extractor = MinerUMarkdownExtractor(
        server_url="http://10.204.245.170:8963",
        backend="http-client",
    )

    image_paths = [
       "./outputs2/2025-07-31-UBS-WDC-Western_Digital/images/2a3f09d3f0ebe8abbc4f1bb44de6517631d94420c3594be857da9e60160f4061.jpg",
       "./outputs2/2025-07-31-UBS-WDC-Western_Digital/images/b185ea38fd7210f137396d43a59743adcd75af431c886a5049e94e246e7a30a7.jpg" ,
       "./outputs2/2025-07-31-UBS-WDC-Western_Digital/images/82350d0e937ab84ae6afc13091bdfde023b2edab7ef2f271bba53b64140b3066.jpg"
    ]


    results = extractor.process_in_batches(image_paths, batch_size=2, mode="last_step")
    for md in results:
        print(md)
        print("-" * 80)
            
            