import requests

def test_convert_files():
    """測試 API 批量上傳檔案轉換"""
    url = "http://localhost:8000/convert"

    file_paths = [
        "/data/eddie.hsiao_data/file2md/test_files/test.docx",
        "/data/eddie.hsiao_data/file2md/test_files/test.txt",
    ]

    try:
        files = []
        handles = []
        for path in file_paths:
            f = open(path, "rb")
            handles.append(f)
            files.append(("files", (path.split("/")[-1], f)))

        response = requests.post(url, files=files)

        for f in handles:
            f.close()

        if response.status_code == 200:
            result = response.json()
            print("批量轉換成功!")
            print(f"狀態: {result['status']}")
            print(f"訊息: {result['message']}")

            for item in result['results']:
                print(f"\n檔案: {item['input_filename']}")
                print(f"格式: {item['format']}")
                print(f"Provider: {item['provider']}")
                print(f"輸出路徑: {item['output_path']}")
                if item.get('markdown_content'):
                    print(f"Markdown 內容預覽: {item['markdown_content'][:200]}...")
        else:
            print(f"轉換失敗，狀態碼: {response.status_code}")
            print(f"錯誤訊息: {response.text}")

    except Exception as e:
        print(f"發生錯誤: {str(e)}")


def test_convert_single_file():
    """測試 API 單檔上傳轉換"""
    url = "http://localhost:8000/convert-single"
    file_path = "test_files/image_test.html"

    try:
        with open(file_path, "rb") as f:
            response = requests.post(url, files={"file": (file_path.split("/")[-1], f)})

        if response.status_code == 200:
            result = response.json()
            print("單檔轉換成功!")
            print(f"檔案: {result['input_filename']}")
            print(f"格式: {result['format']}")
            print(f"Provider: {result['provider']}")
            print(f"輸出路徑: {result['output_path']}")
            if result.get('markdown_content'):
                print(f"Markdown 內容預覽: {result['markdown_content'][:200]}...")
        else:
            print(f"單檔轉換失敗，狀態碼: {response.status_code}")
            print(f"錯誤訊息: {response.text}")

    except Exception as e:
        print(f"單檔轉換發生錯誤: {str(e)}")


if __name__ == "__main__":
    # print("=== 測試批量上傳轉換 API ===")
    # test_convert_files()

    print("\n" + "=" * 50)

    print("=== 測試單檔上傳轉換 API ===")
    test_convert_single_file()
