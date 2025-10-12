"""
全量消息监控器
"""

from typing import List
from models import MessageEvent, Account
from models.config import AllMessagesConfig
from .base_monitor import BaseMonitor


class AllMessagesMonitor(BaseMonitor):
    
    def __init__(self, config: AllMessagesConfig):
        super().__init__(config)
        self.all_messages_config = config
    
    async def _match_condition(self, message_event: MessageEvent, account: Account) -> bool:
        self.logger.info(f"[全量监控] 处理消息 - 来自: {message_event.message.sender.full_name} ({message_event.message.sender.id})")
        self.logger.info(f"[全量监控] 群组: 聊天ID {message_event.message.chat_id}")
        self.logger.info(f"[全量监控] 内容: {message_event.message.text[:100] if message_event.message.text else '(非文本消息)'}")
        return True
    
    async def _execute_custom_actions(self, message_event: MessageEvent, account: Account) -> List[str]:
        actions = []
        
        self.logger.info(f"[全量监控] 执行动作 - 执行次数: {self.config.execution_count + 1}")
        
        if self.config.max_executions:
            remaining = self.config.max_executions - self.config.execution_count - 1
            if remaining <= 5:
                self.logger.warning(f"[全量监控] 剩余执行次数: {remaining}")
        
        return actions 
    
    def get_dynamic_reply_content(self) -> List[str]:
        if hasattr(self.all_messages_config, 'reply_content_type'):
            from models.config import ReplyContentType
            
            if (hasattr(self.all_messages_config.reply_content_type, 'value') 
                and self.all_messages_config.reply_content_type.value == 'ai') or \
               (isinstance(self.all_messages_config.reply_content_type, str) 
                and self.all_messages_config.reply_content_type == 'ai'):
                return []
        
        return self.all_messages_config.reply_texts if self.all_messages_config.reply_texts else []
    
    async def _add_monitor_specific_info(self, log_parts: List[str], message_event: MessageEvent, account: Account):
        if self.all_messages_config.chat_id and self.all_messages_config.chat_id != 0:
            log_parts.append(f"🎯 监控目标: 特定聊天 {self.all_messages_config.chat_id}")
        else:
            log_parts.append(f"🎯 监控目标: 所有聊天")
        
        if self.all_messages_config.reply_enabled:
            if self.all_messages_config.reply_texts:
                reply_count = len(self.all_messages_config.reply_texts)
                log_parts.append(f"💬 自动回复: 已配置 {reply_count} 条回复内容")
            
            if self.all_messages_config.reply_delay_max > 0:
                log_parts.append(f"⏱️ 回复延时: {self.all_messages_config.reply_delay_min}-{self.all_messages_config.reply_delay_max}秒")
        
        log_parts.append(f"📊 监控范围: 全量消息监控")
    
    async def _get_monitor_type_info(self) -> str:
        if self.all_messages_config.chat_id and self.all_messages_config.chat_id != 0:
            return f"(指定聊天:{self.all_messages_config.chat_id})"
        else:
            return "(全聊天)" 