from pathlib import Path
from src.core.types import ProcessOptions
from src.providers.docx.mineru.docx_provider import DocxMinerUProvider
from src.providers.docx.mammoth.docx_provider import DOCXMammothProvider
from src.converters.docx.docx_converter import DOCXConverter

if __name__ == "__main__":
    # 初始化
    provider1 = DocxMinerUProvider(base_url="http://localhost:8962/")
    provider2 = DOCXMammothProvider()
    
    converter = DOCXConverter(providers=[provider1, provider2], prefer="mammoth")
    # 測試檔案
    docx_files = ["./docs/test.docx"]
    

    
    # 執行轉換
    result = converter.convert_files(
        input_paths=docx_files,
        output_root=Path("./test_outputs/docx")
    )
    
    # print(result)