from pathlib import Path
from src.core.types import ProcessOptions
from src.providers.docx.docx_provider import DOCXMammothProvider
from src.converters.docx.docx_converter import DOCXConverter

if __name__ == "__main__":
    # 初始化
    provider = DOCXMammothProvider()
    converter = DOCXConverter(providers=[provider], prefer="mammoth")
    
    # 測試檔案
    docx_files = ["./test_files/test.docx"]
    

    
    # 執行轉換
    result = converter.convert_files(
        input_paths=docx_files,
        output_root=Path("./test_outputs/docx"),
    )
    
    print(result)