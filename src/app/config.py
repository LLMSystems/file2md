# src/app/config.py
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

import yaml
from pydantic import (BaseModel, Field, ValidationError, field_validator,
                      model_validator)


def _coerce_dict(v: Any) -> Dict[str, Any]:
    """Allow YAML null / empty to become {}."""
    if v is None:
        return {}
    if isinstance(v, dict):
        return v
    raise TypeError(f"Expected a dict (or null), got {type(v)}")


def merge_extra(*extras: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Shallow merge dicts from left -> right; later overrides earlier.
    """
    out: Dict[str, Any] = {}
    for d in extras:
        if not d:
            continue
        if not isinstance(d, dict):
            raise TypeError(f"extra must be dict, got {type(d)}")
        out.update(d)
    return out


class ProviderExtraConfig(BaseModel):
    extra: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("extra", mode="before")
    @classmethod
    def _v_extra(cls, v: Any) -> Dict[str, Any]:
        return _coerce_dict(v)


class ConverterConfig(BaseModel):
    # B-only: providers mapping
    providers: Dict[str, ProviderExtraConfig] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _preparse(cls, data: Any) -> Any:
        """
        YAML:
          {"mammoth": {"extra": {...}}, "mineru": {"extra": {...}}}

        Convert to:
          {"providers": {"mammoth": {"extra": {...}}, "mineru": {"extra": {...}}}}
        """
        if data is None:
            return {"providers": {}}
        if isinstance(data, Mapping):
            return {"providers": dict(data)}
        return data


class MinerUConfig(BaseModel):
    base_url: str = "http://localhost:8962/"
    timeout_sec: int = 60
    retry: int = 2
    default_extra: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("default_extra", mode="before")
    @classmethod
    def _v_default_extra(cls, v: Any) -> Dict[str, Any]:
        return _coerce_dict(v)


class ProvidersConfig(BaseModel):
    mineru: MinerUConfig = Field(default_factory=MinerUConfig)


class File2MDConfigRoot(BaseModel):
    output_root: str = "./output"
    prefer: Dict[str, str] = Field(default_factory=dict)
    default_extra: Dict[str, Any] = Field(default_factory=dict)

class LLMConfig(BaseModel):
    default_model: Optional[str] = None
    default_params: Dict[str, Any] = Field(default_factory=dict)
    default_config_path: Optional[str] = None

class File2MDConfig(BaseModel):
    file2md: File2MDConfigRoot = Field(default_factory=File2MDConfigRoot)
    
    llm: LLMConfig = Field(default_factory=LLMConfig)
    
    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)

    # converters[fmt] -> ConverterConfig(providers={...})
    converters: Dict[str, ConverterConfig] = Field(default_factory=dict)

    # metadata
    config_path: Optional[str] = None


# ---------------------------
# ENV names
# ---------------------------

ENV_CONFIG_PATH = "FILE2MD_CONFIG"

ENV_MINERU_BASE_URL = "MINERU_BASE_URL"
ENV_MINERU_TIMEOUT = "MINERU_TIMEOUT_SEC"
ENV_MINERU_RETRY = "MINERU_RETRY"


# ---------------------------
# Loading
# ---------------------------

def _read_yaml(path: str) -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    if not p.is_file():
        raise FileNotFoundError(f"Config path is not a file: {path}")
    with p.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError("YAML root must be a mapping/dict.")
    return data


def _apply_env_overrides(cfg_dict: Dict[str, Any]) -> Dict[str, Any]:
    # MinerU overrides
    mineru_base_url = os.getenv(ENV_MINERU_BASE_URL)
    mineru_timeout = os.getenv(ENV_MINERU_TIMEOUT)
    mineru_retry = os.getenv(ENV_MINERU_RETRY)

    providers = cfg_dict.setdefault("providers", {})
    if not isinstance(providers, dict):
        providers = cfg_dict["providers"] = {}

    mineru = providers.setdefault("mineru", {})
    if not isinstance(mineru, dict):
        mineru = providers["mineru"] = {}

    if mineru_base_url:
        mineru["base_url"] = mineru_base_url
    if mineru_timeout:
        try:
            mineru["timeout_sec"] = int(mineru_timeout)
        except ValueError:
            raise ValueError(f"{ENV_MINERU_TIMEOUT} must be int, got {mineru_timeout}")
    if mineru_retry:
        try:
            mineru["retry"] = int(mineru_retry)
        except ValueError:
            raise ValueError(f"{ENV_MINERU_RETRY} must be int, got {mineru_retry}")

    return cfg_dict

 
def load_config_from_yaml(path: str) -> File2MDConfig:
    raw = _read_yaml(path)
    selected = _apply_env_overrides(raw)

    try:
        cfg = File2MDConfig.model_validate(selected)
    except ValidationError as e:
        raise ValidationError.from_exception_data(
            title="File2MDConfig validation error",
            line_errors=e.errors(),
        )

    cfg.config_path = str(path)
    return cfg


def load_config_from_env(default_path: Optional[str] = None) -> File2MDConfig:
    path = os.getenv(ENV_CONFIG_PATH) or default_path
    if not path:
        raise ValueError(
            f"No config path specified. Set {ENV_CONFIG_PATH} or provide default_path."
        )
    return load_config_from_yaml(path)


# ---------------------------
# Builders / Accessors
# ---------------------------

def resolve_prefer_provider(cfg: File2MDConfig, fmt: str) -> Optional[str]:
    fmt = fmt.lower().strip()
    return cfg.file2md.prefer.get(fmt)


def list_providers_for_format(cfg: File2MDConfig, fmt: str) -> list[str]:
    fmt = fmt.lower().strip()
    conv = cfg.converters.get(fmt)
    if not conv:
        return []
    return list(conv.providers.keys())


def build_process_extra(
    cfg: File2MDConfig,
    fmt: str,
    provider: Optional[str] = None,
    runtime_extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Merge:
      file2md.default_extra
      + providers.<provider>.default_extra (if any)
      + converters.<fmt>.<provider>.extra
      + runtime_extra
    """
    fmt = fmt.lower().strip()
    provider = (provider or resolve_prefer_provider(cfg, fmt) or "").lower().strip()

    if not provider:
        # No provider resolved; leave only global + runtime
        return merge_extra(cfg.file2md.default_extra, runtime_extra)

    # provider-default extra
    provider_default_extra: Dict[str, Any] = {}
    if provider == "mineru":
        provider_default_extra = cfg.providers.mineru.default_extra

    # format-provider extra
    format_provider_extra: Dict[str, Any] = {}
    conv = cfg.converters.get(fmt)
    if conv and provider in conv.providers:
        format_provider_extra = conv.providers[provider].extra

    return merge_extra(
        cfg.file2md.default_extra,
        provider_default_extra,
        format_provider_extra,
        runtime_extra,
    )


def resolve_output_root(cfg: File2MDConfig, runtime_output_root: Optional[str] = None) -> str:
    return runtime_output_root or cfg.file2md.output_root


def get_mineru_base_url(cfg: File2MDConfig) -> str:
    return cfg.providers.mineru.base_url


def get_mineru_timeout(cfg: File2MDConfig) -> int:
    return cfg.providers.mineru.timeout_sec


def get_mineru_retry(cfg: File2MDConfig) -> int:
    return cfg.providers.mineru.retry

def get_llm_default_model(cfg: File2MDConfig) -> Optional[str]:
    if cfg.llm.default_model:
        return cfg.llm.default_model
    return None

def get_llm_default_params(cfg: File2MDConfig) -> Dict[str, Any]:
    if cfg.llm.default_params:
        return cfg.llm.default_params
    return {}

def get_llm_config_path(cfg: File2MDConfig) -> Optional[str]:
    if cfg.llm.default_config_path:
        return cfg.llm.default_config_path
    return None