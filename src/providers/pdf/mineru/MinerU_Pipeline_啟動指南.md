# MinerU Pipeline 啟動指南

> 適用對象：要在本機（或伺服器）安裝 MinerU、下載模型、設定 config，並啟動 `mineru-api` 的使用者。

*   測試環境：Linux / Python 3.11.5（建議 3.10 或 3.11）
*   模型來源：`modelscope`/`huggingface`（可切換），或本地檔案

***

## 1. 建立與啟用 Conda 環境（建議）
```bash
# 建立環境（Python 版本可依系統變更）
conda create -n mineru python=3.10 -c conda-forge -y
conda activate mineru

# 建議升級 pip 與常用工具
python -m pip install --upgrade pip setuptools wheel
```

***

## 2. 取得原始碼並安裝依賴

```bash
# 取得程式碼
git clone https://github.com/opendatalab/MinerU.git
cd MinerU

# 安裝 pipeline 與 api 所需依賴（
pip install -e .[pipeline]
pip install -e .[api]
```

***

## 3. 下載模型

MinerU 支援從 **modelscope** 或 **huggingface** 取得模型。先設定來源，再下載：

```bash
# 設定模型來源（兩擇一）
export MINERU_MODEL_SOURCE=modelscope   # 或：huggingface

# 下載模型（擇一）
mineru-models-download --model_type pipeline   # 僅 pipeline 所需
mineru-models-download --model_type vlm        # 僅視覺語言模型
mineru-models-download --model_type all        # 全部
```

> 下載位置將依工具預設快取路徑放置（常見於 \~/.cache 或 \~/.huggingface）。  
> 下載時間取決於網速與模型大小。

***

## 4. 建立與編輯設定檔 `mineru.json`

在你想放置設定檔的位置（例：`/data/max.dh.kuo_data/doc_parse_test/MinerU/mineru.json`）建立以下 JSON：

```json
{
  "bucket_info": {
    "bucket-name-1": ["ak", "sk", "endpoint"],
    "bucket-name-2": ["ak", "sk", "endpoint"]
  },
  "latex-delimiter-config": {
    "display": {"left": "$$", "right": "$$"},
    "inline": {"left": "$", "right": "$"}
  },
  "llm-aided-config": {
    "title_aided": {
      "api_key": "your_api_key",
      "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
      "model": "qwen3-next-80b-a3b-instruct",
      "enable_thinking": false,
      "enable": false
    }
  },
  "models-dir": {
    "pipeline": "/home/max.dh.kuo/.cache/huggingface/hub/models--opendatalab--PDF-Extract-Kit-1.0/snapshots/1d9a3cd772329d0f83d84638a789296863f940f9",
    "vlm": ""
  },
  "config_version": "1.3.1"
}
```

### 說明與建議
*   **`models-dir.pipeline`**：若你已經下載模型到本機，可將此路徑指向具體模型資料夾，並於下節改用 `local` 模式。
***

## 5. 指向設定檔與模型來源（本地模式）

若你已將模型下載到本機並希望走本地檔案，可將來源切換為 `local`：

```bash
# 指向 config 路徑（請依你的實際路徑調整）
export MINERU_TOOLS_CONFIG_JSON=/data/max.dh.kuo_data/doc_parse_test/MinerU/mineru.json

# 使用本地模型
export MINERU_MODEL_SOURCE=local
```

> **提醒**：當 `MINERU_MODEL_SOURCE=local` 時，`mineru.json` 中的 `"models-dir"` 必須正確指向可用模型的實際目錄。

***

## 6. 啟動 API 服務

```bash
mineru-api --host 0.0.0.0 --port 8962
```
***

## 10. 快速命令總覽

```bash
# 1) 建立環境
conda create -n mineru python=3.10 -c conda-forge -y
conda activate mineru
python -m pip install --upgrade pip setuptools wheel

# 2) 下載與安裝
git clone https://github.com/opendatalab/MinerU.git
cd MinerU
pip install -e .[pipeline] -i https://mirrors.aliyun.com/pypi/simple
pip install -e .[api] -i https://mirrors.aliyun.com/pypi/simple

# 3) 下載模型
export MINERU_MODEL_SOURCE=modelscope   # 或：huggingface
mineru-models-download --model_type pipeline

# 4) 產生並編輯設定檔（請依實際路徑放置 mineru.json）
#   內容見上文，請確認 models-dir 與 bucket/LLM 配置

# 5) 指向設定檔與模型來源（本地）
export MINERU_TOOLS_CONFIG_JSON=/data/max.dh.kuo_data/doc_parse_test/MinerU/mineru.json
export MINERU_MODEL_SOURCE=local

# 6) 啟動 API
mineru-api --host 0.0.0.0 --port 8962
```