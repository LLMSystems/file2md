import asyncio
import httpx
import base64
import os
import re

async def main():
    url = "http://localhost:8000/convert"
    data = {"keep_uploads": "false"}

    # 使用正確的 content-type，並確保檔案在上傳期間不會被關閉
    # 同時開啟兩個檔案：files/test.pdf 與 files/test2.pdf
    # 上傳時的原始檔名清單（用來對應 API 回傳的 results）
    uploaded_names = ["test.pdf", "test2.pdf"]
    with open("files/test.pdf", "rb") as f1, open("files/test2.pdf", "rb") as f2:
        files = [
            ("files", (uploaded_names[0], f1, "application/pdf")),
            ("files", (uploaded_names[1], f2, "application/pdf")),
        ]
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, files=files, data=data, timeout=120.0)
            print(resp.status_code)
            try:
                results = resp.json().get('results', [])
            except ValueError:
                print("Response is not JSON:\n", resp.text)
                return

            if not results:
                print("No results in response:\n", resp.text)
                return

            # 支援多個 results：為每個 result 寫出獨立的 md 與 images 資料夾
            for r_idx, res in enumerate(results):
                md_content = res.get('md_content')
                images = res.get('images')
                if not md_content:
                    print(f"No md_content in result {r_idx}:\n", res)
                    continue

                # 嘗試從 result 裡取回原始檔名欄位，否則用 uploaded_names 的對應索引
                name = None
                for key in ("filename", "name", "file", "orig_name", "original_filename"):
                    if isinstance(res.get(key), str) and res.get(key):
                        name = res.get(key)
                        break
                if not name:
                    # fallback to uploaded_names if available
                    if r_idx < len(uploaded_names):
                        name = uploaded_names[r_idx]
                    else:
                        name = f"result_{r_idx}"

                # 產生安全的目錄名稱（去除副檔名，移除非法字元）
                base, _ = os.path.splitext(os.path.basename(name))
                safe_base = re.sub(r"[^A-Za-z0-9._-]", "_", base)
                out_dir = os.path.join("outputs", safe_base)
                images_dir = os.path.join(out_dir, "images")

                # 寫出 images 與 md 到同一個資料夾
                if images:
                    os.makedirs(images_dir, exist_ok=True)
                    for idx, img in enumerate(images):
                        b64str = None
                        filename = None
                        if isinstance(img, dict):
                            for k in ("data", "b64", "base64", "content", "src"):
                                if k in img and img[k]:
                                    b64str = img[k]
                                    break
                            for k in ("name", "filename", "file", "path"):
                                if k in img and img[k]:
                                    filename = img[k]
                                    break
                        elif isinstance(img, str):
                            b64str = img

                        if isinstance(b64str, str) and b64str.startswith("data:") and "," in b64str:
                            b64str = b64str.split(",", 1)[1]

                        if not b64str:
                            print("Skipping image with no base64 content:", img)
                            continue

                        try:
                            img_bytes = base64.b64decode(b64str)
                        except Exception as e:
                            print("Failed to decode image:", e)
                            continue

                        if not filename:
                            # 保留原始檔名前綴並加入索引
                            filename = f"{safe_base}_{idx}.png"

                        out_img_path = os.path.join(images_dir, filename)
                        try:
                            with open(out_img_path, "wb") as wf:
                                wf.write(img_bytes)
                            print(f"Wrote image {out_img_path}")
                        except Exception as e:
                            print("Failed to write image file:", e)

                os.makedirs(out_dir, exist_ok=True)
                out_path = os.path.join(out_dir, f"{safe_base}.md")
                with open(out_path, "w", encoding="utf-8") as out:
                    out.write(md_content)

                print(f"Wrote markdown to {out_path}")

asyncio.run(main())