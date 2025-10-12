"""
监控配置相关数据模型
"""

from typing import Optional, List, Dict, Any, Union
from dataclasses import dataclass, field
from enum import Enum


class MatchType(Enum):
    EXACT = "exact"
    PARTIAL = "partial" 
    REGEX = "regex"


class MonitorMode(Enum):
    MANUAL = "manual"
    AI = "ai"


class ReplyMode(Enum):
    REPLY = "reply"
    SEND = "send"


class ReplyContentType(Enum):
    CUSTOM = "custom"
    AI = "ai"


class ExecutionMode(Enum):
    MERGE = "merge"
    FIRST_MATCH = "first_match"
    ALL = "all"


@dataclass
class BaseMonitorConfig:
    chats: List[int] = field(default_factory=list)
    users: List[Union[int, str]] = field(default_factory=list)
    user_option: Optional[str] = None
    blocked_users: List[str] = field(default_factory=list)
    blocked_channels: List[int] = field(default_factory=list)
    blocked_bots: List[int] = field(default_factory=list)
    match_bots: List[int] = field(default_factory=list)
    match_channels: List[int] = field(default_factory=list)
    bot_ids: List[int] = field(default_factory=list)
    channel_ids: List[int] = field(default_factory=list)
    group_ids: List[int] = field(default_factory=list)
    email_notify: bool = False
    auto_forward: bool = False
    forward_targets: List[int] = field(default_factory=list)
    log_file: Optional[str] = None
    max_executions: Optional[int] = None
    execution_count: int = 0
    enhanced_forward: bool = False
    max_download_size_mb: Optional[float] = None
    download_folder: str = "downloads"
    priority: int = 50
    active: bool = True
    execution_mode: str = "merge"
    
    def is_execution_limit_reached(self) -> bool:
        if self.max_executions is None:
            return False
        return self.execution_count >= self.max_executions
    
    def increment_execution(self):
        self.execution_count += 1
    
    def reset_execution_count(self):
        self.execution_count = 0
    
    def pause_and_reset(self):
        self.active = False
        self.execution_count = 0


@dataclass
class KeywordConfig(BaseMonitorConfig):
    keyword: str = ""
    match_type: MatchType = MatchType.PARTIAL
    reply_enabled: bool = False
    reply_texts: List[str] = field(default_factory=list)
    reply_delay_min: float = 0
    reply_delay_max: float = 0
    reply_mode: ReplyMode = ReplyMode.REPLY
    reply_content_type: ReplyContentType = ReplyContentType.CUSTOM
    ai_reply_prompt: str = ""
    regex_send_target_id: Optional[int] = None
    regex_send_random_offset: int = 0
    regex_send_delete: bool = False
    matched_keyword: Optional[str] = None
    
    def __post_init__(self):
        if isinstance(self.match_type, str):
            self.match_type = MatchType(self.match_type)
        if isinstance(self.reply_mode, str):
            self.reply_mode = ReplyMode(self.reply_mode)
        if isinstance(self.reply_content_type, str):
            self.reply_content_type = ReplyContentType(self.reply_content_type)


@dataclass
class FileConfig(BaseMonitorConfig):
    file_extension: str = ""
    save_folder: Optional[str] = None
    min_size: Optional[float] = None
    max_size: Optional[float] = None
    
    def is_size_valid(self, file_size_mb: float) -> bool:
        if self.min_size is not None and file_size_mb < self.min_size:
            return False
        if self.max_size is not None and file_size_mb > self.max_size:
            return False
        return True


@dataclass
class ButtonConfig(BaseMonitorConfig):
    button_keyword: str = ""
    mode: MonitorMode = MonitorMode.MANUAL
    ai_prompt: str = ""
    
    def __post_init__(self):
        if isinstance(self.mode, str):
            self.mode = MonitorMode(self.mode)


