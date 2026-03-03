from src.core.types import ProcessOptions
from src.providers.pdf.mineru.pdf_provider import PDFMinerUProvider
from src.converters.pdf.pdf_converter import PDFConverter

if __name__ == "__main__":
    provider = PDFMinerUProvider(base_url="http://10.204.245.170:8962/")
    pdfs = ["./pdfs/demo2.pdf"]
    converter = PDFConverter(providers=[provider], prefer="mineru")
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

    result = converter.convert_files(pdfs, output_root="./test_outputs", options=options)
    print(result)