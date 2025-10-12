"""
配置管理工具
处理环境变量和配置文件的读取
"""

import os
from pathlib import Path
from typing import Optional, Dict, Any
from dotenv import load_dotenv
from utils.logger import get_logger

logger = get_logger(__name__)

def load_env_config():
    env_file = Path('.env')
    if env_file.exists():
        load_dotenv(env_file)
        logger.info("已加载 .env 配置文件")
    else:
        logger.warning("未找到 .env 配置文件，请复制 config.example.env 为 .env 并配置")

load_env_config()

class Config:
    
    TG_API_ID: Optional[int] = None
    TG_API_HASH: Optional[str] = None
    
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-3.5-turbo"
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    
    EMAIL_SMTP_SERVER: str = "smtp.gmail.com"
    EMAIL_SMTP_PORT: int = 587
    EMAIL_USERNAME: Optional[str] = None
    EMAIL_PASSWORD: Optional[str] = None
    EMAIL_FROM: Optional[str] = None
    EMAIL_TO: Optional[str] = None
    
    WEB_HOST: str = "127.0.0.1"
    WEB_PORT: int = 8000
    WEB_DEBUG: bool = False
    WEB_USERNAME: str = "admin"
    WEB_PASSWORD: str = "admin123"
    
    DATA_DIR: str = "./data"
    LOGS_DIR: str = "./logs"
    DOWNLOADS_DIR: str = "./downloads"
    
    
    def __init__(self):
        self.load_from_env()
        self.create_directories()
        self.validate_config()
    
    def load_from_env(self):
        if os.getenv('TG_API_ID'):
            try:
                self.TG_API_ID = int(os.getenv('TG_API_ID'))
            except ValueError:
                logger.error("TG_API_ID 必须是数字")
        
        self.TG_API_HASH = os.getenv('TG_API_HASH')
        
        self.OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
        self.OPENAI_MODEL = os.getenv('OPENAI_MODEL', self.OPENAI_MODEL)
        self.OPENAI_BASE_URL = os.getenv('OPENAI_BASE_URL', self.OPENAI_BASE_URL)
        
        self.EMAIL_SMTP_SERVER = os.getenv('EMAIL_SMTP_SERVER', self.EMAIL_SMTP_SERVER)
        self.EMAIL_SMTP_PORT = int(os.getenv('EMAIL_SMTP_PORT', self.EMAIL_SMTP_PORT))
        self.EMAIL_USERNAME = os.getenv('EMAIL_USERNAME')
        self.EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD')
        self.EMAIL_FROM = os.getenv('EMAIL_FROM')
        self.EMAIL_TO = os.getenv('EMAIL_TO')
        
        self.WEB_HOST = os.getenv('WEB_HOST', self.WEB_HOST)
        self.WEB_PORT = int(os.getenv('WEB_PORT', self.WEB_PORT))
        self.WEB_DEBUG = os.getenv('WEB_DEBUG', 'false').lower() == 'true'
        self.WEB_USERNAME = os.getenv('WEB_USERNAME', self.WEB_USERNAME)
        self.WEB_PASSWORD = os.getenv('WEB_PASSWORD', self.WEB_PASSWORD)
        
        self.DATA_DIR = os.getenv('DATA_DIR', self.DATA_DIR)
        self.LOGS_DIR = os.getenv('LOGS_DIR', self.LOGS_DIR)
        self.DOWNLOADS_DIR = os.getenv('DOWNLOADS_DIR', self.DOWNLOADS_DIR)
        
    
    def create_directories(self):
        directories = [self.DATA_DIR, self.LOGS_DIR, self.DOWNLOADS_DIR]
        for directory in directories:
            Path(directory).mkdir(parents=True, exist_ok=True)
    
    def validate_config(self):
        warnings = []
        errors = []
        
        if not self.TG_API_ID:
            errors.append("TG_API_ID 未配置，请在 .env 文件中设置")
        
        if not self.TG_API_HASH:
            errors.append("TG_API_HASH 未配置，请在 .env 文件中设置")
        
        if not self.OPENAI_API_KEY:
            warnings.append("OPENAI_API_KEY 未配置，AI监控功能将不可用")
        
        if not self.EMAIL_USERNAME or not self.EMAIL_PASSWORD:
            warnings.append("邮件配置未完整，邮件通知功能将不可用")
        
        for warning in warnings:
            logger.warning(warning)
        
        for error in errors:
            logger.error(error)
        
        if errors:
            logger.error("配置验证失败，请检查 .env 文件")
            return False
        
        logger.info("配置验证通过")
        return True
    
    def is_telegram_configured(self) -> bool:
        return self.TG_API_ID is not None and self.TG_API_HASH is not None
    
    def is_openai_configured(self) -> bool:
        return self.OPENAI_API_KEY is not None
    
    def is_email_configured(self) -> bool:
        return all([
            self.EMAIL_USERNAME,
            self.EMAIL_PASSWORD,
            self.EMAIL_FROM
        ])
    
    def get_status(self) -> Dict[str, Any]:
        return {
            "telegram_configured": self.is_telegram_configured(),
            "openai_configured": self.is_openai_configured(),
            "email_configured": self.is_email_configured(),
            "web_host": self.WEB_HOST,
            "web_port": self.WEB_PORT,
            "data_dir": self.DATA_DIR,
            "logs_dir": self.LOGS_DIR,
            "downloads_dir": self.DOWNLOADS_DIR
        }

config = Config() 