from src.converters.docx.doc_converter import DOCConverter


if __name__ == "__main__":
    # 使用空字串來移除所有 alt text
    client = DOCConverter(output_root="./test_outputs", image_alt_text="")
    docs = ["./test.docx"]
    result = client.process_docs(docs)