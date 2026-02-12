
class ConverterError(Exception):
    """一般性轉換錯誤（可重試與否由上層決定）"""

class UnsupportedFormatError(ConverterError):
    """不支援該格式"""

class TransientError(ConverterError):
    """暫時性錯誤（如網路、服務端 5xx，可考慮重試）"""

class FatalError(ConverterError):
    """無法恢復的錯誤（格式毀損等）"""
