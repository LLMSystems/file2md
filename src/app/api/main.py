import asyncio
import json
import os
import re
import shutil
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional
from base64 import b64encode

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile

from src.app.api.schemas import ConvertResponse, ConvertItemResponse
from src.app.api.deps import (
    get_convert_limiter,
    get_file2md,
    get_max_batch,
    on_shutdown,
    on_startup,
)
from src.app.file2md import File2MD
from src.core.types import ArtifactType


def _safe_filename(name: str) -> str:
    """
    Keep it simple: strip path components + replace weird chars.
    """
    name = Path(name).name
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name)
    return name or "upload.bin"

async def _save_upload_to_disk(upload: UploadFile, dst_path: Path) -> None:
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    # Stream copy to avoid reading whole file into memory
    with dst_path.open("wb") as f:
        while True:
            chunk = await upload.read(1024 * 1024)  # 1MB
            if not chunk:
                break
            f.write(chunk)
    await upload.close()


def encode_image(image_path: str) -> str:
    """Encode image using base64 and return a base64 string."""
    with open(image_path, "rb") as f:
        return b64encode(f.read()).decode()

@asynccontextmanager
async def lifespan(app: FastAPI):
    await on_startup(app)
    try:
        yield
    finally:
        await on_shutdown(app)
 
app = FastAPI(title="file2md API", version="0.1.0", lifespan=lifespan)
        
@app.get("/health")
def health(request: Request):
    return {
        "status": "ok",
        "max_batch": request.app.state.max_batch,
    }
    
@app.post("/convert", response_model=ConvertResponse)
async def convert(
    files: List[UploadFile] = File(...),
    output_root: Optional[str] = Form(None),
    keep_uploads: bool = Form(True),
    file2md: File2MD = Depends(get_file2md),
    limiter: asyncio.Semaphore = Depends(get_convert_limiter),
    max_batch: int = Depends(get_max_batch),
)-> ConvertResponse:
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded.")
    if len(files) > max_batch:
        raise HTTPException(status_code=400, detail=f"Too many files. max_batch={max_batch}, got={len(files)}")
    
    job_id = uuid.uuid4().hex
    tmp_base = Path(os.getenv("FILE2MD_TMP_DIR", "/tmp/file2md_uploads"))
    job_tmp_dir = tmp_base / job_id
    job_tmp_dir.mkdir(parents=True, exist_ok=True)
    
    effective_output_root = output_root or str(Path(file2md.cfg.file2md.output_root) / "jobs" / job_id)

    
    saved_paths: List[str] = []
    original_names: List[str] = [] 
    try:
        # save uploaded files to disk
        for up in files:
            fn = _safe_filename(up.filename or "upload.bin")
            original_names.append(up.filename)
            dst = job_tmp_dir / fn
            await _save_upload_to_disk(up, dst)
            saved_paths.append(str(dst))
            
        async with limiter:
            try:
                results = await file2md.aconvert(
                    input_paths=saved_paths,
                    output_root=effective_output_root
                )
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Conversion failed: {str(e)}")
            
        out_items: List[ConvertItemResponse] = []
        saved_to_name = {sp: nm for sp, nm in zip(saved_paths, original_names)}
        
        for item in results:
            pr = item.result
            error = getattr(pr, "error", None)
            md_path = getattr(pr, "md_path", None)
            md_content = getattr(pr, "md_text", None)
            image_artifacts = [a for a in (pr.artifacts or []) if a.type == ArtifactType.IMAGE]

            images_b64 = [
                {
                    "name": a.name,
                    "path": f"images/{a.name}" if a.name else "image/png",
                    "data": encode_image(str(a.path)),  
                }
                for a in image_artifacts
            ]

            out_items.append(
                ConvertItemResponse(
                   filename=saved_to_name.get(item.input_path, Path(item.input_path).name),
                   fmt=item.fmt,
                   provider=item.provider,
                   md_content=md_content,
                   images = images_b64 if images_b64 else None,
                   error=str(error) if error else None,
                )
            )
        
        return ConvertResponse(job_id=job_id, results=out_items)
    finally:
        if not keep_uploads:
            try:
                shutil.rmtree(job_tmp_dir, ignore_errors=True)
            except Exception:
                pass
    
    