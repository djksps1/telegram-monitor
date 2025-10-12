"""
增强转发服务
当直接转发失败时，下载文件到本地再重新发送
"""

import os
import asyncio
import shutil
from pathlib import Path
from typing import Optional, List, Dict, Any
from telethon import TelegramClient
from telethon.errors import FloodWaitError, ChatForwardsRestrictedError, MediaEmptyError

from models import TelegramMessage, Account
from utils.singleton import Singleton
from utils.logger import get_logger


class EnhancedForwardService(metaclass=Singleton):
    
    def __init__(self):
        self.logger = get_logger(__name__)
        self.temp_downloads: Dict[str, str] = {}
        
    async def forward_message_enhanced(
        self,
        message: TelegramMessage,
        account: Account,
        target_ids: List[int],
        max_download_size_mb: Optional[float] = None,
        download_folder: str = "downloads"
    ) -> Dict[int, bool]:
        results = {}
        client = account.client
        
        for target_id in target_ids:
            try:
                success = await self._try_direct_forward(client, message, target_id)
                if success:
                    results[target_id] = True
                    self.logger.info(f"直接转发成功到 {target_id}")
                    continue
                
                success = await self._download_and_resend(
                    client, message, target_id, max_download_size_mb, download_folder
                )
                results[target_id] = success
                
            except Exception as e:
                self.logger.error(f"转发到 {target_id} 时出错: {e}")
                results[target_id] = False
        
        return results
    
    async def _try_direct_forward(
        self, 
        client: TelegramClient, 
        message: TelegramMessage, 
        target_id: int
    ) -> bool:
        try:
            await client.forward_messages(target_id, [message.message_id], message.chat_id)
            return True
            
        except (ChatForwardsRestrictedError, MediaEmptyError) as e:
            self.logger.info(f"直接转发到 {target_id} 受限制: {e}")
            return False
        except FloodWaitError as e:
            self.logger.warning(f"转发频率限制，等待 {e.seconds} 秒")
            await asyncio.sleep(e.seconds)
            return False
        except Exception as e:
            self.logger.error(f"直接转发失败: {e}")
            return False
    
    async def _download_and_resend(
        self,
        client: TelegramClient,
        message: TelegramMessage,
        target_id: int,
        max_download_size_mb: Optional[float],
        download_folder: str
    ) -> bool:
        try:
            if message.media and message.media.file_size_mb:
                if max_download_size_mb and message.media.file_size_mb > max_download_size_mb:
                    self.logger.warning(
                        f"文件大小 {message.media.file_size_mb:.2f}MB 超过限制 {max_download_size_mb}MB"
                    )
                    return False
            
            download_path = Path(download_folder)
            download_path.mkdir(parents=True, exist_ok=True)
            
            if message.media and message.media.has_media:
                return await self._download_and_send_media(client, message, target_id, download_path)
            else:
                return await self._send_text_message(client, message, target_id)
                
        except Exception as e:
            self.logger.error(f"下载重发失败: {e}")
            return False
    
    async def _download_and_send_media(
        self,
        client: TelegramClient,
        message: TelegramMessage,
        target_id: int,
        download_path: Path
    ) -> bool:
        downloaded_path = None
        try:
            original_message = await client.get_messages(message.chat_id, ids=message.message_id)
            
            if not original_message or not original_message.media:
                return False
            
            file_name = message.media.file_name or f"file_{message.message_id}"
            file_path = download_path / file_name
            
            self.logger.info(f"开始下载文件: {file_name}")
            downloaded_path = await original_message.download_media(file=str(file_path))
            
            if not downloaded_path:
                self.logger.error("文件下载失败")
                return False
            
            caption = message.text if message.text else None
            await client.send_file(target_id, downloaded_path, caption=caption)
            
            self.logger.info(f"文件重发成功到 {target_id}: {file_name}")
            return True
            
        except Exception as e:
            self.logger.error(f"下载媒体文件失败: {e}")
            return False
        finally:
            if downloaded_path:
                await self._cleanup_file(downloaded_path)
    
    async def _send_text_message(
        self,
        client: TelegramClient,
        message: TelegramMessage,
        target_id: int
    ) -> bool:
        try:
            if message.text:
                await client.send_message(target_id, message.text)
                self.logger.info(f"文本消息重发成功到 {target_id}")
                return True
            return False
            
        except Exception as e:
            self.logger.error(f"发送文本消息失败: {e}")
            return False
    
    async def _cleanup_file(self, file_path: str):
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                self.logger.debug(f"已清理临时文件: {file_path}")
        except Exception as e:
            self.logger.warning(f"清理临时文件失败: {e}")
    
    async def cleanup_all_temp_files(self):
        for file_path in self.temp_downloads.values():
            await self._cleanup_file(file_path)
        self.temp_downloads.clear()
        self.logger.info("已清理所有临时文件")
    
    def get_download_statistics(self) -> Dict[str, Any]:
        return {
            "temp_files_count": len(self.temp_downloads),
            "temp_files": list(self.temp_downloads.keys())
        } 