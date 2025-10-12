"""
Web应用主文件
基于FastAPI的现代化Web界面
"""

import asyncio
import json
import secrets
import pytz
from typing import Dict, List, Any, Optional
from pathlib import Path
from datetime import datetime
import io
from apscheduler.triggers.cron import CronTrigger

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Form, HTTPException, Depends, Cookie
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse, FileResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from pydantic import BaseModel

from core import AccountManager, MonitorEngine
from core.account_manager import AccountFactory
from models import Account, AccountConfig
from models.config import KeywordConfig, FileConfig, AIMonitorConfig, MatchType, ScheduledMessageConfig
from monitors import monitor_factory, AIMonitorBuilder
from services import AIService
from utils.logger import get_logger
from .status_monitor import StatusMonitor
from .config_wizard import ConfigWizard

try:
    from utils.config import config
except ImportError:
    config = None

try:
    from telethon.errors import SessionPasswordNeededError
except ImportError:
    class SessionPasswordNeededError(Exception):
        pass


class AccountInfo(BaseModel):
    account_id: str
    phone: str
    user_id: Optional[int]
    monitor_active: bool
    monitor_count: int


class MonitorInfo(BaseModel):
    monitor_type: str
    key: str
    config: Dict[str, Any]
    execution_count: int
    max_executions: Optional[int]
    account_id: Optional[str] = None


class SystemStats(BaseModel):
    total_accounts: int
    active_accounts: int
    total_monitors: int
    processed_messages: int
    uptime: str
    cpu_percent: float
    memory_percent: float
    memory_used_mb: float
    memory_total_mb: float
    disk_usage_percent: float
    network_sent_mb: float
    network_recv_mb: float
    network_status: str


class AddAccountRequest(BaseModel):
    phone: str
    api_id: int
    api_hash: str
    proxy_type: Optional[str] = None
    proxy_host: Optional[str] = None
    proxy_port: Optional[int] = None
    proxy_username: Optional[str] = None
    proxy_password: Optional[str] = None


class VerifyCodeRequest(BaseModel):
    account_id: str
    code: str


class PasswordRequest(BaseModel):
    account_id: str
    password: str


