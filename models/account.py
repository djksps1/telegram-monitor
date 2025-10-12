"""
账号相关数据模型
"""

from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from telethon import TelegramClient
import json


@dataclass
class AccountConfig:
    phone: str
    api_id: int
    api_hash: str
    proxy: Optional[tuple] = None
    session_name: str = ""
    
    def __post_init__(self):
        if not self.session_name:
            self.session_name = f"session_{self.phone.replace('+', '')}"


@dataclass
class Account:
    account_id: str
    config: AccountConfig
    client: Optional[TelegramClient] = None
    own_user_id: Optional[int] = None
    monitor_active: bool = False
    monitor_configs: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if not self.monitor_configs:
            self.monitor_configs = {
                "keyword_config": {},
                "file_extension_config": {},
                "all_messages_config": {},
                "button_keyword_config": {},
                "image_button_monitor": [],
                "scheduled_messages": [],
                "channel_in_group_config": []
            }
    
    def is_connected(self) -> bool:
        return self.client is not None and self.client.is_connected()
    
    def is_authorized(self) -> bool:
        return self.own_user_id is not None
    
    async def check_validity(self) -> tuple[bool, str]:
        if not self.client:
            return False, "disconnected"
        
        try:
            if not self.client.is_connected():
                return False, "disconnected"
            
            if not await self.client.is_user_authorized():
                return False, "unauthorized"
            
            try:
                me = await self.client.get_me()
                if me and me.id:
                    return True, "active"
                else:
                    return False, "invalid"
            except Exception as e:
                error_str = str(e).lower()
                if "user deactivated" in error_str or "banned" in error_str:
                    return False, "banned"
                elif "auth key unregistered" in error_str:
                    return False, "unauthorized"
                elif "session revoked" in error_str:
                    return False, "session_revoked"
                else:
                    return False, "error"
                    
        except Exception as e:
            return False, "error"
    
    def get_status_display(self, status: str) -> str:
        status_map = {
            "active": "在线",
            "disconnected": "离线", 
            "unauthorized": "未授权",
            "banned": "已封禁",
            "session_revoked": "会话失效",
            "invalid": "账号无效",
            "error": "连接错误",
            "connecting": "连接中"
        }
        return status_map.get(status, "未知")
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "account_id": self.account_id,
            "phone": self.config.phone,
            "api_id": self.config.api_id,
            "api_hash": self.config.api_hash,
            "proxy": self.config.proxy,
            "session_name": self.config.session_name,
            "own_user_id": self.own_user_id,
            "monitor_active": self.monitor_active,
            "monitor_configs": self.monitor_configs
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Account':
        config = AccountConfig(
            phone=data["phone"],
            api_id=data["api_id"],
            api_hash=data["api_hash"],
            proxy=data.get("proxy"),
            session_name=data.get("session_name", "")
        )
        
        account = cls(
            account_id=data["account_id"],
            config=config,
            own_user_id=data.get("own_user_id"),
            monitor_active=data.get("monitor_active", False),
            monitor_configs=data.get("monitor_configs", {})
        )
        
        return account
    
    def get_monitor_config(self, config_type: str) -> Dict[str, Any]:
        return self.monitor_configs.get(config_type, {})
    
    def update_monitor_config(self, config_type: str, config_data: Dict[str, Any]):
        self.monitor_configs[config_type] = config_data
    
    def add_monitor_config(self, config_type: str, key: str, config: Dict[str, Any]):
        if config_type not in self.monitor_configs:
            self.monitor_configs[config_type] = {}
        self.monitor_configs[config_type][key] = config
    
    def remove_monitor_config(self, config_type: str, key: str) -> bool:
        if config_type in self.monitor_configs and key in self.monitor_configs[config_type]:
            del self.monitor_configs[config_type][key]
            return True
        return False 