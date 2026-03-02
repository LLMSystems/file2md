from src.converters import ImageConverter
from src.core.types import ProcessOptions
from src.providers.image.mineru.image_provider import ImageMinerUProvider

if __name__ == "__main__":
    provider = ImageMinerUProvider(base_url="http://10.204.245.170:8962/")
    images = ["./images/test.png"]
    converter = ImageConverter(providers=[provider], prefer="mineru")
    options = ProcessOptions(
        extra={
            'provider': 'mineru', # optional, 如果沒有，會使用 converter 的 prefer 預設值
            'backend': 'pipeline',
            'parse_method': 'auto',
            'keep_unzipped': True,
            "return_images": True,
            "return_middle_json": True,
            "response_format_zip": True,
        }
    )

    result = converter.convert_files(images, output_root="./test_outputs/images", options=options)
    print(result)