from src.converters.html.html_converter import HTMLConverter

if __name__ == "__main__":
    # 使用 HTMLConverter 轉換 HTML 文件
    # 啟用圖片提取功能，會自動處理相對路徑、絕對路徑和遠端圖片
    client = HTMLConverter(
        output_root="test_outputs/html_conversion",
        verbose=True,
        extract_images=True,           # 啟用圖片提取
        download_remote_images=True,   # 啟用遠端圖片下載
        keep_output=True
    )
    
    # 指定要轉換的 HTML 文件
    docs = ["./test_files/image_test.html"]
    
    # 使用 process_htmls (複數) 來處理多個文件
    print("=" * 70)
    print("開始轉換 HTML 文件...")
    print("=" * 70)
    
    results = client.process_htmls(docs)
    
