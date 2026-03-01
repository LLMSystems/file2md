from pathlib import Path

from src.converters.html.html_converter import HTMLConverter
from src.core.types import ProcessOptions
from src.providers.html.html_provider import HTMLBeautifulSoupProvider

if __name__ == "__main__": 
    provider = HTMLBeautifulSoupProvider()
    converter = HTMLConverter(providers=[provider], prefer="beautifulsoup")

    # 測試檔案
    html_files = ["./test_files/image_test.html"]

    # 執行轉換
    result = converter.convert_files(
        input_paths=html_files,
        output_root=Path("./test_outputs/html"),
        options=ProcessOptions(
            extra={
                'provider': 'beautifulsoup', # optional, 如果沒有，會使用 converter 的 prefer 預設值
                'extract_images': True,
                'keep_output': True,
                'convert_image_format': 'png',
                'download_remote_images': False,
            }
        )
    )

    print(result)
    
