"""
监控器工厂 - 应用工厂模式
根据配置类型创建相应的监控器实例
"""

from typing import Dict, Type, Optional, Any

from models.config import (
    BaseMonitorConfig, KeywordConfig, FileConfig, 
    ButtonConfig, AllMessagesConfig, AIMonitorConfig, ImageButtonConfig
)
from .base_monitor import BaseMonitor
from .keyword_monitor import KeywordMonitor
from .ai_monitor import AIMonitor


class MonitorFactory:
    
    def __init__(self):
        self._monitor_registry: Dict[Type[BaseMonitorConfig], Type[BaseMonitor]] = {}
        self._register_default_monitors()
    
    def _register_default_monitors(self):
        self._monitor_registry[KeywordConfig] = KeywordMonitor
        self._monitor_registry[AIMonitorConfig] = AIMonitor
        
        from .file_monitor import FileMonitor
        from .button_monitor import ButtonMonitor
        from .all_messages_monitor import AllMessagesMonitor
        from .image_button_monitor import ImageButtonMonitor
        
        self._monitor_registry[FileConfig] = FileMonitor
        self._monitor_registry[ButtonConfig] = ButtonMonitor
        self._monitor_registry[AllMessagesConfig] = AllMessagesMonitor
        self._monitor_registry[ImageButtonConfig] = ImageButtonMonitor
    
    def register_monitor(self, config_type: Type[BaseMonitorConfig], monitor_class: Type[BaseMonitor]):
        self._monitor_registry[config_type] = monitor_class
    
    def create_monitor(self, config: BaseMonitorConfig) -> Optional[BaseMonitor]:
        config_type = type(config)
        monitor_class = self._monitor_registry.get(config_type)
        
        if monitor_class is None:
            return None
        
        try:
            return monitor_class(config)
        except Exception:
            return None


monitor_factory = MonitorFactory()
 