"""
数据验证工具
"""

import re
from typing import Union


def validate_phone(phone: str) -> bool:
    if not phone:
        return False
    
    pattern = r'^\+\d{10,15}$'
    return bool(re.match(pattern, phone.strip()))


def validate_chat_id(chat_id: Union[str, int]) -> bool:
    try:
        int_id = int(chat_id)
        return abs(int_id) < 10**12
    except (ValueError, TypeError):
        return False


def validate_api_credentials(api_id: Union[str, int], api_hash: str) -> bool:
    try:
        int(api_id)
    except (ValueError, TypeError):
        return False
    
    if not api_hash or not isinstance(api_hash, str):
        return False
    
    return len(api_hash) == 32 and re.match(r'^[a-fA-F0-9]+$', api_hash)


def validate_cron_expression(cron: str) -> tuple[bool, str]:
    if not cron:
        return False, "Cron表达式不能为空"
    
    cron = cron.strip()
    parts = cron.split()
    
    if len(parts) != 5:
        return False, f"Cron表达式必须包含5个部分(分 时 日 月 周)，当前有{len(parts)}个部分"
    
    field_ranges = [
        (0, 59, "分钟"),
        (0, 23, "小时"),
        (1, 31, "日期"),
        (1, 12, "月份"),
        (0, 6, "星期")
    ]
    
    try:
        from apscheduler.triggers.cron import CronTrigger
        import pytz
        
        CronTrigger.from_crontab(cron, timezone=pytz.timezone('Asia/Shanghai'))
        return True, ""
        
    except Exception as e:
        error_msg = str(e)
        
        if "higher than the maximum value" in error_msg:
            if "38" in error_msg and "23" in error_msg:
                return False, "小时值错误：小时必须在0-23之间，您输入的38无效"
            elif "minute" in error_msg.lower():
                return False, "分钟值错误：分钟必须在0-59之间"
            elif "hour" in error_msg.lower():
                return False, "小时值错误：小时必须在0-23之间"
            elif "day" in error_msg.lower():
                return False, "日期值错误：日期必须在1-31之间"
            elif "month" in error_msg.lower():
                return False, "月份值错误：月份必须在1-12之间"
            else:
                return False, f"数值范围错误：{error_msg}"
        else:
            return False, f"Cron表达式格式错误：{error_msg}"


def get_cron_examples() -> list[dict]:
    return [
        {"expression": "0 9 * * *", "description": "每天上午9:00"},
        {"expression": "30 18 * * *", "description": "每天下午6:30"},
        {"expression": "0 */2 * * *", "description": "每2小时"},
        {"expression": "0 9 * * 1", "description": "每周一上午9:00"},
        {"expression": "0 9 1 * *", "description": "每月1日上午9:00"},
        {"expression": "0 0 * * *", "description": "每天午夜"},
        {"expression": "*/15 * * * *", "description": "每15分钟"},
    ]


def validate_email(email: str) -> bool:
    if not email:
        return False
    
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email.strip())) 