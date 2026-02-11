from src.converters.pdf.pdf_converter import PDFMinerUClient

if __name__ == "__main__":
    client = PDFMinerUClient(base_url="http://10.204.245.170:8962/", output_root="./test_outputs")
    pdfs = ["./pdfs/demo2.pdf", "./pdfs/demo3.pdf"]
    result = client.process_pdfs(pdfs, draw_layout_bbox=True, draw_span_bbox_=True)