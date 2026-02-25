from pathlib import Path
from src.core.types import ProcessOptions
from src.providers.html.html_provider import HTMLBeautifulSoupProvider
from src.converters.html.html_converter import HTMLConverter

if __name__ == "__main__":
    ... 
    provider = HTMLBeautifulSoupProvider()
    converter = HTMLConverter(providers=[provider], prefer="beautifulsoup")

    # 測試檔案
    html_files = ["./test_files/image_test.html"]

    # 執行轉換
    result = converter.convert_files(
        input_paths=html_files,
        output_root=Path("./test_outputs/html"),
    )

    print(result)
    
