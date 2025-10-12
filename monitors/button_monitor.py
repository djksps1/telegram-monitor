"""
按钮监控器
实现按钮点击监控策略
"""

from typing import List

from models import MessageEvent, Account
from models.config import ButtonConfig, MonitorMode
from .base_monitor import BaseMonitor


class ButtonMonitor(BaseMonitor):
    
    def __init__(self, config: ButtonConfig):
        super().__init__(config)
        self.button_config = config
    
    async def _match_condition(self, message_event: MessageEvent, account: Account) -> bool:
        message = message_event.message
        
        if not message.has_buttons:
            return False
        
        if self.button_config.mode == MonitorMode.MANUAL:
            return self._manual_match(message)
        elif self.button_config.mode == MonitorMode.AI:
            return True
        
        return False
    
    def _manual_match(self, message) -> bool:
        keyword = self.button_config.button_keyword.lower()
        for button_text in message.button_texts:
            if keyword in button_text.lower():
                return True
        return False
    
    async def _execute_custom_actions(self, message_event: MessageEvent, account: Account) -> List[str]:
        actions_taken = []
        
        if self.button_config.mode == MonitorMode.MANUAL:
            clicked = await self._click_manual_button(message_event, account)
            if clicked:
                actions_taken.append("点击按钮（手动模式）")
        elif self.button_config.mode == MonitorMode.AI:
            clicked = await self._click_ai_button(message_event, account)
            if clicked:
                actions_taken.append("点击按钮（AI模式）")
        
        return actions_taken
    
    async def _click_manual_button(self, message_event: MessageEvent, account: Account) -> bool:
        try:
            message = message_event.message
            keyword = self.button_config.button_keyword.lower()
            
            target_button = message.get_button_by_text(keyword, exact_match=False)
            
            if target_button:
                self.logger.info(f"点击按钮: {target_button.text}")
                return True
        
        except Exception as e:
            self.logger.error(f"点击按钮失败: {e}")
        
        return False
    
    async def _click_ai_button(self, message_event: MessageEvent, account: Account) -> bool:
        try:
            message = message_event.message
            
            prompt = self.button_config.ai_prompt or "请根据消息内容选择最合适的按钮"
            buttons_text = "\n".join(message.button_texts)
            full_prompt = f"{prompt}\n消息内容: {message.text}\n按钮选项:\n{buttons_text}"
            
            
            
            self.logger.info("AI模式点击按钮（模拟）")
            return True
        
        except Exception as e:
            self.logger.error(f"AI模式点击按钮失败: {e}")
        
        return False
    
    async def _get_ai_choice(self, prompt: str) -> str:
        return ""
    
    async def _add_monitor_specific_info(self, log_parts: List[str], message_event: MessageEvent, account: Account):
        message = message_event.message
        
        mode_name = {
            'manual': '手动模式',
            'ai': 'AI模式'
        }.get(self.button_config.mode.value, self.button_config.mode.value)
        
        log_parts.append(f"🔘 监控模式: {mode_name}")
        
        if self.button_config.mode.value == 'manual':
            log_parts.append(f"🔍 目标按钮: \"{self.button_config.button_keyword}\"")
        elif self.button_config.mode.value == 'ai':
            log_parts.append(f"🤖 AI提示: \"{self.button_config.ai_prompt[:60]}{'...' if len(self.button_config.ai_prompt) > 60 else ''}\"")
        
        if message.has_buttons:
            button_count = len(message.button_texts)
            button_preview = ", ".join(message.button_texts[:3])
            if button_count > 3:
                button_preview += f" (+{button_count-3}个)"
            log_parts.append(f"🎯 检测到按钮: {button_preview}")
            log_parts.append(f"📊 按钮总数: {button_count} 个")
    
    async def _get_monitor_type_info(self) -> str:
        mode_name = {
            'manual': '手动',
            'ai': 'AI'
        }.get(self.button_config.mode.value, '')
        
        if self.button_config.mode.value == 'manual':
            return f"({mode_name}:\"{self.button_config.button_keyword}\")"
        else:
            prompt_preview = self.button_config.ai_prompt[:25] + "..." if len(self.button_config.ai_prompt) > 25 else self.button_config.ai_prompt
            return f"({mode_name}:\"{prompt_preview}\")" 