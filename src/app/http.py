# src/app/http.py
from __future__ import annotations

from typing import FrozenSet, Optional, Tuple

import requests
from requests.adapters import HTTPAdapter, Retry

from src.core.client.llm_client import AsyncLLMChat


def build_retry(
    *,
    retries: int = 3,
    backoff_factor: float = 0.5,
    status_forcelist: Tuple[int, ...] = (429, 500, 502, 503, 504),
    allowed_methods: FrozenSet[str] = frozenset(["POST", "GET"]),
    raise_on_status: bool = False,
) -> Retry:
    """
    Build a urllib3 Retry object.

    Notes:
    - Keep allowed_methods consistent with your MinerU usage.
    - raise_on_status=False means responses with 4xx/5xx won't raise automatically;
      your code should handle status codes.
    """
    return Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
        allowed_methods=allowed_methods,
        raise_on_status=raise_on_status,
    )


def build_session(
    *,
    retries: int = 3,
    backoff_factor: float = 0.5,
    status_forcelist: Tuple[int, ...] = (429, 500, 502, 503, 504),
    allowed_methods: FrozenSet[str] = frozenset(["POST", "GET"]),
    raise_on_status: bool = False,
    pool_connections: int = 32,
    pool_maxsize: int = 32,
) -> requests.Session:
    """
    Build a requests.Session with Retry + HTTPAdapter and a configurable pool.

    Recommended for API usage:
    - Create ONE session per worker process (FastAPI startup).
    - Reuse it across requests (inject into providers).
    """
    session = requests.Session()

    retry = build_retry(
        retries=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
        allowed_methods=allowed_methods,
        raise_on_status=raise_on_status,
    )

    adapter = HTTPAdapter(
        max_retries=retry,
        pool_connections=pool_connections,
        pool_maxsize=pool_maxsize,
    )
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


class ManagedSession:
    """
    Small helper for lifecycle management.
    Useful if you want a clear close() call on shutdown.

    Example:
        ms = ManagedSession(build_session(...))
        session = ms.session
        ...
        ms.close()
    """

    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or build_session()

    def close(self) -> None:
        try:
            self.session.close()
        except Exception:
            pass
        
def build_llm_chat(
    *,
    model: str,
    config_path: str,
)-> AsyncLLMChat:
    """
    Factory for AsyncLLMChat instances.
    You can expand this to support different LLM clients based on config.

    Example:
        llm_client = build_llm_chat(model="gpt-3.5-turbo", config_path="./configs/gpt35.json")
    """
    return AsyncLLMChat(model=model, config_path=config_path)