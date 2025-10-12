"""
文件监控器
实现文件类型监控策略
"""

import os
from typing import List

from models import MessageEvent, Account
from models.config import FileConfig
from .base_monitor import BaseMonitor


class FileMonitor(BaseMonitor):
    
    def __init__(self, config: FileConfig):
        super().__init__(config)
        self.file_config = config
    
    async def _match_condition(self, message_event: MessageEvent, account: Account) -> bool:
        message = message_event.message
        
        if not message.media or not message.media.has_media:
            return False
        
        media = message.media
        
        file_ext = None
        file_name = None
        
        if hasattr(media, 'file_extension') and media.file_extension:
            file_ext = media.file_extension
            file_name = getattr(media, 'file_name', 'unknown_file') or 'unknown_file'
            
        elif hasattr(media, 'file_name') and media.file_name:
            file_name = media.file_name
            _, file_ext = os.path.splitext(file_name)
            if not file_ext:
                return False
            file_ext = file_ext.lower()
                
        elif hasattr(media, 'media_type') and media.media_type:
            mime_type = getattr(media, 'mime_type', None)
            if mime_type:
                mime_to_ext = {
                    'application/pdf': '.pdf',
                    'application/zip': '.zip',
                    'application/x-rar-compressed': '.rar',
                    'application/x-7z-compressed': '.7z',
                    'text/plain': '.txt',
                    'application/msword': '.doc',
                    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': '.docx',
                    'application/vnd.ms-excel': '.xls',
                    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': '.xlsx',
                    'image/jpeg': '.jpg',
                    'image/png': '.png',
                    'video/mp4': '.mp4',
                    'audio/mpeg': '.mp3',
                    'audio/ogg': '.ogg',
                    'video/webm': '.webm'
                }
                file_ext = mime_to_ext.get(mime_type, '')
                if file_ext:
                    file_name = f"unknown_file{file_ext}"
                else:
                    return False
            else:
                return False
        else:
            return False
        
        if file_ext:
            file_ext = file_ext.lower()
            if not file_ext.startswith('.'):
                file_ext = '.' + file_ext
                
            config_ext = self.file_config.file_extension.lower()
            if not config_ext.startswith('.'):
                config_ext = '.' + config_ext
                
            match_result = file_ext == config_ext
            
            if match_result:
                file_size_mb = getattr(message.media, 'file_size_mb', 0) or (getattr(message.media, 'file_size', 0) / (1024 * 1024))
                self.logger.info(f"✅ [文件匹配] 文件: {file_name}, 扩展名: {file_ext}, 大小: {file_size_mb:.2f}MB")
            
            return match_result
        
        return False
    
    async def _execute_custom_actions(self, message_event: MessageEvent, account: Account) -> List[str]:
        actions_taken = []
        
        if self.file_config.save_folder:
            saved = await self._save_file(message_event, account)
            if saved:
                actions_taken.append("保存文件到本地")
        
        return actions_taken
    
    async def _save_file(self, message_event: MessageEvent, account: Account) -> bool:
        try:
            message = message_event.message
            
            if not message.media or not message.media.has_media:
                self.logger.error("消息不包含媒体文件")
                return False
            
            file_size_mb = getattr(message.media, 'file_size_mb', None)
            if file_size_mb is None:
                file_size_bytes = getattr(message.media, 'file_size', 0)
                if file_size_bytes > 0:
                    file_size_mb = file_size_bytes / (1024 * 1024)
                else:
                    self.logger.warning("无法获取文件大小信息")
                    file_size_mb = 0
            
            if not self.file_config.is_size_valid(file_size_mb):
                self.logger.info(f"文件大小 {file_size_mb:.2f} MB 不在设定范围内")
                return False
            
            os.makedirs(self.file_config.save_folder, exist_ok=True)
            
            client = account.client
            try:
                original_message = await client.get_messages(message.chat_id, ids=message.message_id)
                
                if original_message and original_message.media:
                    file_path = await original_message.download_media(file=self.file_config.save_folder)
                    
                    if file_path:
                        self.logger.info(f"文件已保存: {file_path}")
                        return True
                    else:
                        self.logger.error("文件下载失败")
                        return False
                else:
                    self.logger.error("无法获取原始消息对象或消息无媒体")
                    return False
                    
            except Exception as download_error:
                self.logger.error(f"下载文件时出错: {download_error}")
                return False
            
        except Exception as e:
            self.logger.error(f"保存文件失败: {e}")
            return False

    async def _add_monitor_specific_info(self, log_parts: List[str], message_event: MessageEvent, account: Account):
        message = message_event.message
        
        log_parts.append(f"📄 监控扩展名: \"{self.file_config.file_extension}\"")
        
        if self.file_config.min_size or self.file_config.max_size:
            size_info = []
            if self.file_config.min_size:
                size_info.append(f"最小{self.file_config.min_size}MB")
            if self.file_config.max_size:
                size_info.append(f"最大{self.file_config.max_size}MB")
            log_parts.append(f"📐 大小限制: {' - '.join(size_info)}")
        
        if message.media and message.media.has_media:
            if message.media.file_name:
                log_parts.append(f"📁 检测到文件: {message.media.file_name}")
            if message.media.file_size:
                file_size_mb = message.media.file_size / 1024 / 1024
                log_parts.append(f"📊 文件大小: {file_size_mb:.2f} MB")
        
        if self.file_config.save_folder:
            log_parts.append(f"💾 保存路径: {self.file_config.save_folder}")
    
    async def _get_monitor_type_info(self) -> str:
        return f"(文件:{self.file_config.file_extension})" 