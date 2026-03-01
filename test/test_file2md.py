from src.app.file2md import File2MD

client = File2MD.from_env(default_path="configs/config.yaml")
res = client.convert(["./docs/test.docx", "./docs/test2.docx"])