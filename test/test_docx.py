from pathlib import Path
from src.core.types import ProcessOptions
from src.providers.docx.mammoth.docx_provider import DOCXMammothProvider
from src.converters.docx.docx_converter import DOCXConverter

if __name__ == "__main__":
    # 初始化
    provider = DOCXMammothProvider()
    converter = DOCXConverter(providers=[provider], prefer="mammoth")
    
    # 測試檔案
    docx_files = ["./docs/test.docx"]
    

    
    # 執行轉換
    result = converter.convert_files(
        input_paths=docx_files,
        output_root=Path("./test_outputs/docx"),
        options=ProcessOptions(
            extra={
                "docx_provider": "mammoth",
                "extract_images": True,
                "keep_output": True,
                "default_convert_image_format": "png",
                "image_alt_text": ""
            }
        )
    )
    
    print(result)