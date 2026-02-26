from pathlib import Path
from src.core.types import ProcessOptions
from src.providers.docx.mineru.docx_provider import DocxMinerUProvider
from src.converters.docx.docx_converter import DOCXConverter

if __name__ == "__main__":
    # 初始化
    provider = DocxMinerUProvider(base_url="http://10.204.245.170:8962/")
    
    # 測試檔案
    docx_files = ["./docs/test.docx"]
    

    
    # 執行轉換
    result = provider.convert_files(
        file_paths=docx_files,
        output_root=Path("./test_outputs/docx")
    )
    
    print(result)