@dataclass
class AllMessagesConfig(BaseMonitorConfig):
    chat_id: int = 0
    reply_enabled: bool = False
    reply_texts: List[str] = field(default_factory=list)
    reply_delay_min: float = 0
    reply_delay_max: float = 0
    reply_mode: ReplyMode = ReplyMode.REPLY
    reply_content_type: ReplyContentType = ReplyContentType.CUSTOM
    ai_reply_prompt: str = ""
    
    def __post_init__(self):
        if isinstance(self.reply_mode, str):
            self.reply_mode = ReplyMode(self.reply_mode)
        if isinstance(self.reply_content_type, str):
            self.reply_content_type = ReplyContentType(self.reply_content_type)


@dataclass
class ImageButtonConfig(BaseMonitorConfig):
    ai_prompt: str = "分析图片和按钮内容，判断是否需要点击某个按钮"
    button_keywords: List[str] = None
    download_images: bool = True
    auto_reply: bool = False
    confidence_threshold: float = 0.7
    
    def __post_init__(self):
        if self.button_keywords is None:
            self.button_keywords = []


@dataclass
class ScheduledMessageConfig:
    job_id: str
    target_id: int
    message: str
    cron: str
    random_offset: int = 0
    delete_after_sending: bool = False
    account_id: Optional[str] = None
    max_executions: Optional[int] = None
    execution_count: int = 0
    use_ai: bool = False
    ai_prompt: Optional[str] = None
    schedule_mode: str = "cron"
    
    def is_execution_limit_reached(self) -> bool:
        if self.max_executions is None:
            return False
        return self.execution_count >= self.max_executions
    
    def increment_execution(self):
        self.execution_count += 1


@dataclass 
class AIMonitorConfig(BaseMonitorConfig):
    ai_prompt: str = ""
    confidence_threshold: float = 0.7
    ai_model: str = "gpt-4o"
    reply_enabled: bool = False
    reply_texts: List[str] = field(default_factory=list)
    reply_delay_min: float = 0
    reply_delay_max: float = 0
    reply_mode: ReplyMode = ReplyMode.REPLY
    ai_reply_prompt: str = ""
    ai_response_content: Optional[str] = None
    
    def __post_init__(self):
        if not self.ai_prompt:
            self.ai_prompt = "请判断以下消息是否符合监控条件，回答 yes 或 no"
        if isinstance(self.reply_mode, str):
            self.reply_mode = ReplyMode(self.reply_mode)


@dataclass
class MonitorConfig:
    keyword_configs: Dict[str, KeywordConfig] = field(default_factory=dict)
    file_configs: Dict[str, FileConfig] = field(default_factory=dict)
    button_configs: Dict[str, ButtonConfig] = field(default_factory=dict)
    all_message_configs: Dict[int, AllMessagesConfig] = field(default_factory=dict)
    ai_monitor_configs: Dict[str, AIMonitorConfig] = field(default_factory=dict)
    image_button_configs: List[ImageButtonConfig] = field(default_factory=list)
    scheduled_message_configs: List[ScheduledMessageConfig] = field(default_factory=list)
    channel_in_group_configs: List[int] = field(default_factory=list)
    
    def add_keyword_config(self, keyword: str, config: KeywordConfig):
        self.keyword_configs[keyword] = config
    
    def remove_keyword_config(self, keyword: str) -> bool:
        if keyword in self.keyword_configs:
            del self.keyword_configs[keyword]
            return True
        return False
    
    def get_keyword_config(self, keyword: str) -> Optional[KeywordConfig]:
        return self.keyword_configs.get(keyword)
    
    def add_file_config(self, extension: str, config: FileConfig):
        self.file_configs[extension] = config
    
    def remove_file_config(self, extension: str) -> bool:
        if extension in self.file_configs:
            del self.file_configs[extension]
            return True
        return False
    
    def get_file_config(self, extension: str) -> Optional[FileConfig]:
        return self.file_configs.get(extension)
    
    def to_dict(self) -> Dict[str, Any]:
        pass
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MonitorConfig':
        pass 