"""
日志工具
统一管理系统日志
"""

import logging
import sys
import threading
from pathlib import Path
from typing import Optional


def setup_logger(
    name: str = 'telegram_monitor',
    level: int = logging.INFO,
    log_file: Optional[str] = None,
    format_string: Optional[str] = None
) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    if logger.handlers:
        logger.handlers.clear()
    
    if format_string is None:
        format_string = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    formatter = logging.Formatter(format_string)
    
    console_handler = logging.StreamHandler(stream=sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger


def get_logger(name: str) -> logging.Logger:
    _ensure_initialized()
    
    logger = logging.getLogger(name)
    
    if not logger.handlers and not logger.parent.handlers:
        logger.setLevel(logging.INFO)
    
    return logger


def configure_telethon_logging():
    telethon_loggers = [
        'telethon.client.updates',
        'telethon.client.telegramclient',
        'telethon.network.mtprotosender',
        'telethon.network.connection',
        'telethon'
    ]
    
    uvicorn_loggers = [
        'uvicorn',
        'uvicorn.access',
        'uvicorn.error',
        'uvicorn.asgi'
    ]
    
    other_loggers = [
        'asyncio',
        'concurrent.futures',
        'multipart',
        'httpcore',
        'httpx'
    ]
    
    for logger_name in telethon_loggers:
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.WARNING)
    
    for logger_name in uvicorn_loggers:
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.ERROR)
    
    for logger_name in other_loggers:
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.WARNING)


def setup_root_logger():
    root_logger = logging.getLogger()
    
    if not root_logger.handlers:
        root_logger.setLevel(logging.INFO)
        
        console_handler = logging.StreamHandler(stream=sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)
        
        log_path = Path('logs/telegram_monitor.log')
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.FileHandler('logs/telegram_monitor.log', encoding='utf-8')
        file_handler.setLevel(logging.INFO)
        file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)


def init_logging():
    setup_root_logger()
    
    configure_telethon_logging()
    
    return setup_logger(
        name='telegram_monitor',
        level=logging.INFO,
        log_file='logs/telegram_monitor.log'
    )

_init_lock = threading.Lock()
_initialized = False

def _ensure_initialized():
    global _initialized
    if not _initialized:
        with _init_lock:
            if not _initialized:
                init_logging()
                _initialized = True

def get_default_logger():
    _ensure_initialized()
    return logging.getLogger('telegram_monitor')

default_logger = None 