#!/usr/bin/env bash
set -e

########################################
# file2md API startup script
########################################

# -------- 基本路徑設定 --------
# 專案根目錄（假設這個 sh 放在專案根）
PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_ROOT"

# -------- file2md 設定 --------
export FILE2MD_CONFIG="${FILE2MD_CONFIG:-$PROJECT_ROOT/configs/config.yaml}"

# 一次 API request 最多幾個檔案
export FILE2MD_MAX_BATCH="${FILE2MD_MAX_BATCH:-20}"

# 同一個 worker 同時跑幾個 convert()
export FILE2MD_MAX_CONVERT_INFLIGHT="${FILE2MD_MAX_CONVERT_INFLIGHT:-2}"

# 上傳暫存資料夾
export FILE2MD_TMP_DIR="${FILE2MD_TMP_DIR:-/tmp/file2md_uploads}"

# -------- MinerU HTTP client 設定 --------
export MINERU_RETRY="${MINERU_RETRY:-3}"
export MINERU_BACKOFF="${MINERU_BACKOFF:-0.5}"
export MINERU_POOL_CONN="${MINERU_POOL_CONN:-32}"
export MINERU_POOL_MAXSIZE="${MINERU_POOL_MAXSIZE:-32}"

# -------- API Server 設定 --------
export API_HOST="${API_HOST:-0.0.0.0}"
export API_PORT="${API_PORT:-8000}"
export API_WORKERS="${API_WORKERS:-1}"

# -------- Python module path --------
export PYTHONPATH="$PROJECT_ROOT"

# -------- 顯示設定（方便確認） --------
echo "========================================"
echo "Starting file2md API"
echo "PROJECT_ROOT=$PROJECT_ROOT"
echo "FILE2MD_CONFIG=$FILE2MD_CONFIG"
echo "FILE2MD_MAX_BATCH=$FILE2MD_MAX_BATCH"
echo "FILE2MD_MAX_CONVERT_INFLIGHT=$FILE2MD_MAX_CONVERT_INFLIGHT"
echo "FILE2MD_TMP_DIR=$FILE2MD_TMP_DIR"
echo "MINERU_POOL_MAXSIZE=$MINERU_POOL_MAXSIZE"
echo "API_HOST=$API_HOST"
echo "API_PORT=$API_PORT"
echo "API_WORKERS=$API_WORKERS"
echo "========================================"

# -------- 啟動 FastAPI --------
exec uvicorn src.app.api.main:app \
  --host "$API_HOST" \
  --port "$API_PORT" \
  --workers "$API_WORKERS"