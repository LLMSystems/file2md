
class ConverterError(Exception):
    """一般性轉換錯誤（可重試與否由上層決定）"""

class UnsupportedFormatError(ConverterError):
    """不支援該格式"""

