"""
AI服务
封装AI相关功能
"""

import asyncio
import threading
from typing import Optional, List, Dict, Any
from openai import OpenAI

from utils.singleton import Singleton
from utils.logger import get_logger
from utils.config import config


class AIService(metaclass=Singleton):
    
    def __init__(self):
        self.client: Optional[OpenAI] = None
        self._logger = None
        self._initialized = False
        self._init_lock = threading.Lock()
        
    
    @property
    def logger(self):
        if self._logger is None:
            self._logger = get_logger(__name__)
        return self._logger
    
    def _ensure_initialized(self):
        if not self._initialized:
            with self._init_lock:
                if not self._initialized:
                    try:
                        self._initialize_from_config()
                        if self.client is not None:
                            self._initialized = True
                        else:
                            self.logger.warning("AI服务初始化未完成，client仍为None")
                    except Exception as e:
                        self.logger.error(f"AI服务初始化失败: {e}")
                        self.client = None
    
    def _initialize_from_config(self):
        if config.is_openai_configured():
            try:
                self.client = OpenAI(
                    api_key=config.OPENAI_API_KEY,
                    base_url=config.OPENAI_BASE_URL,
                    timeout=30.0,
                    max_retries=2
                )
                self.logger.info("AI服务自动配置完成")
            except Exception as e:
                self.logger.error(f"AI服务配置失败: {e}")
                self.client = None
        else:
            self.logger.warning("OpenAI API未配置，AI功能不可用")
    
    def configure(self, api_key: str, base_url: str, model: str = None):
        with self._init_lock:
            try:
                self.client = OpenAI(
                    api_key=api_key,
                    base_url=base_url,
                    timeout=30.0,
                    max_retries=2
                )
                
                config.OPENAI_API_KEY = api_key
                config.OPENAI_BASE_URL = base_url
                if model:
                    config.OPENAI_MODEL = model
                
                self._initialized = True
                self.logger.info("AI服务手动配置完成")
            except Exception as e:
                self.logger.error(f"AI服务配置失败: {e}")
                self.client = None
                self._initialized = False
    
    def reset(self):
        with self._init_lock:
            self._initialized = False
            self.client = None
            self.logger.info("AI服务状态已重置")
    
    async def get_chat_completion(
        self,
        messages: List[Dict[str, Any]],
        max_retries: int = 1,
        retry_delay: int = 3
    ) -> Optional[str]:
        self._ensure_initialized()
        
        if not self.is_configured():
            self.logger.error("AI服务未配置，请在 .env 文件中设置 OPENAI_API_KEY")
            return None
        
        attempt = 0
        while attempt < max_retries:
            attempt += 1
            try:
                async def call_ai():
                    return await asyncio.to_thread(
                        self.client.chat.completions.create,
                        model=config.OPENAI_MODEL,
                        messages=messages
                    )
                
                response = await asyncio.wait_for(call_ai(), timeout=60.0)
                
                ai_answer = response.choices[0].message.content.strip()
                self.logger.info(f"AI回复: {ai_answer}")
                return ai_answer
                
            except asyncio.TimeoutError:
                self.logger.error(f"AI调用超时(第{attempt}次，超过60秒)")
                if attempt < max_retries:
                    self.logger.info(f"{retry_delay}秒后重试...")
                    await asyncio.sleep(retry_delay)
                else:
                    self.logger.error("AI调用超时，放弃")
                    return None
            except Exception as e:
                self.logger.error(f"AI调用失败(第{attempt}次): {e}")
                if attempt < max_retries:
                    self.logger.info(f"{retry_delay}秒后重试...")
                    await asyncio.sleep(retry_delay)
                else:
                    self.logger.error("多次尝试仍失败，放弃AI调用")
                    return None
    
    async def analyze_message(
        self,
        message_text: str,
        user_prompt: str,
        confidence_threshold: float = 0.7
    ) -> tuple[bool, float]:
        self._ensure_initialized()
        
        if not self.is_configured():
            return False, 0.0
        
        prompt = f"""
请分析以下消息是否符合用户定义的条件。

用户条件: {user_prompt}

消息内容: {message_text}

请根据消息内容判断是否符合用户条件，并给出置信度评分(0-1之间的小数)。

请严格按照以下JSON格式回复，不要包含其他内容：
{{"match": true/false, "confidence": 0.8, "reason": "判断理由"}}
"""
        
        messages = [{"role": "user", "content": prompt}]
        
        try:
            result = await self.get_chat_completion(messages)
            if not result:
                return False, 0.0
            
            import json
            try:
                data = json.loads(result)
                match = data.get("match", False)
                confidence = float(data.get("confidence", 0.0))
                reason = data.get("reason", "")
                
                self.logger.info(f"AI分析结果: 匹配={match}, 置信度={confidence}, 理由={reason}")
                
                if confidence >= confidence_threshold:
                    return match, confidence
                else:
                    self.logger.info(f"置信度 {confidence} 低于阈值 {confidence_threshold}，视为不匹配")
                    return False, confidence
                    
            except json.JSONDecodeError:
                self.logger.error(f"AI返回结果不是有效JSON: {result}")
                return False, 0.0
                
        except Exception as e:
            self.logger.error(f"AI分析失败: {e}")
            return False, 0.0
    
    async def analyze_button_choice(
        self,
        message_text: str,
        button_options: List[str],
        custom_prompt: Optional[str] = None
    ) -> Optional[str]:
        if not button_options:
            return None
        
        self._ensure_initialized()
        
        prompt = custom_prompt or "请根据下面的消息内容和按钮选项，选择最合适的按钮，返回该按钮包含的关键字。"
        options_text = "\n".join(button_options)
        full_prompt = f"{prompt}\n消息内容: {message_text}\n按钮选项:\n{options_text}"
        
        messages = [{"role": "user", "content": full_prompt}]
        
        return await self.get_chat_completion(messages)
    
    async def analyze_image_button(
        self,
        image_base64: str,
        button_options: List[str],
        custom_prompt: Optional[str] = None
    ) -> Optional[str]:
        if not button_options:
            return None
        
        self._ensure_initialized()
        
        prompt = custom_prompt or "请根据图中的内容从下列选项中选出符合图片的选项，你的回答只需要包含选项的内容，不用包含其他内容："
        options_text = "\n".join(button_options)
        full_prompt = f"{prompt}\n{options_text}"
        
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": full_prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpg;base64,{image_base64}"}}
                ]
            }
        ]
        
        return await self.get_chat_completion(messages)
    
    async def analyze_content(
        self,
        content: Dict[str, Any],
        prompt: str
    ) -> Optional[Dict[str, Any]]:
        self._ensure_initialized()
        
        if not self.is_configured():
            return None
        
        system_prompt = f"""
{prompt}

请分析以下内容：
- 群组: {content.get('chat_title', '未知')}
- 发送者: {content.get('sender', '未知')}
- 文本内容: {content.get('text', '(无文本)')}
- 是否有图片: {'是' if content.get('has_image') else '否'}
- 图片描述: {content.get('image_description', '')}

按钮列表:
"""
        
        if content.get('buttons'):
            for btn in content['buttons']:
                system_prompt += f"\n- {btn['text']} (位置: 第{btn['row']+1}行第{btn['col']+1}列)"
        else:
            system_prompt += "\n(无按钮)"
        
        system_prompt += """

请根据上述信息进行分析，并以JSON格式返回结果：
{
    "is_match": true/false,  // 是否符合条件
    "confidence": 0.8,       // 置信度(0-1)
    "reason": "判断理由",
    "button_to_click": "按钮文本",  // 如果需要点击按钮，提供按钮的完整文本
    "reply_message": "回复内容"     // 如果需要回复，提供回复内容
}
"""
        
        if content.get('image_base64'):
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": system_prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpg;base64,{content['image_base64']}"}}
                    ]
                }
            ]
            self.logger.info("[AI分析] 使用图片+文本模式发送给AI")
        else:
            messages = [{"role": "user", "content": system_prompt}]
            self.logger.info("[AI分析] 使用纯文本模式发送给AI")
        
        try:
            result = await self.get_chat_completion(messages)
            if not result:
                return None
            
            import json
            try:
                cleaned_result = result.strip()
                if cleaned_result.startswith('```json'):
                    cleaned_result = cleaned_result[7:]
                if cleaned_result.endswith('```'):
                    cleaned_result = cleaned_result[:-3]
                cleaned_result = cleaned_result.strip()
                
                data = json.loads(cleaned_result)
                self.logger.info(f"[AI分析] JSON解析成功: is_match={data.get('is_match')}, confidence={data.get('confidence')}")
                return data
            except json.JSONDecodeError:
                self.logger.error(f"AI返回结果不是有效JSON: {result}")
                return {
                    "is_match": True,
                    "confidence": 0.5,
                    "reason": "无法解析AI响应",
                    "button_to_click": result.strip() if len(result.strip()) < 50 else None
                }
                
        except Exception as e:
            self.logger.error(f"AI分析内容失败: {e}")
            return None
    
    def is_configured(self) -> bool:
        self._ensure_initialized()
        return self.client is not None
    
    def get_config_status(self) -> Dict[str, Any]:
        return {
            "configured": self.is_configured(),
            "api_key_set": bool(config.OPENAI_API_KEY),
            "model": config.OPENAI_MODEL,
            "base_url": config.OPENAI_BASE_URL
        } 