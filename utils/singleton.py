"""
单例模式元类
确保类只有一个实例
"""

import threading
from typing import Dict, Any


class Singleton(type):
    
    _instances: Dict[type, Any] = {}
    _locks: Dict[type, threading.Lock] = {}
    _master_lock = threading.Lock()
    
    def __call__(cls, *args, **kwargs):
        if cls in cls._instances:
            return cls._instances[cls]
        
        if cls not in cls._locks:
            with cls._master_lock:
                if cls not in cls._locks:
                    cls._locks[cls] = threading.Lock()
        
        with cls._locks[cls]:
            if cls not in cls._instances:
                try:
                    cls._instances[cls] = super().__call__(*args, **kwargs)
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).error(f"创建单例实例失败 {cls.__name__}: {e}")
                    raise
        
        return cls._instances[cls]
    
    def clear_instance(cls):
        if cls in cls._instances:
            if cls not in cls._locks:
                with cls._master_lock:
                    if cls not in cls._locks:
                        cls._locks[cls] = threading.Lock()
            
            with cls._locks[cls]:
                if cls in cls._instances:
                    del cls._instances[cls] 