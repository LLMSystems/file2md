
# LibreOffice 26.2（deb 安裝版）

# DOC / DOCX / PPT / PPTX 轉 PDF 說明書

（Ubuntu / Debian / APT 環境）

***

## 1. 解壓 LibreOffice 安裝包

```bash
tar -xzf LibreOffice_26.2.0_Linux_x86-64_deb.tar.gz
cd LibreOffice_*/DEBS
```

***

## 2. 安裝所有 LibreOffice .deb 套件

```bash
apt update
apt-get update
apt install -y ./*.deb
```

***

## 3. 尋找 soffice 可執行檔路徑

```bash
ls -l /opt | sed -n '1,120p'
ls -l /opt/libreoffice*/program/soffice* || true
find /opt -maxdepth 3 -type f -name soffice 2>/dev/null
```

通常會位於：

    /opt/libreoffice26.2/program/soffice

***

## 4. 測試 LibreOffice 是否能啟動

```bash
/opt/libreoffice26.2/program/soffice --version
```

若缺少系統函式庫會報錯，需依以下步驟補齊。

***

## 5. 補齊 LibreOffice Headless 需要的動態函式庫

### 必要 X11 / GL / 字型相關函式庫

```bash
apt install -y \
  libxinerama1 libxrender1 libxext6 libsm6 libx11-6 libgl1 \
  fontconfig libxau6 libxdmcp6 libxcb1
```

### NSS（提供 libssl3.so）

```bash
apt install -y libnss3
```

### dbus（提供 libdbus-1.so.3）

```bash
apt install -y libdbus-1-3
```

### 其他常見函式庫（建議一次補上）

```bash
apt install -y \
  libxinerama1 libxrender1 libxext6 libsm6 libx11-6 libgl1 \
  libxau6 libxdmcp6 libxcb1 fontconfig libfreetype6 \
  libnss3 libnspr4 libdbus-1-3 libcups2 zlib1g
```

### CUPS（提供 libcups.so.2）

```bash
apt install -y libcups2
apt install -y libcairo2
```

補完後再次驗證：

```bash
/opt/libreoffice26.2/program/soffice --version
```

若能正確顯示版本號，即成功。

***

## 6. 轉檔：DOCX → PDF

```bash
/opt/libreoffice26.2/program/soffice \
  --headless \
  --convert-to pdf \
  --outdir /app/doc_parse_test/data/ \
  /app/doc_parse_test/docs/test.docx
```

輸出結果：

    /app/doc_parse_test/data/test.pdf

***

## 7. 轉檔：PPT / PPTX → PDF

```bash
/opt/libreoffice26.2/program/soffice \
  --headless \
  --convert-to pdf \
  --outdir /app/doc_parse_test/data/ \
  /app/doc_parse_test/docs/test.pptx
```

***

## （可選）8. 安裝中文字型（避免 PDF 中文亂碼或換字）

```bash
apt install -y fonts-noto-cjk
fc-cache -fv
```

如文件使用微軟字型（例如 MS JhengHei、MS YaHei），需將 `.ttf` / `.ttc` 放入：

    /usr/share/fonts/truetype/custom/

並執行：

```bash
fc-cache -fv
```

## （可選）9. 建立 symlink
```bash
ln -s /opt/libreoffice26.2/program/soffice /usr/local/bin/soffice
```
