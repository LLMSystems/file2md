from src.converters import ExcelConverter
from src.core.types import ProcessOptions
from src.providers.excel.excel_provider import ExcelProvider

if __name__ == "__main__":
    provider = ExcelProvider()
    converter = ExcelConverter(providers=[provider], prefer="excel")
    result = converter.convert_files(
        input_paths=["./excel/Transactions.csv", "./excel/Monthly_Report.xlsx"],
        output_root="./test_outputs/excel2md",
        options=ProcessOptions(
            extra={
                'provider': 'excel' # optional, 如果沒有，會使用 converter 的 prefer 預設值
            }
        )
    )
            