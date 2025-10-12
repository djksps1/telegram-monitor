"""
消息相关数据模型
"""

from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime
from telethon.tl.types import User, Channel, Chat
from telethon import events


@dataclass
class MessageSender:
    id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    is_bot: bool = False
    is_channel: bool = False
    title: Optional[str] = None
    
    @property
    def full_name(self) -> str:
        if self.title:
            return self.title
        parts = []
        if self.first_name:
            parts.append(self.first_name)
        if self.last_name:
            parts.append(self.last_name)
        return " ".join(parts) if parts else "未知用户"
    
    @classmethod
    def from_telethon_entity(cls, entity) -> 'MessageSender':
        if isinstance(entity, User):
            return cls(
                id=entity.id,
                username=entity.username,
                first_name=entity.first_name,
                last_name=entity.last_name,
                is_bot=entity.bot or False,
                is_channel=False
            )
        elif isinstance(entity, (Channel, Chat)):
            return cls(
                id=entity.id,
                username=getattr(entity, 'username', None),
                title=entity.title,
                is_bot=False,
                is_channel=isinstance(entity, Channel)
            )
        else:
            return cls(
                id=getattr(entity, 'id', 0),
                username=getattr(entity, 'username', None),
                first_name="未知",
                is_bot=False,
                is_channel=False
            )


@dataclass
class MessageMedia:
    has_media: bool = False
    media_type: Optional[str] = None
    file_name: Optional[str] = None
    file_size: Optional[int] = None
    file_extension: Optional[str] = None
    mime_type: Optional[str] = None
    
    @property
    def file_size_mb(self) -> Optional[float]:
        if self.file_size:
            return self.file_size / (1024 * 1024)
        return None


@dataclass
class MessageButton:
    text: str
    row: int
    col: int
    data: Optional[str] = None


@dataclass
class TelegramMessage:
    message_id: int
    chat_id: int
    sender: MessageSender
    text: str
    timestamp: datetime
    media: Optional[MessageMedia] = None
    buttons: List[List[MessageButton]] = field(default_factory=list)
    is_forwarded: bool = False
    forward_from_channel_id: Optional[int] = None
    reply_to_message_id: Optional[int] = None
    
    @property
    def text_lower(self) -> str:
        return self.text.lower().strip()
    
    @property
    def has_buttons(self) -> bool:
        return len(self.buttons) > 0
    
    @property
    def button_texts(self) -> List[str]:
        texts = []
        for row in self.buttons:
            for button in row:
                texts.append(button.text.strip())
        return texts
    
    def get_button_by_text(self, text: str, exact_match: bool = False) -> Optional[MessageButton]:
        search_text = text.lower()
        for row in self.buttons:
            for button in row:
                button_text = button.text.lower()
                if exact_match:
                    if button_text == search_text:
                        return button
                else:
                    if search_text in button_text:
                        return button
        return None
    
    @classmethod
    def from_telethon_event(cls, event: events.NewMessage, sender: MessageSender) -> 'TelegramMessage':
        message = event.message
        
        media = None
        if message.media:
            media = MessageMedia(has_media=True)
            if hasattr(message.media, 'document'):
                doc = message.media.document
                media.file_size = doc.size
                media.mime_type = doc.mime_type
                
                for attr in doc.attributes:
                    if hasattr(attr, 'file_name'):
                        media.file_name = attr.file_name
                        if '.' in attr.file_name:
                            media.file_extension = '.' + attr.file_name.split('.')[-1].lower()
                        break
                
                if media.mime_type:
                    if media.mime_type.startswith('image/'):
                        media.media_type = 'image'
                    elif media.mime_type.startswith('video/'):
                        media.media_type = 'video'
                    elif media.mime_type.startswith('audio/'):
                        media.media_type = 'audio'
                    else:
                        media.media_type = 'document'
            elif hasattr(message.media, 'photo'):
                media.media_type = 'photo'
        
        buttons = []
        if message.buttons:
            for row_idx, row in enumerate(message.buttons):
                button_row = []
                for col_idx, button in enumerate(row):
                    msg_button = MessageButton(
                        text=button.text,
                        row=row_idx,
                        col=col_idx,
                        data=getattr(button, 'data', None)
                    )
                    button_row.append(msg_button)
                buttons.append(button_row)
        
        is_forwarded = message.fwd_from is not None
        forward_from_channel_id = None
        if is_forwarded and message.fwd_from:
            if hasattr(message.fwd_from, 'from_chat') and message.fwd_from.from_chat:
                forward_from_channel_id = message.fwd_from.from_chat.id
            elif hasattr(message.fwd_from, 'from_id') and message.fwd_from.from_id:
                forward_from_channel_id = getattr(message.fwd_from.from_id, 'channel_id', None)
        
        return cls(
            message_id=message.id,
            chat_id=event.chat_id,
            sender=sender,
            text=message.text or '',
            timestamp=message.date,
            media=media,
            buttons=buttons,
            is_forwarded=is_forwarded,
            forward_from_channel_id=forward_from_channel_id,
            reply_to_message_id=message.reply_to_msg_id
        )


@dataclass
class MessageEvent:
    account_id: str
    message: TelegramMessage
    event_type: str = "new_message"
    processed: bool = False
    
    @property
    def unique_id(self) -> str:
        return f"{self.account_id}_{self.message.chat_id}_{self.message.message_id}" 