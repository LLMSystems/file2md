import asyncio
import os

from fastapi import Request

from src.app.config import (get_llm_config_path, get_llm_default_model,
                            get_mineru_retry, load_config_from_env)
from src.app.file2md import File2MD
from src.app.http import build_llm_chat, build_session

DEFAULT_MAX_BATCH = int(os.getenv("FILE2MD_MAX_BATCH", "5"))
DEFAULT_MAX_CONVERT_INFLIGHT = int(os.getenv("FILE2MD_MAX_CONVERT_INFLIGHT", "2"))
DEFAULT_CONFIG_PATH = os.getenv("FILE2MD_CONFIG", "configs/config.yaml")
CFG = load_config_from_env(DEFAULT_CONFIG_PATH)

async def on_startup(app) -> None:
    # Build shared HTTP session and LLM chat client
    mineru_session = build_session(
        retries=get_mineru_retry(CFG)
    )
    
    llm_client = build_llm_chat(
        model=get_llm_default_model(CFG),
        config_path=get_llm_config_path(CFG)
    )
    
    file2md = File2MD.from_env(
        default_path=DEFAULT_CONFIG_PATH,
        mineru_session=mineru_session,
        llm_client=llm_client
    )
    
    # Store in app state for access in endpoints
    app.state.file2md = file2md
    app.state.mineru_session = mineru_session
    app.state.llm_client = llm_client
    app.state.convert_limiter = asyncio.Semaphore(DEFAULT_MAX_CONVERT_INFLIGHT)
    app.state.max_batch = DEFAULT_MAX_BATCH
    
async def on_shutdown(app) -> None:
    mineru_session = getattr(app.state, "mineru_session", None)
    if mineru_session is not None:
        try:
            mineru_session.close()
        except Exception:
            pass
        
def get_file2md(request: Request) -> File2MD:
    return request.app.state.file2md

def get_convert_limiter(request: Request) -> asyncio.Semaphore:
    return request.app.state.convert_limiter

def get_max_batch(request: Request) -> int:
    return int(request.app.state.max_batch)