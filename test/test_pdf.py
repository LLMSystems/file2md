from src.core.types import ProcessOptions
from src.providers.pdf.mineru.pdf_provider import PDFMinerUProvider
from src.converters.pdf.pdf_converter import PDFConverter

if __name__ == "__main__":
    provider = PDFMinerUProvider(base_url="http://10.204.245.170:8962/", output_root="./test_outputs")
    pdfs = ["./pdfs/demo2.pdf"]
    converter = PDFConverter(providers=[provider], prefer="mineru")
    options = ProcessOptions(
        extra={
            'pdf_backend': 'pipeline',
            'pdf_parse_method': 'auto',
            'pdf_keep_unzipped': True,
            "pdf_provider": "mineru",   
            "draw_layout_bbox": True,
            "draw_span_bbox": True,    
            "return_images": True,
            "return_middle_json": True,
            "response_format_zip": True,
            'return_dict': True,
        }
    )

    result = converter.convert_files(pdfs, output_root="./test_outputs", options=options)
    print(result)