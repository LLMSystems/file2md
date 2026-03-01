from src.providers.txt.txt_provider import TxtProvider
from src.converters import TXTConverter

if __name__ == "__main__":
    provider = TxtProvider()
    converter = TXTConverter(providers=[provider])
    result = converter.convert_files(
        input_paths=["txt/test.txt"],
        output_root="./test_outputs/txt2md",
        options=None
    )
    print(result)