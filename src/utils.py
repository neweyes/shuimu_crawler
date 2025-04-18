import re
import json
from pathlib import Path
from typing import Any, Dict

def get_safe_filename(filename: str) -> str:
    """
    将字符串转换为安全的文件名
    
    Args:
        filename: 原始文件名
        
    Returns:
        安全的文件名
    """
    # 移除或替换不安全的字符
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    # 移除前后的空格和点
    filename = filename.strip('. ')
    # 如果文件名为空，使用默认名称
    if not filename:
        filename = 'untitled'
    return filename

def save_json_file(data: Dict[str, Any], filepath: Path) -> None:
    """
    保存数据到JSON文件
    
    Args:
        data: 要保存的数据
        filepath: 文件路径
    """
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)