from src.core.types import ProcessOptions
from src.providers.image.mineru.image_provider import ImageMinerUProvider
from src.converters.image.image_converter import ImageConverter

if __name__ == "__main__":
    provider = ImageMinerUProvider(base_url="http://10.204.245.170:8962/")
    images = ["./images/test.png"]
    converter = ImageConverter(providers=[provider], prefer="mineru")
    options = ProcessOptions(
        extra={
            'backend': 'pipeline',
            'parse_method': 'auto',
            'keep_unzipped': True,
            "return_images": True,
            "return_middle_json": True,
            "response_format_zip": True,
            'return_dict': True,
        }
    )

    result = converter.convert_files(images, output_root="./test_outputs/images", options=options)
    print(result)