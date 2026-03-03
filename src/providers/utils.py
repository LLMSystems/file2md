import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


def _file_uri(p: Path) -> str:
    # 轉成 file:// URI（跨平台）
    # Windows 例如 C:\tmp\lo-1 會變成 file:///C:/tmp/lo-1
    return p.resolve().as_uri()


def libreoffice_files_to_pdf(
    input_file: str,
    out_dir: str,
    soffice_path: str = "soffice",
    extra_args: list[str] | None = None,
    logger=None,
    timeout: int = 60,
    retries: int = 2,
    user_installation: str | None = None,
) -> str:
    """
    用 LibreOffice headless 模式把 DOC/DOCX 轉成 PDF。

    :param input_file: 要轉的檔案路徑，可以是 .doc, .docx, .ppt, .pptx 等（LibreOffice 支援的格式）
    :param out_dir: 輸出 PDF 的資料夾
    :param soffice_path: soffice 的路徑（若已有 symlink，可改成 "soffice"）
    :param extra_args: 額外 soffice 參數，例如 ["--norestore"]
    :param logger: 可選的日誌記錄器
    :param timeout: 每次轉檔的超時秒數
    :param retries: 失敗後重試次數
    :param user_installation: 可選的 LibreOffice user installation 目錄，避免多次轉檔衝突（例如 "./lo_user_{uuid}"）
    :return: 轉出來的 PDF 路徑（字串）
    """
    input_path = Path(input_file).resolve()
    out_path = Path(out_dir).resolve()
    out_path.mkdir(parents=True, exist_ok=True)

    if not input_path.exists():
        raise FileNotFoundError(f"找不到輸入檔：{input_path}")
    
    base_cmd = [soffice_path]

    if extra_args:
        base_cmd += extra_args

    base_cmd += [
        "--headless",
        "--convert-to", "pdf",
        "--outdir", str(out_path),
    ]

    if user_installation:
        base_cmd.insert(1, f"-env:UserInstallation={user_installation}")

    last_err = None
    for attempt in range(retries + 1):
        cmd = base_cmd + [str(input_path)]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
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

            out_pdf = out_path / (input_path.stem + ".pdf")
            if not out_pdf.exists():
                raise FileNotFoundError(
                    f"轉檔命令成功但未找到輸出 PDF：{out_pdf}\n"
                    f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
                )
            return str(out_pdf)
        except Exception as e:
            last_err = e
            if logger:
                logger.error(f"轉檔嘗試 {attempt + 1} 失敗: {e}")
        
    raise RuntimeError(f"所有轉檔嘗試失敗，共 {retries + 1} 次。最後錯誤: {last_err}")


def batch_convert_to_pdf(
    files: list[str],
    out_dir: str,
    soffice_path: str = "soffice",
    max_workers: int = 4,
    extra_args: list[str] | None = None,
    logger=None,
    timeout: int | None = 600,
    retries: int = 1,
) -> tuple[list[str], list[tuple[str, Exception]]]:
    """
    並行轉檔。回傳 (成功 PDF 清單, 失敗 (檔案, 例外) 清單)
    """
    out_dir_path = Path(out_dir)
    out_dir_path.mkdir(parents=True, exist_ok=True)

    results: list[tuple[int, str | Exception]] = []

    def worker(index: int, input_file: str) -> tuple[int, str | Exception]:
        # 每個工作使用獨立的 UserInstallation
        tmp_profile = Path(tempfile.mkdtemp(prefix="lo-profile-"))
        user_installation = _file_uri(tmp_profile)
        try:
            pdf_path = libreoffice_files_to_pdf(
                input_file=input_file,
                out_dir=out_dir,
                soffice_path=soffice_path,
                extra_args=extra_args,
                logger=logger,
                timeout=timeout,
                retries=retries,
                user_installation=user_installation,
            )
            return index, pdf_path
        except Exception as e:
            return index, e
        finally:
            # 清理 profile 目錄，避免殘留
            try:
                shutil.rmtree(tmp_profile, ignore_errors=True)
            except Exception:
                if logger:
                    logger.warning(f"清理暫存 profile 失敗：{tmp_profile}")

    # 限制並行數
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        future_map = {ex.submit(worker, i, f): i for i, f in enumerate(files)}
        for fut in as_completed(future_map):
            index = future_map[fut]
            try:
                results.append(fut.result())
            except Exception as e:
                results.append((index, e))
                if logger:
                    logger.error(f"[{files[index]}] 轉檔失敗：{e}")

    # 根據索引排序結果
    results.sort(key=lambda x: x[0])

    # 分離成功和失敗的結果
    successes = [res for _, res in results if not isinstance(res, Exception)]
    failures = [(files[idx], res) for idx, res in results if isinstance(res, Exception)]

    return successes, failures