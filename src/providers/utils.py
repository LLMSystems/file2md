import subprocess
from pathlib import Path

def libreoffice_files_to_pdf(
    input_file: str,
    out_dir: str,
    soffice_path: str = "soffice",
    extra_args: list[str] | None = None,
    logger=None
) -> str:
    """
    用 LibreOffice headless 模式把 DOC/DOCX 轉成 PDF。

    :param input_file: 要轉的檔案路徑，可以是 .doc, .docx, .ppt, .pptx 等（LibreOffice 支援的格式）
    :param out_dir: 輸出 PDF 的資料夾
    :param soffice_path: soffice 的路徑（若已有 symlink，可改成 "soffice"）
    :param extra_args: 額外 soffice 參數，例如 ["--norestore"]
    :param logger: 可選的日誌記錄器
    :return: 轉出來的 PDF 路徑（字串）
    """
    input_path = Path(input_file).resolve()
    out_path = Path(out_dir).resolve()
    out_path.mkdir(parents=True, exist_ok=True)

    if not input_path.exists():
        raise FileNotFoundError(f"找不到輸入檔：{input_path}")

    cmd = [
        soffice_path,
        "--headless",
        "--convert-to", "pdf",               # 可改 "pdf:writer_pdf_Export"
        "--outdir", str(out_path),
        str(input_path)
    ]
    if extra_args:
        # 可附加參數（例如避免自動回復對話框）
        cmd[1:1] = extra_args

    # 執行並擷取輸出方便除錯
    result = subprocess.run(cmd, capture_output=True, text=True)
    if logger:
        logger.info(f"Command: {' '.join(cmd)}")
        logger.info(f"STDOUT:\n{result.stdout}")
        logger.info(f"STDERR:\n{result.stderr}")
    if result.returncode != 0:
        raise RuntimeError(
            "轉檔失敗\n"
            f"Command: {' '.join(cmd)}\n"
            f"STDOUT:\n{result.stdout}\n"
            f"STDERR:\n{result.stderr}\n"
        )

    # 推測輸出 PDF 路徑
    out_pdf = out_path / (input_path.stem + ".pdf")
    if not out_pdf.exists():
        # 某些情況（特殊副檔名/濾鏡）可能另有命名，回傳日誌以利排查
        raise FileNotFoundError(
            f"轉檔命令成功但未找到輸出 PDF：{out_pdf}\n"
            f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
    return str(out_pdf)
