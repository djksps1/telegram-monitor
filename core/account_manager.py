"""
账号管理器 - 应用单例模式
负责管理所有Telegram账号的登录、连接和状态
"""

import json
import logging
import asyncio
import socks
import socket
from pathlib import Path
from typing import Dict, Optional, List, Tuple
from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError

from models import Account, AccountConfig
from utils.singleton import Singleton
from utils.logger import get_logger


class AccountManager(metaclass=Singleton):
    
    def __init__(self):
        self.accounts: Dict[str, Account] = {}
        self.current_account_id: Optional[str] = None
        self.blocked_bots: set = set()
        self.logger = get_logger(__name__)
        self.accounts_file = Path("data/accounts.json")
        
        self._load_accounts()
    
    def _load_accounts(self):
        if not self.accounts_file.exists():
            self.logger.info("账号文件不存在，跳过加载")
            return
        
        try:
            with open(self.accounts_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            for account_data in data.get('accounts', []):
                try:
                    config = AccountConfig(
                        phone=account_data['config']['phone'],
                        api_id=account_data['config']['api_id'],
                        api_hash=account_data['config']['api_hash'],
                        proxy=account_data['config'].get('proxy'),
                        session_name=account_data['config'].get('session_name', account_data['config']['phone'])
                    )
                    
                    account = Account(
                        account_id=account_data['account_id'],
                        config=config,
                        client=None,
                        own_user_id=account_data.get('own_user_id', 0),
                        monitor_active=account_data.get('monitor_active', False)
                    )
                    
                    if 'monitor_configs' in account_data:
                        account.monitor_configs = account_data['monitor_configs']
                    
                    self.accounts[account.account_id] = account
                    
                    self.logger.info(f"已加载账号: {account.account_id}")
                    
                except Exception as e:
                    self.logger.error(f"加载账号失败: {e}")
            
            if self.accounts and not self.current_account_id:
                self.current_account_id = next(iter(self.accounts.keys()))
                
        except Exception as e:
            self.logger.error(f"加载账号文件失败: {e}")
    
    def _save_accounts(self):
        try:
            self.accounts_file.parent.mkdir(parents=True, exist_ok=True)
            
            accounts_data = []
            for account in self.accounts.values():
                account_data = {
                    'account_id': account.account_id,
                    'config': {
                        'phone': account.config.phone,
                        'api_id': account.config.api_id,
                        'api_hash': account.config.api_hash,
                        'proxy': account.config.proxy,
                        'session_name': account.config.session_name
                    },
                    'own_user_id': account.own_user_id,
                    'monitor_active': account.monitor_active,
                    'monitor_configs': account.monitor_configs
                }
                accounts_data.append(account_data)
            
            with open(self.accounts_file, 'w', encoding='utf-8') as f:
                json.dump({'accounts': accounts_data}, f, indent=2, ensure_ascii=False)
            
            self.logger.info(f"已保存 {len(accounts_data)} 个账号")
            
        except Exception as e:
            self.logger.error(f"保存账号文件失败: {e}")
    
    async def connect_account(self, account_id: str) -> bool:
        account = self.get_account(account_id)
        if not account:
            return False
        
        try:
            client = TelegramClient(
                account.config.session_name,
                account.config.api_id,
                account.config.api_hash,
                proxy=account.config.proxy
            )
            
            await client.connect()
            
            if await client.is_user_authorized():
                account.client = client
                
                me = await client.get_me()
                account.own_user_id = me.id
                
                self.logger.info(f"账号 {account_id} 连接成功")
                return True
            else:
                self.logger.warning(f"账号 {account_id} 未授权，需要重新登录")
                await client.disconnect()
                return False
                
        except Exception as e:
            self.logger.error(f"连接账号 {account_id} 失败: {e}")
            return False
    
    def add_account(self, account: Account) -> bool:
        try:
            existing_account = self.accounts.get(account.account_id)
            if existing_account:
                account.monitor_configs = existing_account.monitor_configs
                has_monitors = bool(existing_account.monitor_configs and any(existing_account.monitor_configs.values()))
                account.monitor_active = existing_account.monitor_active or has_monitors or True
                self.logger.info(f"重新登录账号 {account.account_id}，已保留原有监控配置，监控状态: {account.monitor_active}")
            
            self.accounts[account.account_id] = account
            if self.current_account_id is None:
                self.current_account_id = account.account_id
            
            self._save_accounts()
            
            if account.monitor_active and account.client and account.client.is_connected():
                from core import MonitorEngine
                monitor_engine = MonitorEngine()
                monitor_engine.setup_event_handlers(account)
                self.logger.info(f"为重新登录的账号 {account.account_id} 设置事件处理器")
            
            self.logger.info(f"账号 {account.account_id} 添加成功")
            return True
        except Exception as e:
            self.logger.error(f"添加账号失败: {e}")
            return False
    
    def remove_account(self, account_id: str) -> bool:
        if account_id not in self.accounts:
            self.logger.warning(f"账号 {account_id} 不存在")
            return False
        
        try:
            account = self.accounts[account_id]
            
            if account.client and account.client.is_connected():
                asyncio.create_task(account.client.disconnect())
            
            session_file = Path(f"{account.config.session_name}.session")
            if session_file.exists():
                try:
                    session_file.unlink()
                    self.logger.info(f"已删除session文件: {session_file}")
                except Exception as e:
                    self.logger.error(f"删除session文件失败: {e}")
            
            session_journal = Path(f"{account.config.session_name}.session-journal")
            if session_journal.exists():
                try:
                    session_journal.unlink()
                    self.logger.debug(f"已删除session-journal文件: {session_journal}")
                except Exception as e:
                    self.logger.debug(f"删除session-journal文件失败: {e}")
            
            del self.accounts[account_id]
            
            self._save_accounts()
            
            if self.current_account_id == account_id:
                self.current_account_id = next(iter(self.accounts.keys()), None)
            
            self.logger.info(f"✅ 账号 {account_id} 及相关文件已完全移除")
            return True
        except Exception as e:
            self.logger.error(f"移除账号失败: {e}")
            return False
    
    def get_account(self, account_id: str) -> Optional[Account]:
        return self.accounts.get(account_id)
    
    def get_current_account(self) -> Optional[Account]:
        if self.current_account_id:
            return self.accounts.get(self.current_account_id)
        return None
    
    def switch_account(self, account_id: str) -> bool:
        if account_id in self.accounts:
            self.current_account_id = account_id
            self.logger.info(f"已切换到账号: {account_id}")
            return True
        return False
    
    def list_accounts(self) -> List[Account]:
        return list(self.accounts.values())
    
    def get_account_count(self) -> int:
        return len(self.accounts)
    
    async def create_and_login_account(self, config: AccountConfig) -> Optional[Account]:
        try:
            client = TelegramClient(
                config.session_name,
                config.api_id,
                config.api_hash,
                proxy=config.proxy
            )
            
            await client.connect()
            
            if not await client.is_user_authorized():
                success = await self._login_process(client, config.phone)
                if not success:
                    await client.disconnect()
                    return None
            
            me = await client.get_me()
            own_user_id = me.id
            
            account = Account(
                account_id=config.phone,
                config=config,
                client=client,
                own_user_id=own_user_id,
                monitor_active=True
            )
            
            self.add_account(account)
            
            self.logger.info(f"账号 {config.phone} 登录成功，用户ID: {own_user_id}")
            return account
            
        except Exception as e:
            self.logger.error(f"创建账号失败: {e}")
            return None
    
    async def _login_process(self, client: TelegramClient, phone: str) -> bool:
        try:
            await client.send_code_request(phone)
            self.logger.info('验证码已发送到您的Telegram账号')
            
            code = input('请输入您收到的验证码: ').strip()
            
            try:
                await client.sign_in(phone, code)
            except SessionPasswordNeededError:
                self.logger.info('检测到两步验证，需要输入密码')
                password = input('请输入您的两步验证密码: ').strip()
                await client.sign_in(password=password)
            
            return True
        except Exception as e:
            self.logger.error(f'登录过程中发生错误：{e}')
            return False
    
    def set_account_monitor_status(self, account_id: str, status: bool) -> bool:
        account = self.get_account(account_id)
        if account:
            account.monitor_active = status
            self._save_accounts()
            self.logger.info(f"账号 {account_id} 的监控状态已设置为: {'开启' if status else '关闭'}")
            return True
        return False
    
    def set_all_monitor_status(self, status: bool):
        for account in self.accounts.values():
            account.monitor_active = status
        self.logger.info(f"全局监控状态已设置为: {'开启' if status else '关闭'}")
    
    def get_active_accounts(self) -> List[Account]:
        return [account for account in self.accounts.values() if account.monitor_active]
    
    def add_blocked_bot(self, bot_id: int):
        self.blocked_bots.add(bot_id)
        self.logger.info(f"已屏蔽机器人: {bot_id}")
    
    def remove_blocked_bot(self, bot_id: int) -> bool:
        if bot_id in self.blocked_bots:
            self.blocked_bots.remove(bot_id)
            self.logger.info(f"已取消屏蔽机器人: {bot_id}")
            return True
        return False
    
    def is_bot_blocked(self, bot_id: int) -> bool:
        return bot_id in self.blocked_bots
    
    async def disconnect_all(self):
        tasks = []
        for account in self.accounts.values():
            if account.client and account.client.is_connected():
                tasks.append(account.client.disconnect())
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
            self.logger.info("所有账号连接已断开")


class AccountFactory:
    
    @staticmethod
    def test_proxy_connection(proxy_config: Dict, timeout: int = 10) -> Tuple[bool, str]:
        
        Args:
            proxy_config: 代理配置字典
            timeout: 连接超时时间（秒）
            
        Returns:
            Tuple[bool, str]: (是否成功, 消息)
        """
        logger = get_logger(__name__)
        
        try:
            proxy_type = proxy_config.get('type')
            proxy_host = proxy_config.get('host')
            proxy_port = proxy_config.get('port')
            proxy_user = proxy_config.get('username')
            proxy_pass = proxy_config.get('password')
            
            if not all([proxy_type, proxy_host, proxy_port]):
                return False, "代理配置不完整"
            
            if proxy_type == 'socks5':
                socks_type = socks.SOCKS5
            elif proxy_type == 'socks4':
                socks_type = socks.SOCKS4
            elif proxy_type == 'http':
                socks_type = socks.HTTP
            else:
                return False, f"不支持的代理类型: {proxy_type}"
            
            sock = socks.socksocket()
            sock.set_proxy(
                proxy_type=socks_type,
                addr=proxy_host,
                port=int(proxy_port),
                username=proxy_user if proxy_user else None,
                password=proxy_pass if proxy_pass else None
            )
            sock.settimeout(timeout)
            
            test_host = "149.154.167.50"  # Telegram DC2
            test_port = 443
            
            logger.info(f"正在测试代理连接: {proxy_type}://{proxy_host}:{proxy_port}")
            if proxy_user:
                logger.info(f"使用认证: 用户名={proxy_user}")
            
            try:
                sock.connect((test_host, test_port))
                sock.close()
                
                msg = f"代理连接成功 ({proxy_type}://{proxy_host}:{proxy_port})"
                if proxy_user:
                    msg += f" [认证用户: {proxy_user}]"
                logger.info(msg)
                return True, msg
                
            except socks.ProxyConnectionError as e:
                msg = f"代理连接失败: {str(e)}"
                logger.error(msg)
                return False, msg
            except socket.timeout:
                msg = f"代理连接超时 (>{timeout}秒)"
                logger.error(msg)
                return False, msg
            except Exception as e:
                msg = f"代理测试失败: {str(e)}"
                logger.error(msg)
                return False, msg
            finally:
                try:
                    sock.close()
                except:
                    pass
                    
        except Exception as e:
            msg = f"代理配置错误: {str(e)}"
            logger.error(msg)
            return False, msg
    
    @staticmethod
    def create_account_config(
        phone: str,
        api_id: int,
        api_hash: str,
        proxy_config: Optional[Dict] = None
    ) -> AccountConfig:
        proxy = None
        if proxy_config:
            proxy_type = proxy_config.get('type')
            proxy_host = proxy_config.get('host')
            proxy_port = proxy_config.get('port')
            proxy_user = proxy_config.get('username')
            proxy_pass = proxy_config.get('password')
            
            if proxy_type == 'socks5':
                socks_type = socks.SOCKS5
            elif proxy_type == 'socks4':
                socks_type = socks.SOCKS4
            elif proxy_type == 'http':
                socks_type = socks.HTTP
            else:
                socks_type = None
            
            if socks_type and proxy_host and proxy_port:
                if proxy_user and proxy_pass:
                    proxy = (socks_type, proxy_host, proxy_port, True, proxy_user, proxy_pass)
                else:
                    proxy = (socks_type, proxy_host, proxy_port)
        
        return AccountConfig(
            phone=phone,
            api_id=api_id,
            api_hash=api_hash,
            proxy=proxy
        )
    
    @staticmethod
    async def create_account_from_config(config: AccountConfig) -> Optional[Account]:
        manager = AccountManager()
        return await manager.create_and_login_account(config) 
