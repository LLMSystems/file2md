from pathlib import Path
from src.core.types import ProcessOptions
from src.providers.pptx.mineru.pptx_provider import PPTXMinerUProvider
from src.converters import PPTXConverter

if __name__ == "__main__":
    # 初始化
    provider = PPTXMinerUProvider(base_url="http://localhost:8962/")
    
    converter = PPTXConverter(providers=[provider], prefer="mineru")
    
    options = ProcessOptions(
        extra={
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
    )
    
    # 測試檔案
    pptx_files = ["./pptx/test.pptx"]
    
    # 執行轉換
    result = converter.convert_files(
        input_paths=pptx_files,
        output_root=Path("./test_outputs/pptx"),
        options=options
    )