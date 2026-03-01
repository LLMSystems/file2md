from pathlib import Path
from src.core.types import ProcessOptions
from src.providers.pptx.mineru.pptx_provider import PPTXMinerUProvider
from src.converters.pptx.pptx_converter import PPTXConverter

if __name__ == "__main__":
    # 初始化
    provider = PPTXMinerUProvider(base_url="http://localhost:8962/")
    
    converter = PPTXConverter(providers=[provider], prefer="mineru")
    
    # 測試檔案
    pptx_files = ["./pptx/test.pptx"]
    
    # 執行轉換
    result = converter.convert_files(
        input_paths=pptx_files,
        output_root=Path("./test_outputs/pptx")
    )
    
    # print(result)