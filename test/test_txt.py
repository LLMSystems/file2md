from src.providers.txt.txt_provider import TxtProvider
from src.converters import TXTConverter
from src.core.types import ProcessOptions


if __name__ == "__main__":
    provider = TxtProvider()
    converter = TXTConverter(providers=[provider], prefer='txt')
    
    options = ProcessOptions(
        extra={
            'provider': 'txt', # optional, 如果沒有，會使用 converter 的 prefer 預設值
            'wrap_in_codeblock': False,
            'smart_format': True,
            'normalize_line_endings': True,
            'strip_trailing_spaces': True,
        }
    )
    
    result = converter.convert_files(
        input_paths=["txt/test.txt"],
        output_root="./test_outputs/txt2md",
        options=options
    )
