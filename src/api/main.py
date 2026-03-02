from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse
from typing import List
import os
import tempfile
import shutil

from src.app.file2md import File2MD

app = FastAPI(title="File2MD API", version="1.0.0")

# 初始化 File2MD 客戶端
client = File2MD.from_env(default_path="configs/config.yaml")

def _extract_md_path(result) -> str | None:
    """從轉換結果中提取 md_path，統一處理物件或字典格式"""
    if hasattr(result, 'md_path'):
        return str(result.md_path)
    elif isinstance(result, dict):
        raw = (result.get('md_path') or result.get('output_path')
               or result.get('markdown_path') or result.get('path'))
        return str(raw) if raw is not None else None
    return str(result)

@app.post("/convert")
async def convert_files(files: List[UploadFile] = File(...)):
    """
    上傳檔案並轉換為 Markdown 格式。
    檔案會先儲存到暫存目錄，轉換完成後自動刪除。
    """
    if not files:
        raise HTTPException(status_code=400, detail="沒有上傳任何檔案")

    # 建立暫存目錄，存放所有上傳的檔案
    temp_dir = tempfile.mkdtemp()
    temp_paths: List[str] = []

    try:
        # 將上傳的檔案寫入暫存目錄
        for uploaded_file in files:
            temp_file_path = os.path.join(temp_dir, uploaded_file.filename)
            with open(temp_file_path, "wb") as buffer:
                shutil.copyfileobj(uploaded_file.file, buffer)
            temp_paths.append(temp_file_path)

        # 呼叫 File2MD 轉換
        conversion_results = client.convert(temp_paths)

        # 處理結果
        results = []
        for item in conversion_results:
            result_data = {
                "input_filename": os.path.basename(str(item.input_path)),
                "format": item.fmt,
                "provider": item.provider,
                "success": True
            }

            try:
                md_path = _extract_md_path(item.result)
                result_data["output_path"] = md_path

                if md_path and os.path.exists(md_path):
                    with open(md_path, 'r', encoding='utf-8') as f:
                        result_data["markdown_content"] = f.read()
                else:
                    result_data["markdown_content"] = "無法找到輸出檔案"

            except Exception as e:
                result_data["success"] = False
                result_data["output_path"] = None
                result_data["markdown_content"] = f"處理結果時發生錯誤: {str(e)}"

            results.append(result_data)

        return JSONResponse(content={
            "status": "success",
            "message": f"成功轉換 {len(results)} 個檔案",
            "results": results
        })

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"轉換失敗: {str(e)}")

    finally:
        # 無論成功或失敗，都清除暫存目錄
        shutil.rmtree(temp_dir, ignore_errors=True)

@app.post("/convert-single")
async def convert_single_file(file: UploadFile = File(...)):
    """
    上傳單個檔案並轉換為 Markdown 格式。
    檔案會先儲存到暫存目錄，轉換完成後自動刪除。
    """
    temp_dir = tempfile.mkdtemp()

    try:
        temp_file_path = os.path.join(temp_dir, file.filename)
        with open(temp_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        conversion_results = client.convert([temp_file_path])

        if not conversion_results:
            raise HTTPException(status_code=500, detail="轉換失敗，沒有返回結果")

        item = conversion_results[0]
        md_path = _extract_md_path(item.result)

        markdown_content = ""
        if md_path and os.path.exists(md_path):
            with open(md_path, 'r', encoding='utf-8') as f:
                markdown_content = f.read()

        return {
            "status": "success",
            "input_filename": file.filename,
            "format": item.fmt,
            "provider": item.provider,
            "output_path": md_path,
            "markdown_content": markdown_content
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"轉換失敗: {str(e)}")

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

@app.get("/")
async def root():
    """
    API 根路徑
    """
    return {"message": "File2MD API 服務運行中"}

@app.get("/health")
async def health_check():
    """
    健康檢查端點
    """
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)