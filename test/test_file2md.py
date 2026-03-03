from src.app.file2md import File2MD

client = File2MD.from_env(default_path="configs/config.yaml")
res = client.convert(["test_files/image_test.html"])


for item in res:
    print(f"檔案: {item.input_path}")
    print(f"格式: {item.fmt}")
    print(f"使用 Provider: {item.provider}")
    print(f"輸出路徑: {item.result.md_path}")
