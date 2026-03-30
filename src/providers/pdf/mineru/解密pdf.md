# qpdf-only Container

## 概述

本容器用於 **解密 PDF 檔案（移除 encryption flag）**，以便後續使用 `pypdf` 等工具進行處理。

## 適用情境

本工具專為以下情境設計：

- **FIPS mode 環境**：系統啟用 FIPS 模式導致加密演算法受限
- **MD5/FIPS 錯誤**：使用 `pypdf` 讀取 PDF 時出現 MD5 或 FIPS 相關錯誤
- PDF 檔案可正常開啟，但 `is_encrypted == True`

## 功能

- 支援 **無密碼 PDF**（最常見情況，PDF 檔案可正常開啟，但 `is_encrypted == True`）
- 支援 **有密碼 PDF**（需提供密碼）

---

## 快速開始

### 建立 Docker Image

使用專案中的 Dockerfile 建立映像檔：

```bash
cd src/providers/pdf/mineru/docker
docker build -t qpdf-only .
```

或使用 podman：

```bash
podman build -t qpdf-only .
```

### 解密 PDF 檔案

#### 無密碼 PDF (PDF 檔案可正常開啟，但 `is_encrypted == True`)

```bash
docker run --rm \
  -v "$PWD:/work" \
  qpdf-only \
  qpdf --decrypt input.pdf output.pdf
```

**參數說明：**
- `--rm`：容器執行完畢後自動刪除
- `-v "$PWD:/work"`：掛載當前目錄到容器的 `/work` 目錄
- `input.pdf`：原始加密的 PDF 檔案
- `output.pdf`：解密後的 PDF 檔案（未加密）

#### 有密碼 PDF

若 PDF 檔案受密碼保護，使用 `--password` 參數：

```bash
docker run --rm \
  -v "$PWD:/work" \
  qpdf-only \
  qpdf --decrypt --password=YOUR_PASSWORD input.pdf output.pdf
```

---

## 使用範例

### 範例 1：解密當前目錄的 PDF

```bash
docker run --rm \
  -v "$PWD:/work" \
  qpdf-only \
  qpdf --decrypt document.pdf document_decrypted.pdf
```

### 範例 2：解密子目錄中的 PDF

```bash
docker run --rm \
  -v "$PWD:/work" \
  qpdf-only \
  qpdf --decrypt pdfs/test6.pdf pdfs/output3.pdf
```