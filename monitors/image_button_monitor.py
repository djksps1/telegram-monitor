"""
图片和按钮监控器
检测图片和按钮内容，发送给AI分析，根据AI结果点击按钮
"""
import asyncio
from typing import List, Optional, Dict, Any
from models import MessageEvent, Account
from models.config import ImageButtonConfig
from .base_monitor import BaseMonitor
from services import AIService
from utils.logger import get_logger

class ImageButtonMonitor(BaseMonitor):
    def __init__(self, config: ImageButtonConfig):
        super().__init__(config)
        self.image_button_config = config
        self.ai_service = AIService()
        self.logger = get_logger(__name__)
    
    def _read_image_base64(self, photo_path: str) -> str:
        import base64
        with open(photo_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")
    
    async def _match_condition(self, message_event: MessageEvent, account: Account) -> bool:
        message = message_event.message
        
        has_image = False
        has_buttons = bool(message.buttons)
        
        try:
            original_message = await account.client.get_messages(message.chat_id, ids=message.message_id)
            if original_message:
                if (original_message.photo or 
                    (original_message.document and 
                     original_message.document.mime_type and 
                     'image' in original_message.document.mime_type)):
                    has_image = True
                    self.logger.info(f"[图片检测] 原始消息检测到图片: photo={bool(original_message.photo)}, doc_image={bool(original_message.document and 'image' in (original_message.document.mime_type or ''))}")
            else:
                self.logger.warning(f"[图片检测] 无法获取原始消息对象")
        except Exception as e:
            self.logger.error(f"[图片检测] 检测图片时出错: {e}")
        
        if not has_image and not has_buttons:
            self.logger.debug(f"[图片按钮监控] 消息无图片无按钮，跳过")
            return False
        
        self.logger.info(f"[图片按钮监控] 检测到消息 - 图片: {has_image}, 按钮: {has_buttons}")
        
        if self.image_button_config.button_keywords:
            if has_buttons:
                button_texts = self._extract_button_texts(message.buttons)
                matched = any(
                    keyword.lower() in text.lower() 
                    for keyword in self.image_button_config.button_keywords
                    for text in button_texts
                )
                if not matched:
                    self.logger.info(f"[图片按钮监控] 按钮关键词不匹配，跳过")
                    return False
        
        return True
    
    async def _execute_custom_actions(self, message_event: MessageEvent, account: Account) -> List[str]:
        actions = []
        message = message_event.message
        
        try:
            if not message.buttons:
                self.logger.warning("[图片按钮监控] 消息没有按钮，跳过处理")
                return actions
            
            button_options = [button.text.strip() for row in message.buttons for button in row]
            if not button_options:
                self.logger.warning("[图片按钮监控] 无法提取按钮文本")
                return actions
            
            self.logger.info(f"[图片按钮监控] 提取到按钮选项: {button_options}")
            
            has_image = False
            image_base64 = None
            
            try:
                original_message = await account.client.get_messages(message.chat_id, ids=message.message_id)
                if original_message:
                    if (original_message.photo or 
                        (original_message.document and 
                         original_message.document.mime_type and 
                         'image' in original_message.document.mime_type)):
                        
                        has_image = True
                        self.logger.info(f"[图片+按钮] 检测到图片，准备下载")
                        
                        try:
                            photo_path = await original_message.download_media()
                            if photo_path:
                                import os
                                import shutil
                                import base64
                                
                                base, ext = os.path.splitext(photo_path)
                                if ext.lower() != '.jpg':
                                    new_image_path = base + '.jpg'
                                    shutil.move(photo_path, new_image_path)
                                    photo_path = new_image_path
                                
                                with open(photo_path, "rb") as image_file:
                                    image_base64 = base64.b64encode(image_file.read()).decode("utf-8")
                                
                                self.logger.info(f"[图片+按钮] ✅ 成功下载并编码图片: {photo_path}")
                                
                                if os.path.exists(photo_path):
                                    os.remove(photo_path)
                                    self.logger.debug(f"[图片+按钮] 已删除临时文件: {photo_path}")
                                    
                            else:
                                self.logger.error(f"[图片+按钮] ❌ 图片下载失败")
                        except Exception as download_error:
                            self.logger.error(f"[图片+按钮] ❌ 下载图片失败: {download_error}")
                    else:
                        self.logger.info(f"[图片+按钮] 原始消息无图片内容")
                else:
                    self.logger.error(f"[图片+按钮] ❌ 无法获取原始消息对象")
                    
            except Exception as get_message_error:
                self.logger.error(f"[图片+按钮] ❌ 获取原始消息失败: {get_message_error}")
            
            prompt_options = "\n".join(button_options)
            if has_image and image_base64:
                ai_prompt = f"{self.image_button_config.ai_prompt}\n按钮选项:\n{prompt_options}"
                
                ai_result = await self.ai_service.analyze_image_button(
                    image_base64=image_base64,
                    button_options=button_options,
                    custom_prompt=ai_prompt
                )
                self.logger.info(f"[图片+按钮] 使用图片+文本模式，AI回复: {ai_result}")
                
            else:
                ai_prompt = f"{self.image_button_config.ai_prompt}\n消息内容: {message.text}\n按钮选项:\n{prompt_options}"
                
                ai_result = await self.ai_service.analyze_button_choice(
                    message_text=message.text or "",
                    button_options=button_options,
                    custom_prompt=ai_prompt
                )
                self.logger.info(f"[图片+按钮] 使用纯文本模式，AI回复: {ai_result}")
            
            if ai_result:
                if isinstance(ai_result, str):
                    button_to_click = ai_result.strip()
                elif isinstance(ai_result, dict):
                    button_to_click = ai_result.get('button_to_click', '').strip()
                else:
                    button_to_click = ""
                
                if button_to_click:
                    success = await self._click_button_by_text(message_event, account, button_to_click, button_options)
                    if success:
                        actions.append(f"点击按钮: {button_to_click}")
                        self.logger.info(f"[图片+按钮] ✅ 成功点击按钮: {button_to_click}")
                    else:
                        self.logger.error(f"[图片+按钮] ❌ 点击按钮失败: {button_to_click}")
                else:
                    self.logger.warning(f"[图片+按钮] AI未返回有效的按钮选择")
            else:
                self.logger.error(f"[图片+按钮] AI分析失败，无返回结果")
            
        except Exception as e:
            self.logger.error(f"[图片按钮监控] 执行动作失败: {e}")
        
        return actions
    
    async def _build_analysis_content(self, message_event: MessageEvent, account: Account) -> Optional[Dict[str, Any]]:
        message = message_event.message
        
        chat_title = "未知聊天"
        try:
            if hasattr(account, 'client') and account.client:
                entity = await account.client.get_entity(message.chat_id)
                if hasattr(entity, 'title'):
                    chat_title = entity.title
                elif hasattr(entity, 'username'):
                    chat_title = f"@{entity.username}"
                elif hasattr(entity, 'first_name'):
                    chat_title = entity.first_name
                    if hasattr(entity, 'last_name') and entity.last_name:
                        chat_title += f" {entity.last_name}"
        except Exception as e:
            self.logger.warning(f"获取聊天信息失败: {e}")
        
        content = {
            'chat_title': chat_title,
            'sender': message.sender.full_name if message.sender else "未知发送者",
            'text': message.text or '',
            'has_image': False,
            'image_description': '',
            'buttons': []
        }
        
        if message.buttons:
            content['buttons'] = self._extract_button_info(message.buttons)
        
        if message.media and message.media.has_media:
            has_media_image = False
            if hasattr(message.media, 'photo') and message.media.photo:
                has_media_image = True
            elif (hasattr(message.media, 'document') and 
                  message.media.document and 
                  hasattr(message.media.document, 'mime_type') and
                  message.media.document.mime_type and
                  'image' in message.media.document.mime_type):
                has_media_image = True
            
            if has_media_image:
                content['has_image'] = True
                content['image_description'] = '检测到图片，准备下载分析'
                
                if self.image_button_config.download_images:
                    try:
                        original_message = await account.client.get_messages(message.chat_id, ids=message.message_id)
                        if original_message:
                            photo_path = await original_message.download_media()
                            if photo_path:
                                import os
                                import shutil
                                base, ext = os.path.splitext(photo_path)
                                if ext.lower() != '.jpg':
                                    new_image_path = base + '.jpg'
                                    shutil.move(photo_path, new_image_path)
                                    photo_path = new_image_path
                                
                                content['image_path'] = str(photo_path)
                                
                                import base64
                                try:
                                    with open(photo_path, "rb") as image_file:
                                        base64_image = base64.b64encode(image_file.read()).decode("utf-8")
                                    content['image_base64'] = base64_image
                                    self.logger.info(f"[图片处理] 成功下载并编码图片: {photo_path}")
                                    
                                    try:
                                        if os.path.exists(photo_path):
                                            os.remove(photo_path)
                                            self.logger.debug(f"[图片处理] 已删除临时图片文件: {photo_path}")
                                    except Exception as cleanup_error:
                                        self.logger.warning(f"[图片处理] 删除临时文件失败: {cleanup_error}")
                                        
                                except Exception as encode_error:
                                    self.logger.error(f"[图片处理] base64编码失败: {encode_error}")
                            else:
                                self.logger.error(f"[图片处理] 图片下载失败")
                        else:
                            self.logger.error(f"[图片处理] 无法获取原始消息对象")
                            
                    except Exception as e:
                        self.logger.error(f"[图片处理] 下载图片失败: {e}")
        
        return content
    
    def _extract_button_texts(self, buttons) -> List[str]:
        texts = []
        for row in buttons:
            for button in row:
                if hasattr(button, 'text'):
                    texts.append(button.text)
        return texts
    
    def _extract_button_info(self, buttons) -> List[Dict[str, str]]:
        button_info = []
        for row_idx, row in enumerate(buttons):
            for col_idx, button in enumerate(row):
                if hasattr(button, 'text'):
                    info = {
                        'text': button.text,
                        'row': row_idx,
                        'col': col_idx,
                        'type': 'inline' if hasattr(button, 'data') else 'keyboard'
                    }
                    button_info.append(info)
        return button_info
    
    async def _click_button(self, message_event: MessageEvent, account: Account, button_text: str) -> bool:
        try:
            message = message_event.message
            
            for row_idx, row in enumerate(message.buttons):
                for col_idx, button in enumerate(row):
                    if hasattr(button, 'text') and button.text == button_text:
                        await message.click(row_idx, col_idx)
                        return True
            
            self.logger.warning(f"未找到按钮: {button_text}")
            return False
            
        except Exception as e:
            self.logger.error(f"点击按钮失败: {e}")
            return False
    
    async def _click_button_by_text(self, message_event: MessageEvent, account: Account, ai_answer: str, button_options: List[str]) -> bool:
        try:
            message = message_event.message
            ai_answer_lower = ai_answer.lower().strip()
            
            best_match = None
            best_match_score = 0
            best_position = None
            
            for row_idx, row in enumerate(message.buttons):
                for col_idx, button in enumerate(row):
                    if hasattr(button, 'text'):
                        button_text = button.text.strip()
                        button_text_lower = button_text.lower()
                        
                        if button_text == ai_answer or button_text_lower == ai_answer_lower:
                            best_match = button_text
                            best_position = (row_idx, col_idx)
                            best_match_score = 100
                            break
                        
                        elif ai_answer_lower in button_text_lower or button_text_lower in ai_answer_lower:
                            score = min(len(ai_answer_lower), len(button_text_lower)) / max(len(ai_answer_lower), len(button_text_lower)) * 80
                            if score > best_match_score:
                                best_match = button_text
                                best_position = (row_idx, col_idx)
                                best_match_score = score
                
                if best_match_score >= 100:
                    break
            
            if best_match and best_position and best_match_score >= 50:
                row_idx, col_idx = best_position
                original_message = await account.client.get_messages(message.chat_id, ids=message.message_id)
                if original_message:
                    await original_message.click(row_idx, col_idx)
                    self.logger.info(f"[图片+按钮] 点击按钮成功: '{best_match}' (匹配度: {best_match_score:.1f}%)")
                    return True
                else:
                    self.logger.error(f"[图片+按钮] 无法获取原始消息对象进行点击")
            else:
                self.logger.warning(f"[图片+按钮] 未找到匹配的按钮。AI回复:'{ai_answer}', 可用按钮:{button_options}")
            
            return False
            
        except Exception as e:
            self.logger.error(f"[图片+按钮] 点击按钮失败: {e}")
            return False
    
    async def _send_reply(self, message_event: MessageEvent, account: Account, reply_text: str):
        try:
            message = message_event.message
            await account.client.send_message(
                message.chat_id,
                reply_text,
                reply_to=message.message_id
            )
            self.logger.info("[图片按钮监控] 发送回复成功")
        except Exception as e:
            self.logger.error(f"发送回复失败: {e}")
    
    async def _add_monitor_specific_info(self, log_parts: List[str], message_event: MessageEvent, account: Account):
        message = message_event.message
        
        log_parts.append(f"🤖 AI提示: \"{self.image_button_config.ai_prompt[:60]}{'...' if len(self.image_button_config.ai_prompt) > 60 else ''}\"")
        log_parts.append(f"📊 置信度阈值: {self.image_button_config.confidence_threshold}")
        
        if self.image_button_config.button_keywords:
            keywords_preview = ", ".join(self.image_button_config.button_keywords[:3])
            if len(self.image_button_config.button_keywords) > 3:
                keywords_preview += f" (+{len(self.image_button_config.button_keywords)-3}个)"
            log_parts.append(f"🔍 按钮关键词过滤: {keywords_preview}")
        
        has_image = bool(message.media) and hasattr(message.media, 'photo')
        has_buttons = bool(message.buttons)
        
        content_types = []
        if has_image:
            content_types.append("📷 图片")
        if has_buttons:
            content_types.append(f"🔘 按钮({len(message.button_texts)}个)")
        
        if content_types:
            log_parts.append(f"📄 检测内容: {' + '.join(content_types)}")
        
        config_options = []
        if self.image_button_config.download_images:
            config_options.append("💾 下载图片")
        if self.image_button_config.auto_reply:
            config_options.append("💬 自动回复")
        
        if config_options:
            log_parts.append(f"⚙️ 启用功能: {' | '.join(config_options)}")
    
    async def _get_monitor_type_info(self) -> str:
        prompt_preview = self.image_button_config.ai_prompt[:25] + "..." if len(self.image_button_config.ai_prompt) > 25 else self.image_button_config.ai_prompt
        return f"(图片+按钮:\"{prompt_preview}\")" 
