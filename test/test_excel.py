from src.providers.excel.excel_provider import ExcelProvider
from src.converters import ExcelConverter

if __name__ == "__main__":
    provider = ExcelProvider()
    converter = ExcelConverter(providers=[provider])
    result = converter.convert_files(
        input_paths=["./excel/Transactions.csv", "./excel/Monthly_Report.csv"],
        output_root="./test_outputs/excel2md",
        options=None
    )
    print(result)