class WebApp:
    
    def __init__(self):
        self.app = FastAPI(title="Telegram监控系统", description="智能化Telegram消息监控平台")
        
        self.app.add_middleware(
            SessionMiddleware,
            secret_key=secrets.token_urlsafe(32),
            max_age=86400
        )
        
        self.account_manager = AccountManager()
        self.monitor_engine = MonitorEngine()
        self.status_monitor = StatusMonitor()
        self.config_wizard = ConfigWizard()
        self.logger = get_logger(__name__)
        
        self.websocket_connections: List[WebSocket] = []
        
        self.pending_accounts: Dict[str, Dict[str, Any]] = {}
        
        self.setup_auth()
        
        self.setup_static_files()
        self.setup_routes()
        
        self.logger.info("Web应用初始化完成")
    
    def _safe_remove_websocket(self, websocket: WebSocket):
        try:
            if websocket in self.websocket_connections:
                self.websocket_connections.remove(websocket)
                self.logger.debug("WebSocket连接已安全移除")
        except (ValueError, AttributeError) as e:
            self.logger.debug(f"移除WebSocket连接时忽略错误: {e}")
        except Exception as e:
            self.logger.warning(f"移除WebSocket连接时发生未预期错误: {e}")
    
    def setup_auth(self):
        if config:
            self.web_username = getattr(config, 'WEB_USERNAME', 'admin')
            self.web_password = getattr(config, 'WEB_PASSWORD', 'admin123')
        else:
            self.web_username = 'admin'
            self.web_password = 'admin123'
        
        self.logger.info(f"Web认证配置 - 用户名: {self.web_username}, 密码: {self.web_password}")
        
        if self.web_password in ['admin123', 'your_secure_password_here', 'admin']:
            self.logger.warning("检测到使用默认密码，强烈建议在.env文件中设置安全的WEB_PASSWORD")
        else:
            self.logger.info("✅ 已使用自定义密码")
        
        self.logger.info(f"Web认证已启用，用户名: {self.web_username}")
    
    def get_current_user(self, request: Request):
        user = request.session.get("user")
        if not user:
            raise HTTPException(
                status_code=401,
                detail="未认证，请先登录"
            )
        return user
    
    def verify_login(self, username: str, password: str) -> bool:
        try:
            is_correct_username = secrets.compare_digest(username, self.web_username)
            is_correct_password = secrets.compare_digest(password, self.web_password)
            return is_correct_username and is_correct_password
        except Exception as e:
            self.logger.error(f"验证登录凭据时发生错误: {e}")
            return False
    
    def setup_static_files(self):
        static_dir = Path("ui/static")
        templates_dir = Path("ui/templates")
        static_dir.mkdir(exist_ok=True)
        templates_dir.mkdir(exist_ok=True)
        
        self.app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
        
        self.templates = Jinja2Templates(directory=str(templates_dir))
    
    def setup_routes(self):
        
        @self.app.exception_handler(400)
        async def bad_request_handler(request: Request, exc):
            return JSONResponse(
                status_code=400,
                content={"detail": "Invalid request"}
            )
        
        @self.app.exception_handler(422)
        async def validation_exception_handler(request: Request, exc):
            return JSONResponse(
                status_code=422,
                content={"detail": "Validation error"}
            )
        
        @self.app.get("/health")
        @self.app.get("/healthz") 
        @self.app.get("/ping")
        async def health_check():
            return {"status": "ok", "timestamp": datetime.now().isoformat()}

        @self.app.get("/robots.txt")
        async def robots_txt():
            return "User-agent: *\nDisallow: /"

        @self.app.post("/logout")
        async def logout(request: Request):
            request.session.clear()
            return {"success": True, "message": "已退出登录"}

        @self.app.get("/login", response_class=HTMLResponse)
        async def login_page(request: Request):
            if request.session.get("user"):
                return RedirectResponse(url="/", status_code=302)
            
            return self.templates.TemplateResponse("login.html", {
                "request": request,
                "title": "登录"
            })
        
        @self.app.post("/login")
        async def login(request: Request, username: str = Form(...), password: str = Form(...)):
            if self.verify_login(username, password):
                request.session["user"] = username
                return {"success": True, "message": "登录成功"}
            else:
                raise HTTPException(
                    status_code=401,
                    detail="用户名或密码错误"
                )
        
        @self.app.post("/logout")
        async def logout(request: Request):
            request.session.clear()
            return {"success": True, "message": "已成功退出登录"}
        
        @self.app.get("/", response_class=HTMLResponse)
        async def dashboard(request: Request):
            if not request.session.get("user"):
                return RedirectResponse(url="/login", status_code=302)
            
            user = self.get_current_user(request)
            return self.templates.TemplateResponse("dashboard.html", {
                "request": request,
                "title": "监控仪表板",
                "user": user
            })
        
        @self.app.get("/logs", response_class=HTMLResponse)
        async def logs_page(request: Request):
            user = self.get_current_user(request)
            return self.templates.TemplateResponse("logs.html", {
                "request": request,
                "title": "程序日志",
                "user": user
            })
        
        @self.app.get("/accounts", response_class=HTMLResponse)
        async def accounts_page(request: Request):
            user = self.get_current_user(request)
            return self.templates.TemplateResponse("accounts.html", {
                "request": request,
                "title": "账号管理",
                "user": user
            })
        
        @self.app.get("/monitors", response_class=HTMLResponse)
        async def monitors_page(request: Request):
            user = self.get_current_user(request)
            return self.templates.TemplateResponse("monitors.html", {
                "request": request,
                "title": "监控器管理",
                "user": user
            })
        
        @self.app.get("/wizard", response_class=HTMLResponse)
        async def wizard_page(request: Request):
            user = self.get_current_user(request)
            monitor_type = request.query_params.get('type', 'keyword')
            edit_mode = request.query_params.get('edit', 'false').lower() == 'true'
            edit_key = request.query_params.get('key', '')
            edit_config = request.query_params.get('config', '{}')
            
            return self.templates.TemplateResponse(
                "wizard.html",
                {
                    "request": request,
                    "monitor_type": monitor_type,
                    "edit_mode": edit_mode,
                    "edit_key": edit_key,
                    "edit_config": edit_config,
                    "user": user
                }
            )
        
        @self.app.get("/scheduled-messages", response_class=HTMLResponse)
        async def scheduled_messages_page(request: Request):
            user = self.get_current_user(request)
            return self.templates.TemplateResponse(
                "scheduled_messages.html",
                {"request": request, "user": user}
            )
        
        @self.app.get("/channels", response_class=HTMLResponse)
        async def channels_page(request: Request):
            user = self.get_current_user(request)
            return self.templates.TemplateResponse(
                "channels.html",
                {"request": request, "user": user}
            )
        
        @self.app.get("/config-export", response_class=HTMLResponse)
        async def config_export_page(request: Request):
            user = self.get_current_user(request)
            return self.templates.TemplateResponse(
                "config_export.html",
                {"request": request, "user": user}
            )
        
        @self.app.get("/api/stats")
        async def get_stats(request: Request):
            user = self.get_current_user(request)
            return await self.get_system_stats()
        
        @self.app.get("/api/backup/history")
        async def get_backup_history(request: Request):
            user = self.get_current_user(request)
            return {
                "history": [
                    {
                        "time": "2025-01-17 10:30",
                        "type": "自动备份",
                        "status": "成功",
                        "size": "2.3 MB"
                    },
                    {
                        "time": "2025-01-16 22:00",
                        "type": "手动备份",
                        "status": "成功",
                        "size": "2.1 MB"
                    }
                ]
            }
        
        @self.app.get("/api/config/stats")
        async def get_config_stats(request: Request):
            user = self.get_current_user(request)
            try:
                accounts_list = self.account_manager.list_accounts()
                account_count = len(accounts_list)
                
                monitor_count = 0
                for account in accounts_list:
                    account_id = account.account_id
                    if account_id in self.monitor_engine.monitors:
                        monitor_count += len(self.monitor_engine.monitors[account_id])
                
                return {
                    "success": True,
                    "stats": {
                        "account_count": account_count,
                        "monitor_count": monitor_count
                    }
                }
            except Exception as e:
                self.logger.error(f"获取配置统计失败: {e}")
                return {
                    "success": False,
                    "stats": {
                        "account_count": 0,
                        "monitor_count": 0
                    }
                }
        
        @self.app.get("/api/email/settings")
        async def get_email_settings(request: Request):
            user = self.get_current_user(request)
            try:
                default_email = ""
                if config and hasattr(config, 'EMAIL_TO') and config.EMAIL_TO:
                    default_email = config.EMAIL_TO.strip()
                elif config and hasattr(config, 'email_to') and config.email_to:
                    default_email = config.email_to.strip()
                elif config and hasattr(config, 'EMAIL_ADDRESS') and config.EMAIL_ADDRESS:
                    default_email = config.EMAIL_ADDRESS.strip()
                elif config and hasattr(config, 'email_address') and config.email_address:
                    default_email = config.email_address.strip()
                    
                self.logger.info(f"读取到默认邮箱配置: {default_email or '未配置'}")
                
                return {
                    "success": True,
                    "settings": {
                        "default_email": default_email,
                        "email_enabled": bool(default_email),
                        "email_list": [default_email] if default_email else []
                    }
                }
            except Exception as e:
                self.logger.error(f"获取邮件设置失败: {e}")
                return {
                    "success": False,
                    "settings": {
                        "default_email": "",
                        "email_enabled": False,
                        "email_list": []
                    }
                }
        
        @self.app.post("/api/email/settings")
        async def update_email_settings(request: Request):
            user = self.get_current_user(request)
            try:
                data = await request.json()
                email_list = data.get('email_list', [])
                email_enabled = data.get('email_enabled', False)
                
                self.logger.info(f"更新邮件设置: enabled={email_enabled}, emails={email_list}")
                
                return {
                    "success": True,
                    "message": "邮件设置已更新"
                }
            except Exception as e:
                self.logger.error(f"更新邮件设置失败: {e}")
                return {
                    "success": False,
                    "message": f"更新失败: {str(e)}"
                }
        
        @self.app.get("/api/config/defaults")
        async def get_config_defaults(request: Request):
            user = self.get_current_user(request)
            try:
                from utils.config import config
                return {
                    "success": True,
                    "api_id": config.TG_API_ID,
                    "api_hash": config.TG_API_HASH
                }
            except Exception as e:
                self.logger.error(f"获取配置默认值失败: {e}")
                return {"success": False, "message": str(e)}
        
        @self.app.get("/api/accounts")
        async def get_accounts(request: Request):
            user = self.get_current_user(request)
            try:
                accounts_list = self.account_manager.list_accounts()
                accounts_info = []
                
                for account in accounts_list:
                    monitor_count = 0
                    if account.account_id in self.monitor_engine.monitors:
                        monitor_count = len(self.monitor_engine.monitors[account.account_id])
                    
                    is_valid, status = await account.check_validity()
                    status_display = account.get_status_display(status)
                    
                    user_id = getattr(account, 'own_user_id', None) or getattr(account, 'user_id', None)
                    name = None
                    if account.client and is_valid:
                        try:
                            me = await account.client.get_me()
                            if me:
                                first_name = getattr(me, 'first_name', '') or ''
                                last_name = getattr(me, 'last_name', '') or ''
                                name = f"{first_name} {last_name}".strip() if first_name or last_name else None
                        except Exception:
                            pass
                    
                    account_info = {
                        "account_id": account.account_id,
                        "phone": account.config.phone,
                        "name": name,
                        "user_id": user_id,
                        "monitor_active": getattr(account, 'monitor_active', False),
                        "monitor_count": monitor_count,
                        "status": status,
                        "status_display": status_display,
                        "is_valid": is_valid
                    }
                    accounts_info.append(account_info)
                
                return {"success": True, "accounts": accounts_info}
            except Exception as e:
                self.logger.error(f"获取账号列表失败: {e}")
                return {"success": False, "accounts": [], "error": str(e)}
        
        @self.app.post("/api/accounts")
        async def add_account(request: Request, add_account_request: AddAccountRequest):
            user = self.get_current_user(request)
            try:
                proxy_config = None
                if add_account_request.proxy_type and add_account_request.proxy_host and add_account_request.proxy_port:
                    proxy_config = {
                        'type': add_account_request.proxy_type,
                        'host': add_account_request.proxy_host,
                        'port': add_account_request.proxy_port,
                        'username': add_account_request.proxy_username,
                        'password': add_account_request.proxy_password
                    }
                
                account_config = AccountFactory.create_account_config(
                    phone=add_account_request.phone,
                    api_id=add_account_request.api_id,
                    api_hash=add_account_request.api_hash,
                    proxy_config=proxy_config
                )
                
                from telethon import TelegramClient
                client = TelegramClient(
                    account_config.session_name,
                    account_config.api_id,
                    account_config.api_hash,
                    proxy=account_config.proxy
                )
                
                await client.connect()
                
                if not await client.is_user_authorized():
                    await client.send_code_request(add_account_request.phone)
                    
                    self.pending_accounts[add_account_request.phone] = {
                        'config': account_config,
                        'client': client,
                        'step': 'verify_code'
                    }
                    
                    return {"success": True, "message": "验证码已发送，请检查您的Telegram", "step": "verify_code"}
                else:
                    me = await client.get_me()
                    account = Account(
                        account_id=add_account_request.phone,
                        config=account_config,
                        client=client,
                        own_user_id=me.id,
                        monitor_active=True
                    )
                    
                    self.account_manager.add_account(account)
                    await self.broadcast_status_update()
                    
                    return {"success": True, "message": "账号添加成功"}
                    
            except Exception as e:
                self.logger.error(f"添加账号失败: {e}")
                return {"success": False, "message": f"添加账号失败: {str(e)}"}
        
        @self.app.post("/api/accounts/verify")
        async def verify_code(request: Request, verify_code_request: VerifyCodeRequest):
            user = self.get_current_user(request)
            try:
                if verify_code_request.account_id not in self.pending_accounts:
                    return {"success": False, "message": "账号信息未找到，请重新开始"}
                
                pending = self.pending_accounts[verify_code_request.account_id]
                client = pending['client']
                
                try:
                    await client.sign_in(verify_code_request.account_id, verify_code_request.code)
                    
                    me = await client.get_me()
                    account = Account(
                        account_id=verify_code_request.account_id,
                        config=pending['config'],
                        client=client,
                        own_user_id=me.id,
                        monitor_active=True
                    )
                    
                    self.account_manager.add_account(account)
                    
                    del self.pending_accounts[verify_code_request.account_id]
                    
                    await self.broadcast_status_update()
                    
                    return {"success": True, "message": "账号添加成功"}
                    
                except SessionPasswordNeededError:
                    pending['step'] = 'password'
                    return {"success": True, "message": "检测到两步验证，请输入密码", "step": "password"}
                except Exception as signin_error:
                    return {"success": False, "message": f"验证码错误或已过期: {str(signin_error)}"}
                        
            except Exception as e:
                self.logger.error(f"验证码验证失败: {e}")
                return {"success": False, "message": f"验证失败: {str(e)}"}
        
        @self.app.post("/api/accounts/password")
        async def verify_password(request: Request, password_request: PasswordRequest):
            user = self.get_current_user(request)
            try:
                if password_request.account_id not in self.pending_accounts:
                    return {"success": False, "message": "账号信息未找到，请重新开始"}
                
                pending = self.pending_accounts[password_request.account_id]
                client = pending['client']
                
                await client.sign_in(password=password_request.password)
                
                me = await client.get_me()
                account = Account(
                    account_id=password_request.account_id,
                    config=pending['config'],
                    client=client,
                    own_user_id=me.id,
                    monitor_active=True
                )
                
                self.account_manager.add_account(account)
                
                del self.pending_accounts[password_request.account_id]
                
                await self.broadcast_status_update()
                
                return {"success": True, "message": "账号添加成功"}
                
            except Exception as e:
                self.logger.error(f"密码验证失败: {e}")
                return {"success": False, "message": f"密码错误或验证失败: {str(e)}"}
        
        @self.app.delete("/api/accounts/{account_id}")
        async def delete_account(request: Request, account_id: str):
            user = self.get_current_user(request)
            try:
                success = self.account_manager.remove_account(account_id)
                if success:
                    self.monitor_engine.remove_all_monitors(account_id)
                    await self.broadcast_status_update()
                    return {"success": True, "message": "账号删除成功"}
                else:
                    return {"success": False, "message": "账号不存在"}
            except Exception as e:
                self.logger.error(f"删除账号失败: {e}")
                return {"success": False, "message": f"删除失败: {str(e)}"}
        
        @self.app.post("/api/accounts/{account_id}/toggle")
        async def toggle_account(request: Request, account_id: str):
            user = self.get_current_user(request)
            account = self.account_manager.get_account(account_id)
            if not account:
                raise HTTPException(status_code=404, detail="账号不存在")
            
            new_status = not account.monitor_active
            self.account_manager.set_account_monitor_status(account_id, new_status)
            
            await self.broadcast_status_update()
            
            return {"success": True, "status": new_status}
        
        @self.app.get("/api/monitors/{account_id}")
        async def get_monitors(request: Request, account_id: str):
            user = self.get_current_user(request)
            return await self.get_monitors_info(account_id)
        
        @self.app.delete("/api/monitors/{account_id}/{monitor_key}")
        async def delete_monitor(request: Request, account_id: str, monitor_key: str):
            user = self.get_current_user(request)
            success = self.monitor_engine.remove_monitor(account_id, monitor_key)
            if success:
                await self.broadcast_status_update()
                return {"success": True}
            else:
                raise HTTPException(status_code=404, detail="监控器不存在")
        
        @self.app.put("/api/monitors/{account_id}/{monitor_key}/toggle")
        async def toggle_monitor_status(request: Request, account_id: str, monitor_key: str):
            user = self.get_current_user(request)
            try:
                data = await request.json()
                active = data.get('active', True)
                
                if account_id in self.monitor_engine.monitors:
                    monitors = self.monitor_engine.monitors[account_id]
                    for i, monitor in enumerate(monitors):
                        generated_key = f"{monitor.__class__.__name__}_{i}"
                        
                        if generated_key == monitor_key:
                            monitor.config.active = active
                            self.monitor_engine._save_monitors()
                            await self.broadcast_status_update()
                            
                            self.logger.info(f"监控器状态切换成功: {monitor_key} -> {'启动' if active else '暂停'}")
                            
                            return {
                                "success": True,
                                "message": f"监控器已{'启动' if active else '暂停'}",
                                "active": active
                            }
                
                return {"success": False, "message": "未找到指定的监控器"}
                
            except Exception as e:
                self.logger.error(f"切换监控器状态失败: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.post("/api/wizard/start")
        async def start_wizard(request: Request, data: Dict[str, Any]):
            user = self.get_current_user(request)
            try:
                import json
                
                session_id = data.get("session_id", "")
                edit_mode = data.get("edit_mode", False)
                edit_key = data.get("edit_key", "")
                edit_config = data.get("edit_config", {})
                force_new = data.get("force_new", False)
                
                if force_new:
                    result = self.config_wizard.force_new_session(session_id)
                elif edit_mode and edit_key:
                    result = self.config_wizard.start_wizard_edit_mode(session_id, edit_key, edit_config)
                else:
                    result = self.config_wizard.start_wizard(session_id)
                
                try:
                    json.dumps(result)
                except (TypeError, ValueError) as serialize_error:
                    self.logger.error(f"序列化错误: {serialize_error}")
                    self.logger.error(f"问题数据: {result}")
                    return {
                        "success": False,
                        "errors": ["数据序列化失败"],
                        "message": "数据序列化失败，请重试"
                    }
                
                return result
                
            except Exception as e:
                self.logger.error(f"启动向导失败: {e}")
                import traceback
                self.logger.error(traceback.format_exc())
                return {
                    "success": False,
                    "errors": [str(e)],
                    "message": f"启动向导失败: {str(e)}"
                }
        
        @self.app.post("/api/wizard/previous")
        async def wizard_previous_step(request: Request, data: Dict[str, Any]):
            user = self.get_current_user(request)
            try:
                session_id = data.get("session_id", "")
                result = self.config_wizard.go_to_previous_step(session_id)
                return result
            except Exception as e:
                self.logger.error(f"返回上一步失败: {e}")
                return {
                    "success": False,
                    "errors": [str(e)],
                    "message": f"返回上一步失败: {str(e)}"
                }
        
        @self.app.post("/api/wizard/step")
        async def wizard_process_step(request: Request, data: Dict[str, Any]):
            user = self.get_current_user(request)
            try:
                session_id = data.get("session_id", "")
                step_data = {k: v for k, v in data.items() if k != "session_id"}
                result = self.config_wizard.process_step(session_id, step_data)
                return result
            except Exception as e:
                self.logger.error(f"处理向导步骤失败: {e}")
                return {
                    "success": False,
                    "errors": [str(e)],
                    "message": f"处理向导步骤失败: {str(e)}"
                }
        
        @self.app.post("/api/wizard/keyword")
        async def create_keyword_monitor(
            request: Request,
            account_id: str = Form(...),
            keyword: str = Form(...),
            match_type: str = Form(...),
            chats: str = Form(...),
            email_notify: bool = Form(False),
            auto_forward: bool = Form(False),
            forward_targets: str = Form(""),
            enhanced_forward: bool = Form(False),
            max_download_size: str = Form(""),
            edit_mode: bool = Form(False),
            edit_key: str = Form("")
        ):
            user = self.get_current_user(request)
            try:
                chat_ids = [int(x.strip()) for x in chats.split(',') if x.strip()]
                target_ids = [int(x.strip()) for x in forward_targets.split(',') if x.strip() and auto_forward]
                max_size = float(max_download_size) if max_download_size else None
                
                config = KeywordConfig(
                    keyword=keyword,
                    match_type=MatchType(match_type),
                    chats=chat_ids,
                    email_notify=email_notify,
                    auto_forward=auto_forward,
                    forward_targets=target_ids,
                    enhanced_forward=enhanced_forward,
                    max_download_size_mb=max_size
                )
                
                monitor = monitor_factory.create_monitor(config)
                if monitor:
                    if edit_mode and edit_key:
                        self.monitor_engine.remove_monitor(account_id, edit_key)
                        self.monitor_engine.add_monitor(account_id, monitor, f"keyword_{keyword}")
                        message = "关键词监控器更新成功"
                    else:
                        self.monitor_engine.add_monitor(account_id, monitor, f"keyword_{keyword}")
                        message = "关键词监控器创建成功"
                    
                    await self.broadcast_status_update()
                    return {"success": True, "message": message}
                else:
                    return {"success": False, "message": "监控器创建失败"}
                    
            except Exception as e:
                self.logger.error(f"创建关键词监控器失败: {e}")
                return {"success": False, "message": f"创建失败: {str(e)}"}
        
        @self.app.post("/api/wizard/ai")
        async def create_ai_monitor(
            request: Request,
            account_id: str = Form(...),
            ai_prompt: str = Form(...),
            chats: str = Form(...),
            email_notify: bool = Form(False),
            auto_forward: bool = Form(False),
            forward_targets: str = Form(""),
            enhanced_forward: bool = Form(False),
            max_download_size: str = Form(""),
            confidence_threshold: float = Form(0.7)
        ):
            user = self.get_current_user(request)
            try:
                ai_service = AIService()
                if not ai_service.is_configured():
                    return {"success": False, "message": "AI服务未配置，请先配置AI服务"}
                
                chat_ids = [int(x.strip()) for x in chats.split(',') if x.strip()]
                target_ids = [int(x.strip()) for x in forward_targets.split(',') if x.strip() and auto_forward]
                max_size = float(max_download_size) if max_download_size else None
                
                ai_monitor = (AIMonitorBuilder()
                             .with_prompt(ai_prompt)
                             .with_chats(chat_ids)
                             .with_email_notify(email_notify)
                             .with_auto_forward(auto_forward, target_ids)
                             .with_enhanced_forward(enhanced_forward, max_size)
                             .with_confidence_threshold(confidence_threshold)
                             .build())
                
                monitor_key = f"ai_{ai_prompt[:20]}..."
                self.monitor_engine.add_monitor(account_id, ai_monitor, monitor_key)
                await self.broadcast_status_update()
                
                return {"success": True, "message": "AI监控器创建成功"}
                
            except Exception as e:
                self.logger.error(f"创建AI监控器失败: {e}")
                return {"success": False, "message": f"创建失败: {str(e)}"}
        
        @self.app.post("/api/wizard/file")
        async def create_file_monitor(
            request: Request,
            account_id: str = Form(...),
            file_extension: str = Form(...),
            chats: str = Form(...),
            email_notify: bool = Form(False),
            auto_forward: bool = Form(False),
            forward_targets: str = Form(""),
            enhanced_forward: bool = Form(False),
            save_folder: str = Form(""),
            min_size: str = Form(""),
            max_size: str = Form(""),
            edit_mode: bool = Form(False),
            edit_key: str = Form("")
        ):
            user = self.get_current_user(request)
            try:
                chat_ids = [int(x.strip()) for x in chats.split(',') if x.strip()]
                target_ids = [int(x.strip()) for x in forward_targets.split(',') if x.strip() and auto_forward]
                min_size_mb = float(min_size) if min_size else None
                max_size_mb = float(max_size) if max_size else None
                
                from models.config import FileConfig
                config = FileConfig(
                    file_extension=file_extension,
                    chats=chat_ids,
                    users=[],
                    blocked_users=[],
                    blocked_channels=[],
                    blocked_bots=[],
                    email_notify=email_notify,
                    auto_forward=auto_forward,
                    forward_targets=target_ids,
                    enhanced_forward=enhanced_forward,
                    save_folder=save_folder if save_folder else None,
                    min_size_mb=min_size_mb,
                    max_size_mb=max_size_mb
                )
                
                monitor = monitor_factory.create_monitor(config)
                if monitor:
                    if edit_mode and edit_key:
                        self.monitor_engine.remove_monitor(account_id, edit_key)
                        self.monitor_engine.add_monitor(account_id, monitor, f"file_{file_extension}")
                        message = "文件监控器更新成功"
                    else:
                        self.monitor_engine.add_monitor(account_id, monitor, f"file_{file_extension}")
                        message = "文件监控器创建成功"
                    
                    await self.broadcast_status_update()
                    return {"success": True, "message": message}
                else:
                    return {"success": False, "message": "监控器创建失败"}
                    
            except Exception as e:
                self.logger.error(f"创建文件监控器失败: {e}")
                return {"success": False, "message": f"创建失败: {str(e)}"}
        
        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            await websocket.accept()
            self.websocket_connections.append(websocket)
            
            try:
                stats = await self.get_system_stats()
                await websocket.send_json(stats.dict())
                
                while True:
                    await websocket.receive_text()
                    
            except WebSocketDisconnect:
                pass
            except Exception as e:
                self.logger.error(f"WebSocket错误: {e}")
            finally:
                self._safe_remove_websocket(websocket)
        
        @self.app.get("/api/accounts/{account_id}/channels")
        async def get_account_channels(request: Request, account_id: str, page: int = 1, limit: int = 100, search: str = "", fetch_all: str = ""):
            user = self.get_current_user(request)
            try:
                fetch_all_bool = fetch_all.lower() in ['1', 'true', 'yes']
                self.logger.info(f"fetch_all参数: '{fetch_all}' -> {fetch_all_bool}")
                account = self.account_manager.get_account(account_id)
                if not account:
                    raise HTTPException(status_code=404, detail="账号不存在")
                
                if not account.client:
                    raise HTTPException(status_code=500, detail="账号客户端未初始化")
                
                if not account.client.is_connected():
                    await account.client.connect()
                
                if fetch_all_bool:
                    max_fetch = None
                    max_archived = None
                    self.logger.info(f"全量模式：获取账号 {account_id} 的所有对话")
                else:
                    max_fetch = 200
                    max_archived = 50
                    self.logger.info(f"限制模式：获取账号 {account_id} 的前{max_fetch}个对话")
                
                channels = []
                dialog_count = 0
                all_dialog_ids = set()
                
                try:
                    self.logger.info(f"开始获取账号 {account_id} 的对话列表，限制数量: {max_fetch}")
                    
                    dialogs = []
                    dialog_iter_count = 0
                    
                    async for dialog in account.client.iter_dialogs(limit=max_fetch, archived=False):
                        if dialog.id not in all_dialog_ids:
                            dialogs.append(dialog)
                            all_dialog_ids.add(dialog.id)
                            dialog_iter_count += 1
                            if max_fetch and dialog_iter_count >= max_fetch:
                                break
                    
                    try:
                        archived_count = 0
                        async for dialog in account.client.iter_dialogs(limit=max_archived, archived=True):
                            if dialog.id not in all_dialog_ids:
                                dialogs.append(dialog)
                                all_dialog_ids.add(dialog.id)
                                archived_count += 1
                                if max_archived and archived_count >= max_archived:
                                    break
                        self.logger.info(f"额外获取 {archived_count} 个归档对话")
                    except Exception as archived_error:
                        self.logger.debug(f"获取归档对话失败: {archived_error}")
                    
                    self.logger.info(f"获取到 {len(dialogs)} 个对话，开始处理...")
                    
                    for dialog in dialogs:
                        try:
                            dialog_count += 1
                            
                            is_bot_dialog = False
                            is_user_dialog = False
                            
                            try:
                                if hasattr(dialog, 'entity') and dialog.entity:
                                    entity = dialog.entity
                                    entity_type = entity.__class__.__name__
                                    
                                    if entity_type == 'User':
                                        is_user_dialog = True
                                        
                                        bot_check_methods = []
                                        
                                        if hasattr(entity, 'bot') and entity.bot is True:
                                            is_bot_dialog = True
                                            bot_check_methods.append('bot_attribute')
                                        
                                        username = getattr(entity, 'username', None)
                                        if username and str(username).lower().endswith('bot'):
                                            is_bot_dialog = True
                                            bot_check_methods.append('username_pattern')
                                        
                                        if hasattr(entity, 'verified') and entity.verified and username:
                                            is_bot_dialog = True
                                            bot_check_methods.append('verified_user')
                                        
                                            
                            except Exception as e:
                                self.logger.warning(f"检查对话类型失败: {e}")
                            
                            if not (dialog.is_channel or dialog.is_group or is_bot_dialog or is_user_dialog):
                                continue
                                
                            try:
                                dialog_id = str(dialog.id) if dialog.id else str(dialog_count)
                                
                                if dialog.title:
                                    dialog_title = dialog.title[:100]
                                elif is_user_dialog and hasattr(dialog, 'entity') and dialog.entity:
                                    entity = dialog.entity
                                    first_name = getattr(entity, 'first_name', '') or ''
                                    last_name = getattr(entity, 'last_name', '') or ''
                                    username = getattr(entity, 'username', None)
                                    
                                    if first_name or last_name:
                                        dialog_title = f"{first_name} {last_name}".strip()
                                        if username:
                                            dialog_title += f" (@{username})"
                                    elif username:
                                        dialog_title = f"@{username}"
                                    else:
                                        dialog_title = f"用户_{dialog.id}"
                                else:
                                    dialog_title = f"对话_{dialog_count}"
                                
                                dialog_title = dialog_title[:100]
                                
                                if is_bot_dialog:
                                    dialog_type = "bot"
                                elif dialog.is_channel:
                                    dialog_type = "channel"
                                elif dialog.is_group:
                                    dialog_type = "group"
                                elif is_user_dialog:
                                    dialog_type = "user"
                                else:
                                    dialog_type = "unknown"
                                
                                if search and search.lower() not in dialog_title.lower():
                                    continue
                                
                            except Exception as basic_error:
                                self.logger.warning(f"获取基本属性失败: {basic_error}")
                                continue
                            
                            username = None
                            description = ""
                            members_count = 0
                            
                            try:
                                entity = dialog.entity
                                if entity:
                                    username = getattr(entity, 'username', None)
                                    description = (getattr(entity, 'about', "") or "")[:100]
                                    members_count = getattr(entity, 'participants_count', 0) or 0
                                    
                                    
                                    if username:
                                        username = str(username)
                                    if description:
                                        description = str(description)
                                    members_count = int(members_count) if members_count else 0
                            except Exception:
                                pass
                            
                            link = ""
                            if username:
                                link = f"https://t.me/{username}"
                            elif dialog_type == 'group' and not username:
                                link = "私密群"
                            elif dialog_type == 'bot':
                                link = f"Bot ID: {dialog_id}"
                            elif dialog_type == 'user':
                                link = f"私聊 ID: {dialog_id}"
                            
                            channel_info = {
                                "id": dialog_id,
                                "name": dialog_title,
                                "description": description,
                                "type": dialog_type,
                                "username": username,
                                "members_count": members_count,
                                "messages_today": 0,
                                "active_level": "中",
                                "is_monitored": False,
                                "avatar": None,
                                "link": link
                            }
                            channels.append(channel_info)
                            
                        except Exception as dialog_error:
                            self.logger.warning(f"处理对话 {dialog_count} 时出错: {dialog_error}")
                            continue
                    
                    total_channels = len(channels)
                    if fetch_all_bool:
                        paged_channels = channels
                        self.logger.info(f"全量模式：返回所有 {total_channels} 个对话")
                    else:
                        start_index = (page - 1) * limit
                        end_index = start_index + limit
                        paged_channels = channels[start_index:end_index]
                        self.logger.info(f"分页模式：返回第{page}页 {len(paged_channels)} 个")
                    
                    type_counts = {}
                    for channel in channels:
                        channel_type = channel.get('type', 'unknown')
                        type_counts[channel_type] = type_counts.get(channel_type, 0) + 1
                    
                    self.logger.info(f"成功获取 {total_channels} 个对话，类型分布: {type_counts}")
                    self.logger.info(f"其中群组: {type_counts.get('group', 0)}, 频道: {type_counts.get('channel', 0)}, Bot: {type_counts.get('bot', 0)}, 私聊: {type_counts.get('user', 0)}")
                    
                    if fetch_all_bool:
                        return {
                            "success": True, 
                            "channels": paged_channels,
                            "total": total_channels,
                            "fetch_all": True,
                            "type_counts": type_counts
                        }
                    else:
                        self.logger.info(f"返回第{page}页 {len(paged_channels)} 个")
                        return {
                            "success": True, 
                            "channels": paged_channels,
                            "total": total_channels,
                            "page": page,
                            "limit": limit,
                            "total_pages": (total_channels + limit - 1) // limit
                        }
                    
                except Exception as iter_error:
                    self.logger.error(f"迭代对话时出错: {iter_error}")
                    return {"success": False, "channels": [], "error": f"获取频道列表失败: {str(iter_error)}"}
                
            except Exception as e:
                self.logger.error(f"获取频道列表失败: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.post("/api/accounts/{account_id}/export-channels")
        async def export_channels(request: Request, account_id: str, format: str = "json"):
            user = self.get_current_user(request)
            try:
                account = self.account_manager.get_account(account_id)
                if not account:
                    raise HTTPException(status_code=404, detail="账号不存在")
                
                dialogs = []
                async for dialog in account.client.iter_dialogs():
                    if dialog.is_channel or dialog.is_group:
                        dialog_info = {
                            "id": dialog.id,
                            "title": dialog.title,
                            "type": "channel" if dialog.is_channel else "group",
                            "username": getattr(dialog.entity, 'username', None),
                            "link": f"https://t.me/{dialog.entity.username}" if getattr(dialog.entity, 'username', None) else None,
                            "members_count": getattr(dialog.entity, 'participants_count', None),
                            "date_joined": str(dialog.date) if dialog.date else None
                        }
                        dialogs.append(dialog_info)
                
                if format == "csv":
                    import csv
                    from io import StringIO
                    output = StringIO()
                    writer = csv.DictWriter(output, fieldnames=["id", "title", "type", "username", "link", "members_count", "date_joined"])
                    writer.writeheader()
                    writer.writerows(dialogs)
                    
                    return StreamingResponse(
                        io.BytesIO(output.getvalue().encode('utf-8')),
                        media_type="text/csv",
                        headers={"Content-Disposition": f"attachment; filename=channels_{account_id}.csv"}
                    )
                else:
                    import tempfile
                    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                        json.dump(dialogs, f, indent=2, ensure_ascii=False)
                        temp_path = f.name
                    
                    return FileResponse(
                        temp_path,
                        media_type="application/json",
                        headers={"Content-Disposition": f"attachment; filename=channels_{account_id}.json"}
                    )
                    
            except Exception as e:
                self.logger.error(f"导出频道列表失败: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.post("/api/scheduled-messages")
        async def create_scheduled_message(request: Request, message: Dict[str, Any]):
            user = self.get_current_user(request)
            try:
                from models.config import ScheduledMessageConfig
                import uuid
                
                channel_id = message.get("channel_id", "")
                if channel_id:
                    try:
                        target_id = int(channel_id)
                    except ValueError:
                        raise HTTPException(status_code=400, detail="无效的群组/频道ID")
                else:
                    raise HTTPException(status_code=400, detail="群组/频道ID不能为空")
                
                max_executions = message.get("max_executions")
                if max_executions == "" or max_executions is None:
                    max_executions = None
                else:
                    try:
                        max_executions = int(max_executions)
                    except (ValueError, TypeError):
                        max_executions = None
                
                schedule_mode = message.get("schedule_mode", "cron")
                schedule_expr = message.get("schedule", message.get("cron", ""))
                
                if not schedule_expr:
                    raise HTTPException(status_code=400, detail="定时规则不能为空")
                
                if schedule_mode == "interval":
                    parts = schedule_expr.split()
                    if len(parts) != 2:
                        raise HTTPException(status_code=400, detail="间隔格式错误，应为：小时 分钟")
                    
                    try:
                        hours = int(parts[0])
                        minutes = int(parts[1])
                        if hours < 0 or minutes < 0 or minutes > 59:
                            raise HTTPException(status_code=400, detail="间隔时间无效：小时必须>=0，分钟必须在0-59之间")
                        if hours == 0 and minutes == 0:
                            raise HTTPException(status_code=400, detail="间隔时间不能为0")
                    except ValueError:
                        raise HTTPException(status_code=400, detail="间隔时间必须是整数")
                else:
                    from utils.validators import validate_cron_expression
                    is_valid, error_msg = validate_cron_expression(schedule_expr)
                    if not is_valid:
                        raise HTTPException(status_code=400, detail=f"Cron表达式错误: {error_msg}")
                
                if not message.get("account_id"):
                    raise HTTPException(status_code=400, detail="账号ID不能为空")
                if not message.get("message") and not message.get("use_ai"):
                    raise HTTPException(status_code=400, detail="消息内容或AI提示词不能为空")
                
                config = ScheduledMessageConfig(
                    job_id=str(uuid.uuid4()),
                    target_id=target_id,
                    message=message.get("message", ""),
                    schedule_mode=schedule_mode,
                    cron=schedule_expr,
                    random_offset=message.get("random_delay", message.get("random_offset", 0)),
                    delete_after_sending=message.get("delete_after_send", message.get("delete_after_sending", False)),
                    account_id=message.get("account_id"),
                    max_executions=max_executions,
                    execution_count=0,
                    use_ai=message.get("use_ai", False),
                    ai_prompt=message.get("ai_prompt")
                )
                
                from core import MonitorEngine
                engine = MonitorEngine()
                engine.add_scheduled_message(config)
                
                return {"success": True, "job_id": config.job_id}
                
            except Exception as e:
                self.logger.error(f"创建定时消息失败: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/api/scheduled-messages")
        async def list_scheduled_messages(request: Request):
            user = self.get_current_user(request)
            try:
                from core import MonitorEngine
                engine = MonitorEngine()
                messages = engine.get_scheduled_messages()
                
                total_count = len(messages)
                active_count = sum(1 for msg in messages if msg.get('active', True))
                paused_count = sum(1 for msg in messages if not msg.get('active', True))
                total_executions = sum(msg.get('execution_count', 0) for msg in messages)
                
                return {
                    "success": True, 
                    "messages": messages,
                    "statistics": {
                        "total_count": total_count,
                        "active_count": active_count,
                        "paused_count": paused_count,
                        "total_executions": total_executions
                    }
                }
                
            except Exception as e:
                self.logger.error(f"获取定时消息失败: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/api/cron-examples")
        async def get_cron_examples(request: Request):
            user = self.get_current_user(request)
            from utils.validators import get_cron_examples
            return {"success": True, "examples": get_cron_examples()}
        
        @self.app.delete("/api/scheduled-messages/{job_id}")
        async def delete_scheduled_message(request: Request, job_id: str):
            user = self.get_current_user(request)
            try:
                from core import MonitorEngine
                engine = MonitorEngine()
                success = engine.remove_scheduled_message(job_id)
                
                if success:
                    return {"success": True, "message": "定时消息删除成功"}
                else:
                    return {"success": False, "message": "未找到指定的定时消息"}
                
            except Exception as e:
                self.logger.error(f"删除定时消息失败: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.put("/api/scheduled-messages/{job_id}")
        async def update_scheduled_message(request: Request, job_id: str):
            user = self.get_current_user(request)
            try:
                data = await request.json()
                
                from core import MonitorEngine
                engine = MonitorEngine()
                
                for i, msg in enumerate(engine.scheduled_messages):
                    if msg.get('job_id') == job_id:
                        old_cron = msg.get('cron') or msg.get('schedule')
                        old_active = msg.get('active', True)
                        
                        max_executions = data.get("max_executions")
                        if max_executions == "" or max_executions is None or max_executions == 0:
                            max_executions = None
                        else:
                            try:
                                max_executions = int(max_executions)
                                if max_executions <= 0:
                                    max_executions = None
                            except (ValueError, TypeError):
                                max_executions = None
                        
                        self.logger.info(f"📝 更新定时消息执行次数限制: {max_executions or '无限制'}")
                        
                        new_cron = data.get('schedule', data.get('cron', old_cron))
                        engine.scheduled_messages[i].update({
                            'account_id': data.get('account_id'),
                            'message': data.get('message', ''),
                            'channel_id': data.get('channel_id'),
                            'target_id': data.get('channel_id'),
                            'schedule': new_cron,
                            'cron': new_cron,
                            'use_ai': data.get('use_ai', False),
                            'ai_prompt': data.get('ai_prompt', ''),
                            'random_delay': data.get('random_delay', 0),
                            'random_offset': data.get('random_delay', 0),
                            'delete_after_send': data.get('delete_after_send', False),
                            'delete_after_sending': data.get('delete_after_send', False),
                            'max_executions': max_executions
                        })
                        
                        self.logger.info(f"📝 定时消息更新: {job_id}, 执行限制: {max_executions or '无限制'}, Cron: {new_cron}")
                        
                        if old_cron != new_cron or old_active:
                            engine._ensure_scheduler_started()
                            
                            if engine.scheduler and engine.scheduler.running:
                                try:
                                    engine.scheduler.remove_job(job_id)
                                    self.logger.info(f"移除旧的定时任务: {job_id}")
                                except Exception as remove_error:
                                    self.logger.debug(f"移除旧任务失败（可能不存在）: {remove_error}")
                                
                                if msg.get('active', True) and new_cron:
                                    try:
                                        engine.scheduler.add_job(
                                            engine._execute_scheduled_message,
                                            CronTrigger.from_crontab(new_cron, timezone=pytz.timezone('Asia/Shanghai')),
                                            id=job_id,
                                            args=[job_id],
                                            replace_existing=True
                                        )
                                        self.logger.info(f"更新定时任务: {job_id}, 新Cron: {new_cron}")
                                    except Exception as add_error:
                                        self.logger.error(f"重新添加定时任务失败: {add_error}")
                        
                        engine._save_scheduled_messages()
                        return {"success": True, "message": "定时消息更新成功"}
                
                return {"success": False, "message": "未找到指定的定时消息"}
                
            except Exception as e:
                self.logger.error(f"更新定时消息失败: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.put("/api/scheduled-messages/{job_id}/toggle")
        async def toggle_scheduled_message(request: Request, job_id: str):
            user = self.get_current_user(request)
            try:
                data = await request.json()
                active = data.get('active', True)
                
                from core import MonitorEngine
                engine = MonitorEngine()
                
                for msg in engine.scheduled_messages:
                    if msg.get('job_id') == job_id:
                        msg['active'] = active
                        
                        engine._ensure_scheduler_started()
                        
                        if active:
                            if msg.get('max_executions') and msg.get('execution_count', 0) >= msg.get('max_executions'):
                                msg['execution_count'] = 0
                                self.logger.info(f"重新启动定时任务，执行计数已重置: {job_id}")
                            
                            cron_expr = msg.get('cron', msg.get('schedule'))
                            schedule_mode = msg.get('schedule_mode', 'cron')
                            
                            if cron_expr and engine.scheduler and engine.scheduler.running:
                                try:
                                    if schedule_mode == 'interval':
                                        parts = cron_expr.split()
                                        hours = int(parts[0]) if len(parts) > 0 else 0
                                        minutes = int(parts[1]) if len(parts) > 1 else 0
                                        
                                        from apscheduler.triggers.interval import IntervalTrigger
                                        trigger = IntervalTrigger(
                                            hours=hours,
                                            minutes=minutes,
                                            timezone=pytz.timezone('Asia/Shanghai')
                                        )
                                        self.logger.info(f"使用间隔触发器重新启动: {hours}小时 {minutes}分钟")
                                    else:
                                        trigger = CronTrigger.from_crontab(cron_expr, timezone=pytz.timezone('Asia/Shanghai'))
                                        self.logger.info(f"使用Cron触发器重新启动: {cron_expr}")
                                    
                                    engine.scheduler.add_job(
                                        engine._execute_scheduled_message,
                                        trigger,
                                        id=job_id,
                                        args=[job_id],
                                        replace_existing=True
                                    )
                                    self.logger.info(f"成功重新启动定时任务: {job_id}")
                                except Exception as scheduler_error:
                                    self.logger.error(f"启动定时任务失败: {scheduler_error}")
                        else:
                            if engine.scheduler and engine.scheduler.running:
                                try:
                                    engine.scheduler.remove_job(job_id)
                                    self.logger.info(f"暂停定时任务: {job_id}")
                                except Exception as scheduler_error:
                                    self.logger.warning(f"暂停定时任务失败: {scheduler_error}")
                            else:
                                self.logger.debug(f"调度器未运行，跳过暂停任务: {job_id}")
                        
                        engine._save_scheduled_messages()
                        return {
                            "success": True, 
                            "message": f"定时消息已{'启动' if active else '暂停'}",
                            "active": active
                        }
                
                return {"success": False, "message": "未找到指定的定时消息"}
                
            except Exception as e:
                self.logger.error(f"切换定时消息状态失败: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/api/logs")
        async def get_logs(request: Request, limit: int = 1000, since: str = ""):
            user = self.get_current_user(request)
            try:
                import logging
                import time
                from datetime import datetime, timedelta
                
                logs = []
                
                log_file = Path("logs/telegram_monitor.log")
                if log_file.exists():
                    try:
                        since_time = datetime.fromisoformat(since) if since else datetime.now() - timedelta(hours=24)
                        
                        with open(log_file, 'r', encoding='utf-8') as f:
                            lines = f.readlines()
                            
                        recent_lines = lines[-limit:] if len(lines) > limit else lines
                        
                        for line in recent_lines:
                            if line.strip():
                                try:
                                    if 'GET /api/' in line or 'POST /api/' in line or \
                                       'PUT /api/' in line or 'DELETE /api/' in line or \
                                       'INFO:     ' in line and 'HTTP/1.1' in line:
                                        continue
                                    
                                    parts = line.strip().split(' - ', 3)
                                    if len(parts) >= 4:
                                        timestamp_str = parts[0]
                                        source = parts[1]
                                        level = parts[2]
                                        message = parts[3]
                                        
                                        if '日志' in message or '获取日志' in message or '读取日志' in message:
                                            continue
                                        
                                        log_time = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f')
                                        
                                        if log_time >= since_time:
                                            logs.append({
                                                'timestamp': log_time.isoformat(),
                                                'level': level,
                                                'source': source,
                                                'message': message
                                            })
                                except Exception as parse_error:
                                    continue
                    except Exception as file_error:
                        self.logger.error(f"读取日志文件失败: {file_error}")
                
                if not logs:
                    logs = [
                        {
                            'timestamp': datetime.now().isoformat(),
                            'level': 'INFO',
                            'source': 'System',
                            'message': '日志系统正在运行...'
                        }
                    ]
                
                return {
                    "success": True,
                    "logs": logs[-limit:],
                    "total": len(logs)
                }
                
            except Exception as e:
                self.logger.error(f"获取日志失败: {e}")
                return {
                    "success": False,
                    "message": f"获取日志失败: {str(e)}",
                    "logs": []
                }
        
        @self.app.get("/api/logs/download")
        async def download_logs(request: Request):
            user = self.get_current_user(request)
            try:
                log_file = Path("logs/telegram_monitor.log")
                if log_file.exists():
                    return FileResponse(
                        path=str(log_file),
                        filename=f"tg_monitor_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log",
                        media_type="text/plain"
                    )
                else:
                    temp_content = f"# TG监控系统日志文件\n# 生成时间: {datetime.now()}\n\n暂无日志记录。\n"
                    temp_file = Path(f"temp_logs_{datetime.now().timestamp()}.log")
                    temp_file.write_text(temp_content, encoding='utf-8')
                    
                    return FileResponse(
                        path=str(temp_file),
                        filename=f"tg_monitor_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log",
                        media_type="text/plain"
                    )
                    
            except Exception as e:
                self.logger.error(f"下载日志失败: {e}")
                raise HTTPException(status_code=500, detail=f"下载日志失败: {str(e)}")
        
        @self.app.delete("/api/logs/clear")
        async def clear_logs(request: Request):
            user = self.get_current_user(request)
            try:
                log_file = Path("logs/telegram_monitor.log")
                if log_file.exists():
                    with open(log_file, 'w', encoding='utf-8') as f:
                        f.write('')

                
                return {"success": True, "message": "日志已清空"}
                
            except Exception as e:
                self.logger.error(f"清空日志失败: {e}")
                raise HTTPException(status_code=500, detail=f"清空日志失败: {str(e)}")
        
        @self.app.get("/api/export/monitors")
        async def export_monitors(request: Request):
            user = self.get_current_user(request)
            try:
                from pathlib import Path
                monitors_file = Path("data/monitor_configs.json")
                
                if monitors_file.exists():
                    import json
                    with open(monitors_file, 'r', encoding='utf-8') as f:
                        monitors = json.load(f)
                    return monitors
                else:
                    return {}
                    
            except Exception as e:
                self.logger.error(f"导出监控器配置失败: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/api/export/config")
        async def export_config(request: Request):
            user = self.get_current_user(request)
            try:
                account_ids = request.query_params.get('accounts', '')
                
                export_data = {
                    'version': '2.0',
                    'export_time': datetime.now().isoformat(),
                    'accounts': {},
                    'monitors': {},
                    'scheduled_messages': []
                }
                
                if account_ids == 'all' or not account_ids:
                    accounts = self.account_manager.list_accounts()
                    self.logger.info(f"导出全部账号，共 {len(accounts)} 个")
                else:
                    account_list = account_ids.split(',') if ',' in account_ids else [account_ids]
                    accounts = []
                    for aid in account_list:
                        aid = aid.strip()
                        if aid:
                            account = self.account_manager.get_account(aid)
                            if account:
                                accounts.append(account)
                                self.logger.info(f"成功获取账号: {aid}")
                            else:
                                self.logger.warning(f"未找到账号: {aid}")
                    self.logger.info(f"导出指定账号，共 {len(accounts)} 个")
                
                if not accounts:
                    self.logger.error("未找到任何可导出的账号")
                    raise HTTPException(status_code=404, detail="未找到指定的账号")
                
                for account in accounts:
                    export_data['accounts'][account.account_id] = {
                        'phone': account.config.phone,
                        'api_id': account.config.api_id,
                        'api_hash': account.config.api_hash,
                        'monitor_active': account.monitor_active,
                        'proxy': account.config.proxy if hasattr(account.config, 'proxy') else None
                    }
                    
                    monitors = self.monitor_engine.get_monitors(account.account_id)
                    if monitors:
                        export_data['monitors'][account.account_id] = []
                        for monitor in monitors:
                            config = monitor.config
                            monitor_data = {
                                'type': monitor.__class__.__name__,
                                'config': config.dict() if hasattr(config, 'dict') else config.__dict__
                            }
                            export_data['monitors'][account.account_id].append(monitor_data)
                
                scheduled_messages = self.monitor_engine.get_scheduled_messages()
                for msg in scheduled_messages:
                    export_data['scheduled_messages'].append({
                        'job_id': msg.get('job_id', ''),
                        'target_id': msg.get('target_id'),
                        'channel_id': msg.get('channel_id'),
                        'message': msg.get('message', ''),
                        'cron': msg.get('cron', ''),
                        'schedule': msg.get('schedule', msg.get('cron', '')),
                        'schedule_mode': msg.get('schedule_mode', 'cron'),
                        'account_id': msg.get('account_id'),
                        'random_offset': msg.get('random_offset', 0),
                        'random_delay': msg.get('random_delay', 0),
                        'delete_after_sending': msg.get('delete_after_sending', False),
                        'delete_after_send': msg.get('delete_after_send', False),
                        'max_executions': msg.get('max_executions'),
                        'execution_count': msg.get('execution_count', 0),
                        'use_ai': msg.get('use_ai', False),
                        'ai_prompt': msg.get('ai_prompt', ''),
                        'active': msg.get('active', True)
                    })
                
                return export_data
                
            except Exception as e:
                self.logger.error(f"导出配置失败: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.post("/api/import/config")
        async def import_config(request: Request):
            user = self.get_current_user(request)
            try:
                data = await request.json()
                
                if 'config' in data:
                    config = data.get('config', {})
                    mode = data.get('mode', 'merge')
                else:
                    config = data
                    mode = 'merge'
                
                self.logger.info(f"开始导入配置，模式: {mode}")
                
                imported_accounts = 0
                imported_monitors = 0
                imported_scheduled = 0
                
                if mode == 'overwrite':
                    self.logger.info("覆盖模式：清理现有配置")
                    for account_id in self.account_manager.list_accounts():
                        try:
                            self.monitor_engine.remove_all_monitors(account_id.account_id)
                        except Exception as e:
                            self.logger.warning(f"清理账号 {account_id.account_id} 监控器失败: {e}")
                    
                    try:
                        if hasattr(self.monitor_engine, 'clear_scheduled_messages'):
                            self.monitor_engine.clear_scheduled_messages()
                    except Exception as e:
                        self.logger.warning(f"清理定时消息失败: {e}")
                
                if 'accounts' in config:
                    self.logger.info(f"导入 {len(config['accounts'])} 个账号配置")
                    for account_id, account_config in config['accounts'].items():
                        try:
                            existing_account = self.account_manager.get_account(account_id)
                            if existing_account and mode == 'merge':
                                self.logger.info(f"账号 {account_id} 已存在，跳过导入")
                                continue
                            
                            imported_accounts += 1
                            
                        except Exception as e:
                            self.logger.error(f"导入账号 {account_id} 配置失败: {e}")
                
                if 'monitors' in config:
                    self.logger.info("导入监控器配置")
                    for account_id, monitors_data in config['monitors'].items():
                        account = self.account_manager.get_account(account_id)
                        if not account:
                            self.logger.warning(f"账号 {account_id} 不存在，跳过导入")
                            continue
                        
                        self.logger.info(f"为账号 {account_id} 导入 {len(monitors_data)} 个监控器")
                        
                        for monitor_data in monitors_data:
                            try:
                                monitor_type = monitor_data.get('type')
                                config_data = monitor_data.get('config', {})
                                
                                type_mapping = {
                                    'KeywordMonitor': 'keyword',
                                    'FileMonitor': 'file', 
                                    'AIMonitor': 'ai',
                                    'AllMessagesMonitor': 'allmessages',
                                    'ImageButtonMonitor': 'imagebutton',
                                    'ButtonMonitor': 'button'
                                }
                                
                                def convert_bool(value):
                                    if isinstance(value, str):
                                        return value.lower() in ('true', 'on', 'yes', '1')
                                    return bool(value)
                                
                                if monitor_type in type_mapping:
                                    monitor_type = type_mapping[monitor_type]
                                    self.logger.debug(f"类型映射: {monitor_data.get('type')} -> {monitor_type}")
                                
                                if monitor_type == 'keyword':
                                    from models.config import KeywordConfig, MatchType, ReplyMode
                                    monitor_config = KeywordConfig(
                                        keyword=config_data.get('keyword', ''),
                                        match_type=MatchType(config_data.get('match_type', 'partial')),
                                        chats=config_data.get('chats', []),
                                        users=config_data.get('users', []),
                                        user_option=config_data.get('user_option'),
                                        blocked_users=config_data.get('blocked_users', []),
                                        blocked_channels=config_data.get('blocked_channels', []),
                                        blocked_bots=config_data.get('blocked_bots', []),
                                        bot_ids=config_data.get('bot_ids', []),
                                        channel_ids=config_data.get('channel_ids', []),
                                        group_ids=config_data.get('group_ids', []),
                                        email_notify=convert_bool(config_data.get('email_notify', False)),
                                        auto_forward=convert_bool(config_data.get('auto_forward', False)),
                                        forward_targets=config_data.get('forward_targets', []),
                                        enhanced_forward=convert_bool(config_data.get('enhanced_forward', False)),
                                        reply_enabled=convert_bool(config_data.get('reply_enabled', False)),
                                        reply_texts=config_data.get('reply_texts', []),
                                        reply_delay_min=config_data.get('reply_delay_min', 0),
                                        reply_delay_max=config_data.get('reply_delay_max', 0),
                                        reply_mode=ReplyMode(config_data.get('reply_mode', 'reply')),
                                        max_executions=config_data.get('max_executions'),
                                        execution_count=config_data.get('execution_count', 0),
                                        priority=config_data.get('priority', 50),
                                        execution_mode=config_data.get('execution_mode', 'merge'),
                                        active=convert_bool(config_data.get('active', True)),
                                        log_file=config_data.get('log_file')
                                    )
                                    monitor = monitor_factory.create_monitor(monitor_config)
                                    if monitor:
                                        self.monitor_engine.add_monitor(account_id, monitor, f"keyword_{monitor_config.keyword}")
                                        imported_monitors += 1
                                
                                elif monitor_type == 'file':
                                    from models.config import FileConfig
                                    monitor_config = FileConfig(
                                        file_extension=config_data.get('file_extension', ''),
                                        chats=config_data.get('chats', []),
                                        users=config_data.get('users', []),
                                        user_option=config_data.get('user_option'),
                                        blocked_users=config_data.get('blocked_users', []),
                                        blocked_channels=config_data.get('blocked_channels', []),
                                        blocked_bots=config_data.get('blocked_bots', []),
                                        bot_ids=config_data.get('bot_ids', []),
                                        channel_ids=config_data.get('channel_ids', []),
                                        group_ids=config_data.get('group_ids', []),
                                        email_notify=convert_bool(config_data.get('email_notify', False)),
                                        auto_forward=convert_bool(config_data.get('auto_forward', False)),
                                        forward_targets=config_data.get('forward_targets', []),
                                        enhanced_forward=convert_bool(config_data.get('enhanced_forward', False)),
                                        save_folder=config_data.get('save_folder'),
                                        min_size=config_data.get('min_size'),
                                        max_size=config_data.get('max_size'),
                                        max_download_size_mb=config_data.get('max_download_size_mb'),
                                        max_executions=config_data.get('max_executions'),
                                        execution_count=config_data.get('execution_count', 0),
                                        priority=config_data.get('priority', 50),
                                        execution_mode=config_data.get('execution_mode', 'merge'),
                                        active=convert_bool(config_data.get('active', True)),
                                        log_file=config_data.get('log_file')
                                    )
                                    monitor = monitor_factory.create_monitor(monitor_config)
                                    if monitor:
                                        self.monitor_engine.add_monitor(account_id, monitor, f"file_{monitor_config.file_extension}")
                                        imported_monitors += 1
                                    
                                elif monitor_type == 'ai':
                                    from models.config import AIMonitorConfig, ReplyMode
                                    monitor_config = AIMonitorConfig(
                                        ai_prompt=config_data.get('ai_prompt', ''),
                                        chats=config_data.get('chats', []),
                                        users=config_data.get('users', []),
                                        user_option=config_data.get('user_option'),
                                        blocked_users=config_data.get('blocked_users', []),
                                        blocked_channels=config_data.get('blocked_channels', []),
                                        blocked_bots=config_data.get('blocked_bots', []),
                                        bot_ids=config_data.get('bot_ids', []),
                                        channel_ids=config_data.get('channel_ids', []),
                                        group_ids=config_data.get('group_ids', []),
                                        email_notify=convert_bool(config_data.get('email_notify', False)),
                                        auto_forward=convert_bool(config_data.get('auto_forward', False)),
                                        forward_targets=config_data.get('forward_targets', []),
                                        enhanced_forward=convert_bool(config_data.get('enhanced_forward', False)),
                                        confidence_threshold=config_data.get('confidence_threshold', 0.7),
                                        ai_model=config_data.get('ai_model', 'gpt-4o'),
                                        reply_enabled=convert_bool(config_data.get('reply_enabled', False)),
                                        reply_texts=config_data.get('reply_texts', []),
                                        reply_delay_min=config_data.get('reply_delay_min', 0),
                                        reply_delay_max=config_data.get('reply_delay_max', 0),
                                        reply_mode=ReplyMode(config_data.get('reply_mode', 'reply')),
                                        max_executions=config_data.get('max_executions'),
                                        execution_count=config_data.get('execution_count', 0),
                                        priority=config_data.get('priority', 50),
                                        execution_mode=config_data.get('execution_mode', 'merge'),
                                        active=convert_bool(config_data.get('active', True)),
                                        log_file=config_data.get('log_file')
                                    )
                                    monitor = monitor_factory.create_monitor(monitor_config)
                                    if monitor:
                                        self.monitor_engine.add_monitor(account_id, monitor, f"ai_{monitor_config.ai_prompt[:20]}...")
                                        imported_monitors += 1
                                
                                elif monitor_type == 'allmessages':
                                    from models.config import AllMessagesConfig, ReplyMode, ReplyContentType
                                    monitor_config = AllMessagesConfig(
                                        chat_id=config_data.get('chat_id', 0),
                                        chats=config_data.get('chats', []),
                                        users=config_data.get('users', []),
                                        user_option=config_data.get('user_option'),
                                        blocked_users=config_data.get('blocked_users', []),
                                        blocked_channels=config_data.get('blocked_channels', []),
                                        blocked_bots=config_data.get('blocked_bots', []),
                                        bot_ids=config_data.get('bot_ids', []),
                                        channel_ids=config_data.get('channel_ids', []),
                                        group_ids=config_data.get('group_ids', []),
                                        email_notify=convert_bool(config_data.get('email_notify', False)),
                                        auto_forward=convert_bool(config_data.get('auto_forward', False)),
                                        forward_targets=config_data.get('forward_targets', []),
                                        enhanced_forward=convert_bool(config_data.get('enhanced_forward', False)),
                                        reply_enabled=convert_bool(config_data.get('reply_enabled', False)),
                                        reply_texts=config_data.get('reply_texts', []),
                                        reply_delay_min=config_data.get('reply_delay_min', 0),
                                        reply_delay_max=config_data.get('reply_delay_max', 0),
                                        reply_mode=ReplyMode(config_data.get('reply_mode', 'reply')),
                                        reply_content_type=ReplyContentType(config_data.get('reply_content_type', 'custom')),
                                        ai_reply_prompt=config_data.get('ai_reply_prompt', ''),
                                        max_executions=config_data.get('max_executions'),
                                        execution_count=config_data.get('execution_count', 0),
                                        priority=config_data.get('priority', 50),
                                        execution_mode=config_data.get('execution_mode', 'merge'),
                                        active=convert_bool(config_data.get('active', True)),
                                        log_file=config_data.get('log_file')
                                    )
                                    monitor = monitor_factory.create_monitor(monitor_config)
                                    if monitor:
                                        self.monitor_engine.add_monitor(account_id, monitor, f"allmessages_{monitor_config.chat_id}")
                                        imported_monitors += 1
                                
                                elif monitor_type == 'imagebutton':
                                    from models.config import ImageButtonConfig
                                    monitor_config = ImageButtonConfig(
                                        ai_prompt=config_data.get('ai_prompt', '分析图片和按钮内容'),
                                        button_keywords=config_data.get('button_keywords', []),
                                        download_images=convert_bool(config_data.get('download_images', True)),
                                        auto_reply=convert_bool(config_data.get('auto_reply', False)),
                                        confidence_threshold=config_data.get('confidence_threshold', 0.7),
                                        chats=config_data.get('chats', []),
                                        users=config_data.get('users', []),
                                        blocked_users=config_data.get('blocked_users', []),
                                        blocked_channels=config_data.get('blocked_channels', []),
                                        blocked_bots=config_data.get('blocked_bots', []),
                                        bot_ids=config_data.get('bot_ids', []),
                                        channel_ids=config_data.get('channel_ids', []),
                                        group_ids=config_data.get('group_ids', []),
                                        email_notify=convert_bool(config_data.get('email_notify', False)),
                                        auto_forward=convert_bool(config_data.get('auto_forward', False)),
                                        forward_targets=config_data.get('forward_targets', []),
                                        enhanced_forward=convert_bool(config_data.get('enhanced_forward', False)),
                                        max_executions=config_data.get('max_executions'),
                                        execution_count=config_data.get('execution_count', 0),
                                        priority=config_data.get('priority', 50),
                                        active=convert_bool(config_data.get('active', True)),
                                        log_file=config_data.get('log_file')
                                    )
                                    monitor = monitor_factory.create_monitor(monitor_config)
                                    if monitor:
                                        self.monitor_engine.add_monitor(account_id, monitor, f"imagebutton_{monitor_config.ai_prompt[:20]}")
                                        imported_monitors += 1
                                
                                else:
                                    self.logger.warning(f"未知的监控器类型: {monitor_type}")
                                    
                            except Exception as e:
                                self.logger.error(f"导入监控器失败: {e}")
                                continue
                    
                    else:
                        for account_id, account_data in config.items():
                            if not isinstance(account_data, dict) or 'config' not in account_data:
                                continue
                            
                            account_config = account_data['config']
                            
                            account = self.account_manager.get_account(account_id)
                            if not account:
                                self.logger.warning(f"账号 {account_id} 不存在，跳过导入")
                                continue
                            
                            if mode == 'replace':
                                self.monitor_engine.remove_all_monitors(account_id)
                            
                            if 'keyword_config' in account_config:
                                for keyword, cfg in account_config['keyword_config'].items():
                                    try:
                                        from models.config import KeywordConfig, MatchType
                                        monitor_config = KeywordConfig(
                                            keyword=keyword,
                                            match_type=MatchType(cfg.get('match_type', 'contains')),
                                            chats=cfg.get('chats', []),
                                            email_notify=cfg.get('email_notify', False),
                                            auto_forward=cfg.get('auto_forward', False),
                                            forward_targets=cfg.get('forward_targets', []),
                                            enhanced_forward=cfg.get('enhanced_forward', False),
                                            reply_enabled=cfg.get('reply_enabled', False),
                                            reply_texts=cfg.get('reply_texts', []),
                                            reply_delay_min=cfg.get('reply_delay_min', 0),
                                            reply_delay_max=cfg.get('reply_delay_max', 0),
                                            max_executions=cfg.get('max_executions'),
                                            priority=cfg.get('priority', 50),
                                            bot_ids=cfg.get('bot_ids', []),
                                            channel_ids=cfg.get('channel_ids', []),
                                            group_ids=cfg.get('group_ids', [])
                                        )
                                        monitor = monitor_factory.create_monitor(monitor_config)
                                        if monitor:
                                            self.monitor_engine.add_monitor(account_id, monitor, f"keyword_{keyword}")
                                            imported_monitors += 1
                                    except Exception as e:
                                        self.logger.error(f"导入关键词配置失败: {e}")
                                        continue
                            
                            if 'file_extension_config' in account_config:
                                for extension, cfg in account_config['file_extension_config'].items():
                                    try:
                                        from models.config import FileConfig
                                        monitor_config = FileConfig(
                                            file_extension=extension,
                                            chats=cfg.get('chats', []),
                                            users=cfg.get('users', []),
                                            blocked_users=cfg.get('blocked_users', []),
                                            blocked_channels=cfg.get('blocked_channels', []),
                                            blocked_bots=cfg.get('blocked_bots', []),
                                            email_notify=cfg.get('email_notify', False),
                                            auto_forward=cfg.get('auto_forward', False),
                                            forward_targets=cfg.get('forward_targets', []),
                                            enhanced_forward=cfg.get('enhanced_forward', False),
                                            save_folder=cfg.get('save_folder'),
                                            min_size=cfg.get('min_size'),
                                            max_size=cfg.get('max_size'),
                                            max_download_size_mb=cfg.get('max_download_size_mb'),
                                            max_executions=cfg.get('max_executions'),
                                            priority=cfg.get('priority', 50),
                                            log_file=cfg.get('log_file'),
                                            bot_ids=cfg.get('bot_ids', []),
                                            channel_ids=cfg.get('channel_ids', []),
                                            group_ids=cfg.get('group_ids', [])
                                        )
                                        monitor = monitor_factory.create_monitor(monitor_config)
                                        if monitor:
                                            self.monitor_engine.add_monitor(account_id, monitor, f"file_{extension}")
                                            imported_monitors += 1
                                    except Exception as e:
                                        self.logger.error(f"导入文件配置失败: {e}")
                                        continue
                    
                if 'scheduled_messages' in config and config['scheduled_messages']:
                    self.logger.info(f"导入 {len(config['scheduled_messages'])} 个定时消息")
                    for msg_data in config['scheduled_messages']:
                        try:
                            from models.config import ScheduledMessageConfig
                            import uuid
                            
                            job_id = msg_data.get('job_id') or msg_data.get('id') or str(uuid.uuid4())
                            schedule = msg_data.get('schedule', msg_data.get('cron', ''))
                            target_id = msg_data.get('target_id', msg_data.get('channel_id'))
                            
                            if target_id:
                                try:
                                    target_id = int(target_id)
                                except:
                                    self.logger.warning(f"无效的目标ID: {target_id}")
                                    continue
                            
                            config = ScheduledMessageConfig(
                                job_id=job_id,
                                target_id=target_id,
                                message=msg_data.get('message', ''),
                                cron=schedule,
                                random_offset=msg_data.get('random_offset', msg_data.get('random_delay', 0)),
                                delete_after_sending=msg_data.get('delete_after_sending', msg_data.get('delete_after_send', False)),
                                account_id=msg_data.get('account_id'),
                                max_executions=msg_data.get('max_executions'),
                                execution_count=msg_data.get('execution_count', 0),
                                use_ai=msg_data.get('use_ai', False),
                                ai_prompt=msg_data.get('ai_prompt'),
                                schedule_mode=msg_data.get('schedule_mode', 'cron')
                            )
                            
                            self.monitor_engine.add_scheduled_message(config)
                            imported_scheduled += 1
                        except Exception as e:
                            self.logger.error(f"导入定时消息失败: {e}")
                            continue
                
                await self.broadcast_status_update()
                
                result_parts = []
                if imported_accounts > 0:
                    result_parts.append(f"{imported_accounts}个账号")
                if imported_monitors > 0:
                    result_parts.append(f"{imported_monitors}个监控器")
                if imported_scheduled > 0:
                    result_parts.append(f"{imported_scheduled}个定时消息")
                
                if result_parts:
                    message = f"配置导入成功，共导入 {', '.join(result_parts)}"
                    mode_text = "覆盖" if mode == 'overwrite' else "合并"
                    message += f" (模式: {mode_text})"
                else:
                    message = "未找到可导入的有效配置"
                
                return {
                    "success": True,
                    "message": message,
                    "imported": {
                        "accounts": imported_accounts,
                        "monitors": imported_monitors,
                        "scheduled_messages": imported_scheduled
                    },
                    "mode": mode
                }
                
            except Exception as e:
                self.logger.error(f"导入配置失败: {e}")
                raise HTTPException(status_code=500, detail=f"导入配置失败: {str(e)}")
    
    async def get_system_stats(self) -> SystemStats:
        total_accounts, active_accounts, connected_accounts, invalid_accounts = await self.status_monitor.get_account_stats()
        engine_stats = self.monitor_engine.get_statistics()
        
        performance_metrics = self.status_monitor.get_performance_metrics()
        
        network_status = "良好"
        if performance_metrics.network_sent_mb == 0 and performance_metrics.network_recv_mb == 0:
            network_status = "无活动"
        elif performance_metrics.network_sent_mb > 100 or performance_metrics.network_recv_mb > 100:
            network_status = "高活动"
        
        return SystemStats(
            total_accounts=total_accounts,
            active_accounts=active_accounts,
            total_monitors=engine_stats['total_monitors'],
            processed_messages=engine_stats['processed_messages'],
            uptime=self.status_monitor.get_uptime(),
            cpu_percent=performance_metrics.cpu_percent,
            memory_percent=performance_metrics.memory_percent,
            memory_used_mb=performance_metrics.memory_used_mb,
            memory_total_mb=performance_metrics.memory_total_mb,
            disk_usage_percent=performance_metrics.disk_usage_percent,
            network_sent_mb=performance_metrics.network_sent_mb,
            network_recv_mb=performance_metrics.network_recv_mb,
            network_status=network_status
        )
    
    async def get_accounts_info(self) -> List[AccountInfo]:
        accounts = self.account_manager.list_accounts()
        result = []
        
        for account in accounts:
            monitor_count = len(self.monitor_engine.get_monitors(account.account_id))
            result.append(AccountInfo(
                account_id=account.account_id,
                phone=account.config.phone,
                user_id=account.own_user_id,
                monitor_active=account.monitor_active,
                monitor_count=monitor_count
            ))
        
        return result
    
    async def get_monitors_info(self, account_id: str) -> List[MonitorInfo]:
        monitors = self.monitor_engine.get_monitors(account_id)
        result = []
        
        for i, monitor in enumerate(monitors):
            try:
                config_dict = {}
                if hasattr(monitor, 'config') and monitor.config:
                    config_dict = {
                        "monitor_type": monitor.__class__.__name__,
                        "type": monitor.__class__.__name__,
                        "chats": getattr(monitor.config, 'chats', []),
                        "email_notify": getattr(monitor.config, 'email_notify', False),
                        "auto_forward": getattr(monitor.config, 'auto_forward', False),
                        "forward_targets": getattr(monitor.config, 'forward_targets', []),
                        "enhanced_forward": getattr(monitor.config, 'enhanced_forward', False),
                        "active": getattr(monitor.config, 'active', True),
                        "priority": getattr(monitor.config, 'priority', 50),
                        "execution_mode": getattr(monitor.config, 'execution_mode', 'merge'),
                        "max_executions": getattr(monitor.config, 'max_executions', None),
                        "execution_count": getattr(monitor.config, 'execution_count', 0),
                        "users": getattr(monitor.config, 'users', []),
                        "user_option": getattr(monitor.config, 'user_option', None),
                        "blocked_users": getattr(monitor.config, 'blocked_users', []),
                        "blocked_channels": getattr(monitor.config, 'blocked_channels', []),
                        "blocked_bots": getattr(monitor.config, 'blocked_bots', []),
                        "bot_ids": getattr(monitor.config, 'bot_ids', []),
                        "channel_ids": getattr(monitor.config, 'channel_ids', []),
                        "group_ids": getattr(monitor.config, 'group_ids', []),
                        "reply_enabled": getattr(monitor.config, 'reply_enabled', False),
                        "reply_texts": getattr(monitor.config, 'reply_texts', []),
                        "reply_delay_min": getattr(monitor.config, 'reply_delay_min', 0),
                        "reply_delay_max": getattr(monitor.config, 'reply_delay_max', 0),
                        "ai_reply_prompt": getattr(monitor.config, 'ai_reply_prompt', '')
                    }
                    
                    reply_mode = getattr(monitor.config, 'reply_mode', 'reply')
                    config_dict["reply_mode"] = reply_mode.value if hasattr(reply_mode, 'value') else str(reply_mode)
                    
                    reply_content_type = getattr(monitor.config, 'reply_content_type', 'custom')
                    config_dict["reply_content_type"] = reply_content_type.value if hasattr(reply_content_type, 'value') else str(reply_content_type)
                    
                    match_type = getattr(monitor.config, 'match_type', 'partial')
                    config_dict["match_type"] = match_type.value if hasattr(match_type, 'value') else str(match_type)
                    
                    if hasattr(monitor.config, 'keyword'):
                        config_dict["keyword"] = monitor.config.keyword
                    if hasattr(monitor.config, 'chat_id'):
                        config_dict["chat_id"] = monitor.config.chat_id
                    if hasattr(monitor.config, 'ai_prompt'):
                        config_dict["ai_prompt"] = monitor.config.ai_prompt
                        config_dict["confidence_threshold"] = getattr(monitor.config, 'confidence_threshold', 0.7)
                        config_dict["ai_model"] = getattr(monitor.config, 'ai_model', 'gpt-4o')
                    if hasattr(monitor.config, 'file_extension'):
                        config_dict["file_extension"] = monitor.config.file_extension
                        config_dict["save_folder"] = getattr(monitor.config, 'save_folder', None)
                        config_dict["min_size"] = getattr(monitor.config, 'min_size', None)
                        config_dict["max_size"] = getattr(monitor.config, 'max_size', None)
                    if hasattr(monitor.config, 'button_keyword'):
                        config_dict["button_keyword"] = monitor.config.button_keyword
                        button_mode = getattr(monitor.config, 'mode', 'manual')
                        config_dict["mode"] = button_mode.value if hasattr(button_mode, 'value') else str(button_mode)
                    if hasattr(monitor.config, 'extension'):
                        config_dict["extension"] = monitor.config.extension
                
                result.append(MonitorInfo(
                    monitor_type=monitor.__class__.__name__,
                    key=f"{monitor.__class__.__name__}_{i}",
                    config=config_dict,
                    execution_count=getattr(monitor.config, 'execution_count', 0) if hasattr(monitor, 'config') else 0,
                    max_executions=getattr(monitor.config, 'max_executions', None) if hasattr(monitor, 'config') else None,
                    account_id=account_id
                ))
                
            except Exception as e:
                self.logger.error(f"获取监控器信息失败: {e}")
                result.append(MonitorInfo(
                    monitor_type=monitor.__class__.__name__,
                    key=f"{monitor.__class__.__name__}_{i}",
                    config={"type": monitor.__class__.__name__, "error": str(e)},
                    execution_count=0,
                    max_executions=None,
                    account_id=account_id
                ))
        
        return result
    
    async def broadcast_status_update(self):
        if not self.websocket_connections:
            return

        stats = await self.get_system_stats()
        message = {
            "type": "stats_update",
            "data": stats.dict()
        }

        connections_copy = list(self.websocket_connections)
        disconnected = []

        for websocket in connections_copy:
            try:
                await websocket.send_json(message)
            except:
                disconnected.append(websocket)

        for websocket in disconnected:
            if websocket in self.websocket_connections:
                self.websocket_connections.remove(websocket)
    
    async def start_background_tasks(self):
        async def status_updater():
            while True:
                try:
                    await asyncio.sleep(5)
                    await self.broadcast_status_update()
                except Exception as e:
                    self.logger.error(f"状态更新错误: {e}")
        
        asyncio.create_task(status_updater())
    
    def get_app(self) -> FastAPI:
        return self.app 