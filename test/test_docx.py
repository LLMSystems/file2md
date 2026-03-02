from pathlib import Path

from src.converters import DOCXConverter
from src.core.types import ProcessOptions
from src.providers.docx.mammoth.docx_provider import DOCXMammothProvider
from src.providers.docx.mineru.docx_provider import DocxMinerUProvider

if __name__ == "__main__":
    # 初始化
    provider1 = DocxMinerUProvider(base_url="http://localhost:8962/")
    provider2 = DOCXMammothProvider()
    converter = DOCXConverter(providers=[provider1, provider2], prefer="mineru")
    
    # 測試檔案
    docx_files = ["./docs/test.docx"] # 支援多個檔案
    
    # 執行轉換
    result = converter.convert_files(
        input_paths=docx_files,
        output_root=Path("./test_outputs/docx"),
        options=ProcessOptions(
            extra={ # provider1
                'provider': 'mineru', # optional, 如果沒有，會使用 converter 的 prefer 預設值
                'backend': 'pipeline', 
                'parse_method': 'auto',
                'keep_unzipped': True,
                "draw_layout_bbox": True,
                "draw_span_bbox": True,    
                "return_images": True,
                "return_middle_json": True,
                "response_format_zip": True,
            }
            # extra={ # provider2
            #     "provider": "mammoth", # optional, 如果沒有，會使用 converter 的 prefer 預設值
            #     "extract_images": True,
            #     "keep_output": True,
            #     "default_convert_image_format": "png",
            #     "image_alt_text": ""
            # }
        )
    )
