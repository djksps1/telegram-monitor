import sys
from telethon import TelegramClient, events
from telethon.tl.types import Channel, Chat, MessageMediaDocument
import asyncio
import logging
from datetime import datetime, timedelta
from telethon.errors import SessionPasswordNeededError
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import os
import pytz
import re
import random
import shutil
import base64
import json
from openai import OpenAI
import socks  

# 配置One/New API
ONEAPI_KEY = "你的 API 令牌"  # 替换为实际的 API 令牌
ONEAPI_BASE_URL = "http://你的 API 地址/v1"  # API 的服务地址
client_ai = OpenAI(api_key=ONEAPI_KEY, base_url=ONEAPI_BASE_URL)

# === 配置部分 ===
SMTP_SERVER = "smtp.qq.com"          # SMTP 服务器，例如 QQ 邮箱
SMTP_PORT = 465                      # SMTP 端口，通常为 465
SENDER_EMAIL = "您的邮箱@example.com"  # 发件人邮箱
EMAIL_PASSWORD = "您的邮箱授权码"      # 邮箱授权码或密码
RECIPIENT_EMAIL = "收件人邮箱@example.com"  # 收件人邮箱

ACCOUNTS = {}
D_BOTS = set() 
current_account = None  
processed_messages = set()

# 日志配置
def setup_logger():
    logger = logging.getLogger('telegram_monitor')
    logger.setLevel(logging.INFO)
    fh = logging.FileHandler('telegram_monitor.log', encoding='utf-8')
    ch = logging.StreamHandler(stream=sys.stdout)
    ch.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)
    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger

logger = setup_logger()

async def ainput(prompt: str = '') -> str:
    loop = asyncio.get_event_loop()
    print(prompt, end='', flush=True)
    return (await loop.run_in_executor(None, sys.stdin.readline)).rstrip('\n')

def send_email(message_text):
    try:
        message = MIMEMultipart()
        message["From"] = SENDER_EMAIL
        message["To"] = RECIPIENT_EMAIL
        message["Subject"] = Header("Telegram 监控消息", "utf-8")
        body = MIMEText(message_text, "plain", "utf-8")
        message.attach(body)
        server = smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT)
        server.login(SENDER_EMAIL, EMAIL_PASSWORD)
        server.sendmail(SENDER_EMAIL, RECIPIENT_EMAIL, message.as_string())
        logger.info("邮件发送成功")
    except Exception as e:
        logger.error(f"邮件发送失败: {e}")
    finally:
        try:
            server.quit()
        except:
            pass

def match_user(sender, user_set, user_option):
    if not user_set:
        return True
    if not sender:
        return False
    sender_id = sender.id
    sender_username = sender.username.lower() if hasattr(sender, 'username') and sender.username else None
    if hasattr(sender, 'first_name'):
        sender_first_name = sender.first_name or ''
        sender_last_name = sender.last_name or ''
    else:
        sender_first_name = getattr(sender, 'title', '')  # 频道使用 title
        sender_last_name = ''
    sender_full_name = f"{sender_first_name} {sender_last_name}".strip()
    if user_option == '1':
        return sender_id in user_set
    elif user_option == '2':
        return sender_username in user_set
    elif user_option == '3':
        return sender_full_name in user_set
    else:
        return True
        
def default_config():
    return {
        "keyword_config": {},
        "file_extension_config": {},
        "all_messages_config": {},
        "button_keyword_config": {},
        "image_button_monitor": [],
        "scheduled_messages": [],
        "channel_in_group_config": []
    }

def set_account_monitor_active(account_id, status: bool):
    if account_id in ACCOUNTS:
        ACCOUNTS[account_id]['monitor_active'] = status
        logger.info(f"账号 {account_id} 的监控状态已设置为: {'开启' if status else '关闭'}")

def set_monitor_active(status: bool):
    for acc in ACCOUNTS.values():
        acc['monitor_active'] = status
    logger.info(f"全局监控状态已设置为: {'开启' if status else '关闭'}")

async def add_account():
    global ACCOUNTS, current_account
    print("=== 添加账号 ===")
    phone = (await ainput('请输入您的Telegram手机号 (格式如: +8613800138000): ')).strip()
    api_id = int((await ainput('请输入您的 api_id: ')).strip())
    api_hash = (await ainput('请输入您的 api_hash: ')).strip()
    use_proxy = (await ainput("是否配置代理？(yes/no): ")).strip().lower() == 'yes'
    proxy = None
    if use_proxy:
        print("\n支持的代理类型：socks5, socks4, http")
        proxy_type_input = (await ainput("请输入代理类型（例如：socks5）: ")).strip().lower()
        proxy_host = (await ainput("请输入代理服务器地址（例如：127.0.0.1）: ")).strip()
        proxy_port_str = (await ainput("请输入代理服务器端口号（例如：1080）: ")).strip()
        if proxy_host and proxy_port_str.isdigit():
            proxy_port = int(proxy_port_str)
            if proxy_type_input == 'socks5':
                proxy_type = socks.SOCKS5
            elif proxy_type_input == 'socks4':
                proxy_type = socks.SOCKS4
            elif proxy_type_input == 'http':
                proxy_type = socks.HTTP
            else:
                proxy_type = None
                print("不支持的代理类型，将不使用代理连接。")
            if proxy_type:
                proxy_user = (await ainput("请输入代理用户名（如果不需要认证可回车跳过）: ")).strip()
                proxy_pass = (await ainput("请输入代理密码（如果不需要认证可回车跳过）: ")).strip()
                if proxy_user and proxy_pass:
                    proxy = (proxy_type, proxy_host, proxy_port, True, proxy_user, proxy_pass)
                else:
                    proxy = (proxy_type, proxy_host, proxy_port)
        else:
            print("代理地址或端口无效，将使用本地网络连接。")
    session_name = f"session_{phone.replace('+','')}"
    client = TelegramClient(session_name, api_id, api_hash, proxy=proxy)
    try:
        await client.connect()
        if not await client.is_user_authorized():
            await telegram_login(client)
        me = await client.get_me()
        own_user_id = me.id
        account_id = phone  
        ACCOUNTS[account_id] = {
            "client": client,
            "own_user_id": own_user_id,
            "phone": phone,
            "config": default_config(),
            "monitor_active": False
        }
        client.add_event_handler(lambda event, account_id=account_id: message_handler(event, account_id), events.NewMessage())
        print(f"账号 {phone} 登录成功，用户ID: {own_user_id}")
        asyncio.create_task(client.run_until_disconnected())
        if current_account is None:
            current_account = account_id
            print(f"当前工作账号设置为：{current_account}")
    except Exception as e:
        logger.error(f"账号 {phone} 登录失败: {repr(e)}")
        print(f"账号 {phone} 登录失败: {repr(e)}")

async def remove_account():
    global ACCOUNTS, current_account
    account_id = (await ainput("请输入要移除的账号标识（例如手机号）: ")).strip()
    if account_id in ACCOUNTS:
        account = ACCOUNTS.pop(account_id)
        try:
            await account["client"].disconnect()
            print(f"账号 {account_id} 已成功移除并断开连接。")
            if current_account == account_id:
                current_account = None
        except Exception as e:
            logger.error(f"断开账号 {account_id} 时出错: {repr(e)}")
            print(f"断开账号 {account_id} 时出错: {repr(e)}")
    else:
        print("未找到该账号。")

async def list_accounts():
    if not ACCOUNTS:
        print("当前没有登录的账号。")
    else:
        print("=== 已登录账号列表 ===")
        for idx, (account_id, info) in enumerate(ACCOUNTS.items(), start=1):
            print(f"{idx}. 电话: {info['phone']}, 用户ID: {info['own_user_id']}")

def ensure_keyword_config_defaults(keyword_cfg):
    if 'reply_enabled' not in keyword_cfg:
        keyword_cfg['reply_enabled'] = False
    if 'reply_texts' not in keyword_cfg:
        keyword_cfg['reply_texts'] = []
    if 'reply_delay_min' not in keyword_cfg:
        keyword_cfg['reply_delay_min'] = 0
    if 'reply_delay_max' not in keyword_cfg:
        keyword_cfg['reply_delay_max'] = 0
    return keyword_cfg
    
async def export_all_configs():
    global ACCOUNTS
    filepath = (await ainput("请输入导出所有账号配置文件的路径: ")).strip()
    if os.path.isdir(filepath):
        filepath = os.path.join(filepath, "all_configs.json")
    all_configs = {}
    for account_id, info in ACCOUNTS.items():
        all_configs[account_id] = {
            "phone": info["phone"],
            "config": info["config"]
        }
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(all_configs, f, ensure_ascii=False, indent=4)
        print(f"所有账号配置已导出到 {filepath}")
    except Exception as e:
        logger.error(f"导出配置时发生错误：{repr(e)}")
        print(f"导出配置时发生错误：{repr(e)}")

async def import_all_configs():
    global ACCOUNTS
    filepath = (await ainput("请输入要导入配置文件的路径: ")).strip()
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            all_configs = json.load(f)
        
        account_keys = list(all_configs.keys())
        print("配置文件中包含以下账号：")
        for idx, account_id in enumerate(account_keys, start=1):
            print(f"{idx}. {account_id}")
        selection = (await ainput("请输入要导入配置的账号序号（多个逗号分隔）： ")).strip()
        selected_numbers = [s.strip() for s in selection.split(',') if s.strip()]
        selected_ids = []
        for num_str in selected_numbers:
            if num_str.isdigit():
                index = int(num_str) - 1
                if 0 <= index < len(account_keys):
                    selected_ids.append(account_keys[index])
                else:
                    print(f"无效的序号: {num_str}")
            else:
                print(f"无效输入: {num_str}")
        imported = 0
        for account_id in selected_ids:
            if account_id in all_configs:
                config = all_configs[account_id]["config"]
                keyword_cfg = config.get("keyword_config", {})
                for key, cfg_item in keyword_cfg.items():
                    if 'max_executions' not in cfg_item:
                        cfg_item['max_executions'] = None
                    if 'execution_count' not in cfg_item:
                        cfg_item['execution_count'] = 0
                    if 'blocked_users' not in cfg_item:
                        cfg_item['blocked_users'] = []
                    if 'reply_enabled' not in cfg_item:
                        cfg_item['reply_enabled'] = False
                    if 'reply_texts' not in cfg_item:
                        cfg_item['reply_texts'] = []
                    if 'reply_delay_min' not in cfg_item:
                        cfg_item['reply_delay_min'] = 0
                    if 'reply_delay_max' not in cfg_item:
                        cfg_item['reply_delay_max'] = 0
                config["keyword_config"] = keyword_cfg

                ext_cfg = config.get("file_extension_config", {})
                for key, cfg_item in ext_cfg.items():
                    if 'max_executions' not in cfg_item:
                        cfg_item['max_executions'] = None
                    if 'execution_count' not in cfg_item:
                        cfg_item['execution_count'] = 0
                    if 'blocked_users' not in cfg_item:
                        cfg_item['blocked_users'] = []
                    if 'save_folder' not in cfg_item:
                        cfg_item['save_folder'] = None
                    if 'min_size' not in cfg_item:
                        cfg_item['min_size'] = None
                    if 'max_size' not in cfg_item:
                        cfg_item['max_size'] = None
                config["file_extension_config"] = ext_cfg

                all_msg_cfg = config.get("all_messages_config", {})
                new_all_msg_cfg = {}
                for chat_id_key, cfg_item in all_msg_cfg.items():
                    try:
                        chat_id_int = int(chat_id_key)
                    except Exception as e:
                        chat_id_int = chat_id_key
                    if 'max_executions' not in cfg_item:
                        cfg_item['max_executions'] = None
                    if 'execution_count' not in cfg_item:
                        cfg_item['execution_count'] = 0
                    if 'blocked_users' not in cfg_item:
                        cfg_item['blocked_users'] = []
                    new_all_msg_cfg[chat_id_int] = cfg_item
                config["all_messages_config"] = new_all_msg_cfg

                button_cfg = config.get("button_keyword_config", {})
                for button_keyword, b_config in button_cfg.items():
                    b_config['chats'] = set(b_config.get('chats', []))
                    b_config['users'] = set(b_config.get('users', []))
                config["button_keyword_config"] = button_cfg

                image_button_monitor = set(config.get("image_button_monitor", []))
                config["image_button_monitor"] = image_button_monitor

                scheduled_messages = config.get("scheduled_messages", [])
                config["scheduled_messages"] = scheduled_messages

                if account_id in ACCOUNTS:
                    ACCOUNTS[account_id]["config"] = config
                    imported += 1
                    for sched in config.get("scheduled_messages", []):
                        if not scheduler.get_job(sched["job_id"]):
                            try:
                                job = scheduler.add_job(
                                    send_scheduled_message,
                                    CronTrigger.from_crontab(sched['cron'], timezone=pytz.timezone('Asia/Shanghai')),
                                    args=[sched['target_id'], sched['message'],
                                          sched.get('random_offset', 0),
                                          sched.get('delete_after_sending', False),
                                          sched.get('account_id')],
                                    id=sched["job_id"]
                                )
                                logger.info(f"重新加载定时任务，Job ID: {job.id}")
                            except Exception as e:
                                logger.error(f"添加定时任务时出错: {e}")
                else:
                    print(f"当前系统中不存在账号 {account_id}，请先添加该账号")
            else:
                print(f"配置文件中未找到账号 {account_id}")
        print(f"已成功导入 {imported} 个账号的配置")
    except Exception as e:
        logger.error(f"导入配置时发生错误：{repr(e)}")
        print(f"导入配置时发生错误：{repr(e)}")
        
async def message_handler(event, account_id):
    account = ACCOUNTS.get(account_id)
    if not account:
        return
    if not account.get('monitor_active', False):
        return
    own_user_id = account["own_user_id"]
    keyword_config = account["config"]["keyword_config"]
    file_extension_config = account["config"]["file_extension_config"]
    all_messages_config = account["config"]["all_messages_config"]
    button_keyword_config = account["config"]["button_keyword_config"]
    image_button_monitor = set(account["config"]["image_button_monitor"])
    channel_in_group_config = account["config"].get("channel_in_group_config", [])

    chat_id = event.chat_id
    message_id = event.message.id
    if (account_id, chat_id, message_id) in processed_messages:
        return
    processed_messages.add((account_id, chat_id, message_id))
    def get_fwd_channel_id(fwd):
        if not fwd:
            return None
        if hasattr(fwd, 'from_chat') and fwd.from_chat is not None:
            return getattr(fwd.from_chat, 'id', None)
        if hasattr(fwd, 'from_id') and fwd.from_id:
            return getattr(fwd.from_id, 'channel_id', None)
        return None
    try:
        message_text = event.raw_text or ''
        message_text_lower = message_text.lower().strip()
        sender = await event.get_sender()
        if not sender:
            return
            
        sender_id = sender.id
        username = getattr(sender, 'username', '')
        if hasattr(sender, 'first_name'):
            name = f"{sender.first_name or ''} {sender.last_name or ''}".strip()
        else:
            name = getattr(sender, 'title', '')

        if getattr(sender, "bot", False) and sender_id in BLOCKED_BOTS:
            return
        if sender_id == own_user_id:
            return

        def is_not_blocked(config):
            if 'blocked_users' in config and str(sender_id) in config['blocked_users']:
                return False
            local_fwd = get_fwd_channel_id(event.message.fwd_from)
            if local_fwd is not None and 'blocked_channels' in config and local_fwd in config['blocked_channels']:
                return False
            if 'blocked_bots' in config and sender_id in config['blocked_bots']:
                return False
            return True
        def should_listen(config, sender, event):
            user_filter = config.get('users', [])
            bot_filter = config.get('match_bots', [])
            channel_filter = config.get('match_channels', [])
            if not (user_filter or bot_filter or channel_filter):
                return True
            allowed = False
            if user_filter and match_user(sender, set(user_filter), config.get('user_option')):
                allowed = True
            if not allowed and bot_filter and getattr(sender, "bot", False) and sender_id in bot_filter:
                allowed = True
            if not allowed:
                local_fwd = get_fwd_channel_id(event.message.fwd_from)
                if local_fwd is None and isinstance(sender, Channel):
                    local_fwd = sender.id
                if channel_filter and local_fwd is not None and local_fwd in channel_filter:
                    allowed = True
            return allowed
        if chat_id in all_messages_config:
            config = all_messages_config[chat_id]
            if is_not_blocked(config) and should_listen(config, sender, event):
                logger.info(f"匹配到全量监控消息: 对话ID={chat_id}, 发送者: id={sender_id}, 名称={name}, 用户名={username}")
                if config.get('email_notify'):
                    send_email(f"检测到来自对话 {chat_id} 的消息: {message_text}")
                if config.get('auto_forward'):
                    for target_id in config.get('forward_targets', []):
                        await account["client"].forward_messages(target_id, event.message)
                if config.get('log_file'):
                    try:
                        with open(config.get('log_file'), 'a', encoding='utf-8') as f:
                            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 全量监控 - 对话 {chat_id} 消息: {message_text}\n")
                    except Exception as e:
                        logger.error(f"写入全量监控文件时出错: {e}")
                if config.get('reply_enabled'):
                    delay = (random.uniform(config.get('reply_delay_min', 0), config.get('reply_delay_max', 0))
                             if config.get('reply_delay_max', 0) > config.get('reply_delay_min', 0)
                             else config.get('reply_delay_min', 0))
                    if delay > 0:
                        await asyncio.sleep(delay)
                    reply_texts = config.get('reply_texts', [])
                    if reply_texts:
                        reply_msg = random.choice(reply_texts)
                        await event.message.reply(reply_msg)
                if config.get('max_executions'):
                    config['execution_count'] = config.get('execution_count', 0) + 1
                    if config['execution_count'] >= config['max_executions']:
                        del all_messages_config[chat_id]
                        logger.info(f"全量监控配置（对话ID={chat_id}）已达到最大执行次数，自动删除")

        if isinstance(event.chat, Chat):
            local_fwd = get_fwd_channel_id(event.message.fwd_from)
            if local_fwd is None and isinstance(sender, Channel):
                local_fwd = sender.id
            if local_fwd and local_fwd in channel_in_group_config:
                logger.info(f"匹配到频道发言: 对话ID={chat_id}, 频道ID={local_fwd}")
                if chat_id in all_messages_config:
                    config = all_messages_config[chat_id]
                    if config.get('email_notify'):
                        send_email(f"检测到指定频道 {local_fwd} 在群聊中的消息: {message_text}")
                    if config.get('log_file'):
                        try:
                            with open(config.get('log_file'), 'a', encoding='utf-8') as f:
                                f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 频道转发 - 对话 {chat_id} 消息: {message_text}\n")
                        except Exception as e:
                            logger.error(f"写入频道转发文件时出错: {e}")
                else:
                    send_email(f"检测到指定频道 {local_fwd} 在群聊中的消息: {message_text}")
                    
        handled = False
        for keyword, config in keyword_config.items():
            if chat_id not in config.get('chats', []):
                continue
            if not is_not_blocked(config) or not should_listen(config, sender, event):
                continue
            mtype = config.get('match_type', 'partial')
            normal_match = False
            if mtype == 'exact' and message_text_lower == keyword:
                normal_match = True
            elif mtype == 'partial' and keyword in message_text_lower:
                normal_match = True
            elif mtype == 'regex':
                pattern = re.compile(rf'{keyword}')
                if pattern.search(message_text):
                    normal_match = True
            if normal_match:
                logger.info(f"匹配到关键词 '{keyword}': 对话ID={chat_id}, 发送者: id={sender_id}, 名称={name}, 用户名={username}")
                if config.get('email_notify'):
                    send_email(f"检测到关键词 '{keyword}' 的消息: {message_text}")
                if config.get('auto_forward'):
                    await auto_forward_message(event, keyword, account_id)
                if config.get('log_file'):
                    try:
                        with open(config.get('log_file'), 'a', encoding='utf-8') as f:
                            if mtype == 'exact':
                                f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 对话 {chat_id} 完全匹配 '{keyword}': {message_text}\n")
                            elif mtype == 'partial':
                                f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 对话 {chat_id} 关键词 '{keyword}': {message_text}\n")
                            else:
                                f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 对话 {chat_id} 正则匹配 '{keyword}': {message_text}\n")
                    except Exception as e:
                        logger.error(f"写入关键词匹配文件时出错: {e}")
                if config.get('reply_enabled'):
                    delay = (random.uniform(config.get('reply_delay_min', 0), config.get('reply_delay_max', 0))
                             if config.get('reply_delay_max', 0) > config.get('reply_delay_min', 0)
                             else config.get('reply_delay_min', 0))
                    if delay > 0:
                        await asyncio.sleep(delay)
                    reply_texts = config.get('reply_texts', [])
                    if reply_texts:
                        reply_msg = random.choice(reply_texts)
                        await event.message.reply(reply_msg)
                if config.get('max_executions'):
                    config['execution_count'] = config.get('execution_count', 0) + 1
                    if config['execution_count'] >= config['max_executions']:
                        del keyword_config[keyword]
                        logger.info(f"关键词配置 '{keyword}' 达到最大执行次数，已删除")
                handled = True
                break

        if not handled:
            if event.message.media and isinstance(event.message.media, MessageMediaDocument):
                file_attr = event.message.media.document.attributes
                file_name = None
                for attr in file_attr:
                    if hasattr(attr, 'file_name'):
                        file_name = attr.file_name
                        break
                if file_name:
                    file_extension = os.path.splitext(file_name)[1].lower()
                    config = file_extension_config.get(file_extension)
                    if config and chat_id in config['chats']:
                        if is_not_blocked(config) and should_listen(config, sender, event):
                            user_set = set(config.get('users', []))
                            user_option = config.get('user_option')
                            if not match_user(sender, user_set, user_option):
                                return
                            logger.info(f"匹配到文件后缀监控: 对话ID={chat_id}, 文件后缀={file_extension}, 文件名={file_name}")
                            if config.get('email_notify'):
                                send_email(f"检测到文件后缀名 '{file_extension}' 的消息：{file_name}")
                            if config.get('auto_forward'):
                                await auto_forward_file_message(event, file_extension, account_id)
                        
                            if config.get('save_folder'):
                                # 获取文件大小（单位：字节），转换为 MB
                                file_size = event.message.media.document.size
                                file_size_mb = file_size / (1024 * 1024)
                                min_size = config.get('min_size')
                                max_size = config.get('max_size')
                                size_ok = True
                                if min_size is not None and file_size_mb < min_size:
                                    size_ok = False
                                if max_size is not None and file_size_mb > max_size:
                                    size_ok = False
                                if size_ok:
                                    save_folder = config.get('save_folder')
                                    os.makedirs(save_folder, exist_ok=True)
                                    file_path = await event.message.download_media(file=save_folder)
                                    logger.info(f"已保存文件 '{file_name}' 到: {file_path}")
                                else:
                                    logger.info(f"文件大小 {file_size_mb:.2f} MB 不在设定范围内，未保存文件")
                            
                            if config.get('max_executions'):
                                config['execution_count'] = config.get('execution_count', 0) + 1
                                if config['execution_count'] >= config['max_executions']:
                                    del file_extension_config[file_extension]
                                    logger.info(f"文件后缀配置 '{file_extension}' 达到最大执行次数，已删除")

        if event.message.buttons:
            for b_keyword, b_config in button_keyword_config.items():
                if chat_id in b_config['chats']:
                    if match_user(sender, b_config.get('users', set()), b_config.get('user_option')):
                        for row_i, row in enumerate(event.message.buttons):
                            for col_i, button in enumerate(row):
                                if b_keyword in button.text.lower():
                                    await event.message.click(row_i, col_i)
                                    logger.info(f"已点击对话 {chat_id} 中包含按钮关键词 '{b_keyword}' 的按钮: {button.text}")
                                    return
        if chat_id in image_button_monitor and event.message.buttons:
            image_path = None
            if event.message.photo or (event.message.document and 'image' in event.message.document.mime_type):
                image_path = await event.message.download_media()
            if image_path and event.message.buttons:
                base, ext = os.path.splitext(image_path)
                if ext.lower() != '.jpg':
                    new_image_path = base + '.jpg'
                    shutil.move(image_path, new_image_path)
                    image_path = new_image_path
                options = []
                for row in event.message.buttons:
                    for button in row:
                        options.append(button.text.strip())
                prompt_options = "\n".join(options)
                ai_prompt = f"请根据图中的内容从下列选项中选出符合图片的选项，你的回答只需要包含选项的内容，不用包含其他内容：\n{prompt_options}"
                def encode_image(image_path):
                    with open(image_path, "rb") as image_file:
                        return base64.b64encode(image_file.read()).decode("utf-8")
                base64_image = encode_image(image_path)
                messages = [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": ai_prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpg;base64,{base64_image}"}}
                        ]
                    }
                ]
                max_retries = 2
                attempt = 0
                ai_answer = None
                while attempt < max_retries:
                    attempt += 1
                    try:
                        response = client_ai.chat.completions.create(
                            model="gpt-4o",
                            messages=messages
                        )
                        ai_answer = response.choices[0].message.content.strip()
                        logger.info(f"AI模型返回的内容: {ai_answer}")
                        break
                    except Exception as e:
                        logger.error(f"AI模型调用时发生错误(第{attempt}次): {e}")
                        if attempt < max_retries:
                            logger.info("10秒后重试上传给AI模型...")
                            await asyncio.sleep(10)
                        else:
                            logger.info("多次尝试仍失败，放弃上传给AI模型。")
                            try:
                                if os.path.exists(image_path):
                                    os.remove(image_path)
                                    logger.info(f"已删除图片文件：{image_path}")
                            except Exception as e:
                                logger.error(f"删除图片文件时发生错误: {e}")
                            return
                if ai_answer is None:
                    return
                for row_i, row in enumerate(event.message.buttons):
                    for col_i, button in enumerate(row):
                        if button.text.strip() == ai_answer:
                            await event.message.click(row_i, col_i)
                            logger.info(f"已点击AI模型选择的按钮: {button.text}")
                            break
                try:
                    if os.path.exists(image_path):
                        os.remove(image_path)
                        logger.info(f"已删除图片文件：{image_path}")
                except Exception as e:
                    logger.error(f"删除图片文件时发生错误: {e}")
    except Exception as e:
        logger.error(f"处理消息时出错：{repr(e)}")

async def auto_forward_message(event, keyword, account_id):
    try:
        config = ACCOUNTS[account_id]["config"]["keyword_config"].get(keyword, {})
        target_ids = config.get('forward_targets', [])
        chat_id = event.chat_id
        if account_id and account_id in ACCOUNTS:
            client_instance = ACCOUNTS[account_id]["client"]
        else:
            logger.error("auto_forward_message 未指定有效账号")
            return
        for target_id in target_ids:
            if target_id == chat_id:
                logger.info(f"转发目标ID({target_id})与监控群组({chat_id})相同，跳过转发以避免循环。")
                continue
            await client_instance.forward_messages(target_id, event.message)
            logger.info(f"已将关键词 '{keyword}' 消息转发到ID: {target_id}")
    except Exception as e:
        error_message = repr(e)
        logger.error(f"自动转发消息时发生错误：{error_message}")

async def auto_forward_file_message(event, file_extension, account_id):
    try:
        config = ACCOUNTS[account_id]["config"]["file_extension_config"].get(file_extension, {})
        target_ids = config.get('forward_targets', [])
        chat_id = event.chat_id
        if account_id and account_id in ACCOUNTS:
            client_instance = ACCOUNTS[account_id]["client"]
        else:
            logger.error("auto_forward_file_message 未指定有效账号")
            return
        for target_id in target_ids:
            if target_id == chat_id:
                logger.info(f"转发目标ID({target_id})与监控群组({chat_id})相同，跳过转发以避免循环。")
                continue
            await client_instance.forward_messages(target_id, event.message)
            logger.info(f"已将包含文件 {file_extension} 的消息转发到ID: {target_id}")
    except Exception as e:
        error_message = repr(e)
        logger.error(f"自动转发文件消息时发生错误：{error_message}")

def schedule_message(target_id, message, cron_expression, random_offset=0, delete_after_sending=False, account_id=None):
    job = scheduler.add_job(
        send_scheduled_message,
        CronTrigger.from_crontab(cron_expression, timezone=pytz.timezone('Asia/Shanghai')),
        args=[target_id, message, random_offset, delete_after_sending, account_id]
    )
    logger.info(f"已添加定时消息，Cron表达式: {cron_expression}，目标ID: {target_id}，账号: {account_id}")
    return job

async def send_scheduled_message(target_id, message, random_offset=0, delete_after_sending=False, account_id=None):
    try:
        if random_offset > 0:
            delay = random.uniform(0, random_offset)
            logger.info(f"等待 {delay:.2f} 秒后发送定时消息")
            await asyncio.sleep(delay)
        if account_id and account_id in ACCOUNTS:
            client_instance = ACCOUNTS[account_id]["client"]
        else:
            logger.error("send_scheduled_message 未指定有效账号")
            return
        sent_message = await client_instance.send_message(target_id, message)
        logger.info(f"已发送定时消息到ID: {target_id}，账号: {account_id}")
        if delete_after_sending:
            await asyncio.sleep(5)
            await client_instance.delete_messages(target_id, sent_message.id)
            logger.info(f"已删除发送的定时消息，消息ID: {sent_message.id}")
    except Exception as e:
        error_message = repr(e)
        logger.error(f"发送定时消息时发生错误：{error_message}")

async def handle_commands():
    global monitor_active, ACCOUNTS, current_account
    short_prompt = "请输入命令 (输入 help 查看详细命令): "
    full_commands = """
=== 可用命令 ===
addaccount         - 添加新账号
removeaccount      - 移除账号
listaccount        - 列出所有账号
switchaccount      - 切换当前工作账号
exportconfig       - 导出当前账号配置
importconfig       - 导入当前账号配置
blockbot           - 屏蔽指定 TG Bot（输入 bot id）
unblockbot         - 取消屏蔽 TG Bot
list               - 列出当前账号的所有频道和群组对话
addkeyword         - 添加关键词监控配置
modifykeyword      - 修改关键词监控配置
removekeyword      - 移除关键词监控配置
showkeywords       - 显示当前账号所有关键词配置
addext             - 添加文件后缀监控配置
modifyext          - 修改文件后缀监控配置
removeext          - 移除文件后缀监控配置
showext            - 显示当前账号所有文件后缀监控配置
addall             - 添加全量监控配置（频道或群组）
modifyall          - 修改全量监控配置
removeall          - 移除全量监控配置
showall            - 显示当前账号所有全量监控配置
addbutton          - 添加按钮关键词监控配置
modifybutton       - 修改按钮关键词监控配置
removebutton       - 移除按钮关键词监控配置
showbuttons        - 显示当前账号所有按钮关键词配置
listchats          - 列出当前账号与 Bot 的对话 chat_id
addlistener        - 添加图片+按钮监听的对话ID
removelistener     - 移除图片+按钮监听的对话ID
showlistener       - 显示当前账号所有图片+按钮监听对话ID
schedule           - 添加定时消息配置
modifyschedule     - 修改定时消息配置
removeschedule     - 删除定时消息配置
showschedule       - 显示当前账号所有定时消息配置
start              - 开始监控
stop               - 停止监控
exit               - 退出程序
"""
    while True:
        command = (await ainput(short_prompt)).strip().lower()
        if command == "help":
            print(full_commands)
            continue
        try:
            if command == 'addaccount':
                await add_account()
            elif command == 'removeaccount':
                await remove_account()
            elif command == 'listaccount':
                await list_accounts()
            elif command == 'switchaccount':
                if not ACCOUNTS:
                    print("当前没有登录的账号")
                    continue
                accounts_list = list(ACCOUNTS.keys())
                print("=== 已登录账号列表 ===")
                for idx, account_id in enumerate(accounts_list, start=1):
                    info = ACCOUNTS[account_id]
                    print(f"{idx}. 电话: {info['phone']}, 用户ID: {info['own_user_id']}")
                selection = (await ainput("请输入要切换到的账号序号: ")).strip()
                if selection.isdigit():
                    index = int(selection) - 1
                    if 0 <= index < len(accounts_list):
                        current_account = accounts_list[index]
                        print(f"当前工作账号已切换为：{current_account}")
                    else:
                        print("无效的序号")
                else:
                    print("请输入数字序号")
            elif command == 'exportconfig':
                await export_all_configs()
            elif command == 'importconfig':
                await import_all_configs()
            elif command == 'blockbot':
                bot_id_str = (await ainput("请输入要屏蔽的 TG Bot 的 bot id: ")).strip()
                if bot_id_str.isdigit():
                    BLOCKED_BOTS.add(int(bot_id_str))
                    print(f"已屏蔽 TG Bot: {bot_id_str}")
                else:
                    print("无效的 bot id")
            elif command == 'unblockbot':
                bot_id_str = (await ainput("请输入要取消屏蔽的 TG Bot 的 bot id: ")).strip()
                if bot_id_str.isdigit():
                    bot_id = int(bot_id_str)
                    if bot_id in BLOCKED_BOTS:
                        BLOCKED_BOTS.remove(bot_id)
                        print(f"已取消屏蔽 TG Bot: {bot_id_str}")
                    else:
                        print("该 bot id 未被屏蔽")
                else:
                    print("无效的 bot id")
            elif command == 'list':
                if current_account is None:
                    print("当前没有选定工作账号")
                    continue
                print(f"\n=== 当前账号 {current_account} 的所有对话 ===")
                async for dialog in ACCOUNTS[current_account]["client"].iter_dialogs():
                    if isinstance(dialog.entity, (Channel, Chat)):
                        print(f"ID: {dialog.id}, 名称: {dialog.name}, 类型: {'频道' if isinstance(dialog.entity, Channel) else '群组'}")
            elif command == 'addkeyword':
                if current_account is None:
                    print("请先切换或添加账号")
                    continue
                cfg = ACCOUNTS[current_account]["config"]["keyword_config"]
            
                print("\n请选择关键词匹配类型：")
                print("1. 完全匹配")
                print("2. 关键词匹配")
                print("3. 正则表达式匹配")
                match_option = (await ainput("请输入匹配类型编号 (1/2/3): ")).strip()
                if match_option == '1':
                    match_type = 'exact'
                elif match_option == '2':
                    match_type = 'partial'
                elif match_option == '3':
                    match_type = 'regex'
                else:
                    print("无效的匹配类型，默认使用关键词匹配")
                    match_type = 'partial'
                    
                if match_type != 'regex':
                    keywords_input = (await ainput("请输入关键词，多个关键词用逗号分隔: ")).strip()
                    keywords = [kw.strip().lower() for kw in keywords_input.split(',')]
                else:
                    keywords_input = (await ainput("请输入正则表达式模式（不使用逗号分隔）: ")).strip()
                    keywords = [keywords_input.strip()]
                    
                chat_ids_input = (await ainput("请输入要监听的对话ID（多个逗号分隔）： ")).strip()
                chat_ids = [int(x.strip()) for x in chat_ids_input.split(',')]
                
                print("\n请选择要监控用户其类型： 1. 用户ID(频道id或Bot id)  2. 用户名  3. 昵称")
                user_option = (await ainput("请输入选项编号（直接回车表示全部）： ")).strip()
                if user_option in ['1', '2', '3']:
                    users_input = (await ainput("请输入对应用户标识（回车则监控全部用户，多个逗号分隔）： ")).strip()
                    if users_input:
                        if user_option == '1':
                            user_set = [int(u.strip()) for u in users_input.split(',') if u.strip().isdigit()]
                        else:
                            user_set = [u.strip() for u in users_input.split(',')]
                    else:
                        user_set = []
                else:
                    user_option = None
                    user_set = []
                
                auto_forward = (await ainput("是否启用自动转发？(yes/no): ")).strip().lower() == 'yes'
                email_notify = (await ainput("是否启用邮件通知？(yes/no): ")).strip().lower() == 'yes'
                log_to_file = (await ainput("是否记录匹配消息到文件？(yes/no): ")).strip().lower() == 'yes'
                if log_to_file:
                    log_file = (await ainput("请输入文件名称： ")).strip()
                else:
                    log_file = None
                
                if auto_forward:
                    target_ids_input = (await ainput("请输入自动转发目标对话ID（多个逗号分隔）： ")).strip()
                    target_ids = [int(x.strip()) for x in target_ids_input.split(',')]
                else:
                    target_ids = []
                
                filter_choice = (await ainput("是否设置屏蔽过滤？(yes/no): ")).strip().lower() == 'yes'
                if filter_choice:
                    blocked_users_input = (await ainput("请输入屏蔽用户（用户ID，多个逗号分隔）： ")).strip()
                    blocked_users = [x.strip() for x in blocked_users_input.split(',')] if blocked_users_input else []
                else:
                    blocked_users = []
                
                execution_limit_input = (await ainput("请输入执行次数限制（正整数），直接回车表示不设置： ")).strip()
                if execution_limit_input.isdigit():
                    max_executions = int(execution_limit_input)
                else:
                    max_executions = None
            
                # 新增：回复功能配置
                reply_choice = (await ainput("是否启用回复功能？(yes/no): ")).strip().lower() == 'yes'
                if reply_choice:
                    reply_enabled = True
                    reply_texts_input = (await ainput("请输入回复词组，多个词组用逗号分隔: ")).strip()
                    reply_texts = [s.strip() for s in reply_texts_input.split(',')] if reply_texts_input else []
                    reply_delay_input = (await ainput("请输入回复延时范围（格式: min,max，单位秒）： ")).strip()
                    try:
                        reply_delay_min, reply_delay_max = map(float, reply_delay_input.split(','))
                    except Exception as e:
                        print("回复延时范围输入格式有误，默认设为0")
                        reply_delay_min = 0
                        reply_delay_max = 0
                else:
                    reply_enabled = False
                    reply_texts = []
                    reply_delay_min = 0
                    reply_delay_max = 0
            
                for keyword in keywords:
                    cfg[keyword] = {
                        'chats': chat_ids,
                        'auto_forward': auto_forward,
                        'email_notify': email_notify,
                        'match_type': match_type,
                        'users': user_set,
                        'user_option': user_option,
                        'forward_targets': target_ids,
                        'log_file': log_file,
                        'reply_enabled': reply_enabled,
                        'reply_texts': reply_texts,
                        'reply_delay_min': reply_delay_min,
                        'reply_delay_max': reply_delay_max,
                        'max_executions': max_executions,
                        'execution_count': 0,
                        'blocked_users': blocked_users,
                    }
                    if match_type == 'regex':
                        regex_send = (await ainput("是否发送正则匹配结果到指定对话？(yes/no): ")).strip().lower() == 'yes'
                        if regex_send:
                            cfg[keyword]['regex_send_target_id'] = int((await ainput("请输入目标对话ID: ")).strip())
                            random_offset_input = (await ainput("请输入随机延时（秒）： ")).strip()
                            cfg[keyword]['regex_send_random_offset'] = int(random_offset_input) if random_offset_input else 0
                            cfg[keyword]['regex_send_delete'] = (await ainput("发送后是否删除消息？(yes/no): ")).strip().lower() == 'yes'
                            print(f"正则匹配结果将发送到ID: {cfg[keyword]['regex_send_target_id']}, 延时: {cfg[keyword]['regex_send_random_offset']}秒, 删除后: {'是' if cfg[keyword]['regex_send_delete'] else '否'}")
                    print(f"已添加关键词 '{keyword}' 的配置： {cfg[keyword]}")


            elif command == 'modifykeyword':
                if current_account is None:
                    print("请先切换或添加账号")
                    continue
                cfg = ACCOUNTS[current_account]["config"]["keyword_config"]
                keyword_input = (await ainput("请输入要修改的关键词: ")).strip()
                if keyword_input in cfg:
                    config = cfg[keyword_input]
                    print(f"当前配置：{config}")
                    print("请输入要修改的项（逗号分隔）：")
                    print("1. 关键词  2. 监听对话ID  3. 自动转发  4. 邮件通知")
                    print("5. 匹配类型  6. 用户过滤  7. 文件记录  8. 回复功能")
                    print("9. 执行次数限制  10. 屏蔽过滤  ")
                    options = (await ainput("请输入修改项: ")).strip().split(',')
                    options = [x.strip() for x in options]
                    if '1' in options:
                        new_keyword = (await ainput("请输入新的关键词: ")).strip()
                        cfg[new_keyword] = cfg.pop(keyword_input)
                        keyword_input = new_keyword
                        print(f"关键词修改为： {new_keyword}")
                    if '2' in options:
                        chat_ids_input = (await ainput("请输入新的监听对话ID（多个逗号分隔）： ")).strip()
                        cfg[keyword_input]['chats'] = [int(x.strip()) for x in chat_ids_input.split(',')]
                        print("监听对话ID已更新")
                    if '3' in options:
                        auto_forward = (await ainput("是否启用自动转发？(yes/no): ")).strip().lower() == 'yes'
                        cfg[keyword_input]['auto_forward'] = auto_forward
                        if auto_forward:
                            target_ids_input = (await ainput("请输入自动转发目标对话ID（多个逗号分隔）： ")).strip()
                            cfg[keyword_input]['forward_targets'] = [int(x.strip()) for x in target_ids_input.split(',')]
                        else:
                            cfg[keyword_input]['forward_targets'] = []
                    if '4' in options:
                        email_notify = (await ainput("是否启用邮件通知？(yes/no): ")).strip().lower() == 'yes'
                        cfg[keyword_input]['email_notify'] = email_notify
                    if '5' in options:
                        print("请选择匹配类型： 1. 完全匹配  2. 关键词匹配  3. 正则匹配")
                        match_option = (await ainput("请输入匹配类型编号: ")).strip()
                        if match_option == '1':
                            cfg[keyword_input]['match_type'] = 'exact'
                        elif match_option == '2':
                            cfg[keyword_input]['match_type'] = 'partial'
                        elif match_option == '3':
                            cfg[keyword_input]['match_type'] = 'regex'
                        else:
                            print("输入无效，匹配类型保持不变")
                    if '6' in options:
                        print("请选择要监控用户其类型： 1. 用户ID(频道i或Bot id)  2. 用户名  3. 昵称")
                        user_option = (await ainput("请输入用户类型编号: ")).strip()
                        users_input = (await ainput("请输入对应用户标识（多个逗号分隔）： ")).strip()
                        if users_input:
                            if user_option == '1':
                                cfg[keyword_input]['users'] = [int(x.strip()) for x in users_input.split(',') if x.strip().isdigit()]
                            else:
                                cfg[keyword_input]['users'] = [x.strip() for x in users_input.split(',')]
                        else:
                            cfg[keyword_input]['users'] = []
                        cfg[keyword_input]['user_option'] = user_option
                    if '7' in options:
                        log_to_file = (await ainput("是否记录匹配消息到文件？(yes/no): ")).strip().lower() == 'yes'
                        if log_to_file:
                            log_file = (await ainput("请输入文件名称： ")).strip()
                            cfg[keyword_input]['log_file'] = log_file
                        else:
                            cfg[keyword_input].pop('log_file', None)
                    if '8' in options:
                        reply_enabled = (await ainput("是否启用回复？(yes/no): ")).strip().lower() == 'yes'
                        cfg[keyword_input]['reply_enabled'] = reply_enabled
                        if reply_enabled:
                            reply_texts_input = (await ainput("请输入回复词组，多个词组用逗号分隔: ")).strip()
                            cfg[keyword_input]['reply_texts'] = [s.strip() for s in reply_texts_input.split(',')]
                            reply_delay_input = (await ainput("请输入回复延时范围（格式: min,max，单位秒）： ")).strip()
                            try:
                                reply_delay_min, reply_delay_max = map(float, reply_delay_input.split(','))
                            except Exception as e:
                                print("回复延时范围输入格式有误，默认设为0")
                                reply_delay_min = 0
                                reply_delay_max = 0
                            cfg[keyword_input]['reply_delay_min'] = reply_delay_min
                            cfg[keyword_input]['reply_delay_max'] = reply_delay_max
                        else:
                            cfg[keyword_input]['reply_texts'] = []
                            cfg[keyword_input]['reply_delay_min'] = 0
                            cfg[keyword_input]['reply_delay_max'] = 0
                    if '9' in options:
                        execution_limit_input = (await ainput("请输入新的执行次数限制（正整数），直接回车表示不设置： ")).strip()
                        if execution_limit_input.isdigit():
                            cfg[keyword_input]['max_executions'] = int(execution_limit_input)
                        else:
                            cfg[keyword_input]['max_executions'] = None
                        cfg[keyword_input]['execution_count'] = 0
                    if '10' in options:
                        filter_choice = (await ainput("是否设置屏蔽过滤？(yes/no): ")).strip().lower() == 'yes'
                        if filter_choice:
                            blocked_users_input = (await ainput("请输入屏蔽用户、频道或Bot（ID，多个逗号分隔）： ")).strip()
                            blocked_users = [x.strip() for x in blocked_users_input.split(',')] if blocked_users_input else []
                        else:
                            blocked_users = []
                        cfg[keyword_input]['blocked_users'] = blocked_users
                    print(f"关键词 '{keyword_input}' 的新配置： {cfg[keyword_input]}")
                else:
                    print("未找到该关键词配置")

            elif command == 'removekeyword':
                if current_account is None:
                    print("请先切换或添加账号")
                    continue
                cfg = ACCOUNTS[current_account]["config"]["keyword_config"]
                keyword_input = (await ainput("请输入要移除的关键词: ")).strip()
                if keyword_input in cfg:
                    del cfg[keyword_input]
                    print(f"已移除关键词 '{keyword_input}'")
                else:
                    print("未找到该关键词配置")

            elif command == 'showkeywords':
                if current_account is None:
                    print("请先切换或添加账号")
                    continue
                cfg = ACCOUNTS[current_account]["config"]["keyword_config"]
                print("\n=== 当前关键词配置 ===")
                for k, v in cfg.items():
                    print(f"{k} : {v}")
                    
            elif command == 'addext':
                if current_account is None:
                    print("请先切换或添加账号")
                    continue
                cfg = ACCOUNTS[current_account]["config"]["file_extension_config"]
                extensions_input = (await ainput("请输入文件后缀（多个逗号分隔）： ")).strip().lower()
                extensions = [ext.strip() if ext.startswith('.') else '.' + ext.strip() for ext in extensions_input.split(',')]
                chat_ids_input = (await ainput("请输入监听对话ID（多个逗号分隔）： ")).strip()
                chat_ids = [int(x.strip()) for x in chat_ids_input.split(',')]
                print("请选择要监控用户其类型： 1. 用户ID(频道id或Bot id)  2. 用户名  3. 昵称")
                user_option = (await ainput("请输入选项编号（可留空表示全部）： ")).strip()
                if user_option in ['1', '2', '3']:
                    users_input = (await ainput("请输入对应用户标识（多个逗号分隔）： ")).strip()
                    if users_input:
                        if user_option == '1':
                            user_set = [int(x.strip()) for x in users_input.split(',') if x.strip().isdigit()]
                        else:
                            user_set = [x.strip() for x in users_input.split(',')]
                    else:
                        user_set = []
                else:
                    user_option = None
                    user_set = []
                auto_forward = (await ainput("启用自动转发？(yes/no): ")).strip().lower() == 'yes'
                email_notify = (await ainput("启用邮件通知？(yes/no): ")).strip().lower() == 'yes'
                if auto_forward:
                    target_ids_input = (await ainput("请输入转发目标对话ID（多个逗号分隔）： ")).strip()
                    target_ids = [int(x.strip()) for x in target_ids_input.split(',')]
                else:
                    target_ids = []
                filter_choice = (await ainput("是否设置屏蔽过滤？(yes/no): ")).strip().lower() == 'yes'
                if filter_choice:
                    blocked_users_input = (await ainput("请输入屏蔽用户、频道或Bot（ID，多个逗号分隔）： ")).strip()
                    blocked_users = [x.strip() for x in blocked_users_input.split(',')] if blocked_users_input else []
                else:
                    blocked_users = []
                execution_limit_input = (await ainput("请输入执行次数限制（正整数），直接回车表示不设置： ")).strip()
                if execution_limit_input.isdigit():
                    max_executions = int(execution_limit_input)
                else:
                    max_executions = None
                save_choice = (await ainput("是否保存匹配到的文件到本地？(yes/no): ")).strip().lower() == 'yes'
                if save_choice:
                    save_folder = (await ainput("请输入保存文件的本地文件夹路径: ")).strip()
                    size_limit_choice = (await ainput("是否设置文件大小范围限制？(yes/no): ")).strip().lower() == 'yes'
                    if size_limit_choice:
                        min_size_input = (await ainput("请输入文件最小大小（MB）： ")).strip()
                        max_size_input = (await ainput("请输入文件最大大小（MB）： ")).strip()
                        try:
                            min_size = float(min_size_input) if min_size_input else None
                        except:
                            min_size = None
                        try:
                            max_size = float(max_size_input) if max_size_input else None
                        except:
                            max_size = None
                    else:
                        min_size = None
                        max_size = None
                else:
                    save_folder = None
                    min_size = None
                    max_size = None

                for ext in extensions:
                    cfg[ext] = {
                        'chats': chat_ids,
                        'auto_forward': auto_forward,
                        'email_notify': email_notify,
                        'users': user_set,
                        'user_option': user_option,
                        'forward_targets': target_ids,
                        'max_executions': max_executions,
                        'execution_count': 0,
                        'blocked_users': blocked_users,
                        'save_folder': save_folder,
                        'min_size': min_size,
                        'max_size': max_size,
                    }
                    print(f"已添加文件后缀 '{ext}' 的配置： {cfg[ext]}")

            elif command == 'modifyext':
                if current_account is None:
                    print("请先切换或添加账号")
                    continue
                cfg = ACCOUNTS[current_account]["config"]["file_extension_config"]
                ext = (await ainput("请输入要修改的文件后缀（如 .pdf）： ")).strip().lower()
                if not ext.startswith('.'):
                    ext = '.' + ext
                if ext in cfg:
                    config = cfg[ext]
                    print(f"当前配置：{config}")
                    print("请输入要修改的项（逗号分隔）：")
                    print("1. 文件后缀")
                    print("2. 监听对话ID")
                    print("3. 自动转发")
                    print("4. 邮件通知")
                    print("5. 用户过滤")
                    print("6. 执行次数限制")
                    print("7. 屏蔽过滤")
                    print("8. 保存文件设置（包括保存路径及大小限制）")
                    options = (await ainput("请输入修改项: ")).strip().split(',')
                    options = [x.strip() for x in options]
                    if '1' in options:
                        new_ext = (await ainput("请输入新的文件后缀: ")).strip().lower()
                        if not new_ext.startswith('.'):
                            new_ext = '.' + new_ext
                        cfg[new_ext] = cfg.pop(ext)
                        ext = new_ext
                        print(f"文件后缀修改为： {new_ext}")
                    if '2' in options:
                        chat_ids_input = (await ainput("请输入新的监听对话ID（多个逗号分隔）： ")).strip()
                        cfg[ext]['chats'] = [int(x.strip()) for x in chat_ids_input.split(',')]
                        print("监听对话ID已更新")
                    if '3' in options:
                        auto_forward = (await ainput("是否启用自动转发？(yes/no): ")).strip().lower() == 'yes'
                        cfg[ext]['auto_forward'] = auto_forward
                        if auto_forward:
                            target_ids_input = (await ainput("请输入自动转发目标对话ID（多个逗号分隔）： ")).strip()
                            cfg[ext]['forward_targets'] = [int(x.strip()) for x in target_ids_input.split(',')]
                        else:
                            cfg[ext]['forward_targets'] = []
                    if '4' in options:
                        email_notify = (await ainput("是否启用邮件通知？(yes/no): ")).strip().lower() == 'yes'
                        cfg[ext]['email_notify'] = email_notify
                    if '5' in options:
                        print("请选择要监控用户其类型： 1. 用户ID(频道id或Bot id)  2. 用户名  3. 昵称")
                        user_option = (await ainput("请输入用户类型编号: ")).strip()
                        users_input = (await ainput("请输入对应用户标识（多个逗号分隔）： ")).strip()
                        if users_input:
                            if user_option == '1':
                                cfg[ext]['users'] = [int(x.strip()) for x in users_input.split(',') if x.strip().isdigit()]
                            else:
                                cfg[ext]['users'] = [x.strip() for x in users_input.split(',')]
                        else:
                            cfg[ext]['users'] = []
                        cfg[ext]['user_option'] = user_option
                    if '6' in options:
                        execution_limit_input = (await ainput("请输入新的执行次数限制（正整数），直接回车表示不设置： ")).strip()
                        if execution_limit_input.isdigit():
                            cfg[ext]['max_executions'] = int(execution_limit_input)
                        else:
                            cfg[ext]['max_executions'] = None
                        cfg[ext]['execution_count'] = 0
                    if '7' in options:
                        filter_choice = (await ainput("是否设置屏蔽过滤？(yes/no): ")).strip().lower() == 'yes'
                        if filter_choice:
                            blocked_users_input = (await ainput("请输入屏蔽用户、频道或Bot（ID，多个逗号分隔）： ")).strip()
                            blocked_users = [x.strip() for x in blocked_users_input.split(',')] if blocked_users_input else []
                        else:
                            blocked_users = []
                        cfg[ext]['blocked_users'] = blocked_users
                    if '8' in options:
                        save_choice = (await ainput("是否启用保存文件到本地？(yes/no): ")).strip().lower() == 'yes'
                        if save_choice:
                            save_folder = (await ainput("请输入保存文件的本地文件夹路径: ")).strip()
                            size_limit_choice = (await ainput("是否设置文件大小范围限制？(yes/no): ")).strip().lower() == 'yes'
                            if size_limit_choice:
                                min_size_input = (await ainput("请输入文件最小大小（MB）： ")).strip()
                                max_size_input = (await ainput("请输入文件最大大小（MB）： ")).strip()
                                try:
                                    min_size = float(min_size_input) if min_size_input else None
                                except:
                                    min_size = None
                                try:
                                    max_size = float(max_size_input) if max_size_input else None
                                except:
                                    max_size = None
                            else:
                                min_size = None
                                max_size = None
                            cfg[ext]['save_folder'] = save_folder
                            cfg[ext]['min_size'] = min_size
                            cfg[ext]['max_size'] = max_size
                            print(f"保存文件设置已更新：保存路径：{save_folder}, 最小大小：{min_size} MB, 最大大小：{max_size} MB")
                        else:
                            cfg[ext]['save_folder'] = None
                            cfg[ext]['min_size'] = None
                            cfg[ext]['max_size'] = None
                            print("已关闭保存文件功能")
                    print(f"文件后缀配置更新为： {cfg[ext]}")
                else:
                    print("未找到该文件后缀配置")
                    
            elif command == 'removeext':
                if current_account is None:
                    print("请先切换或添加账号")
                    continue
                cfg = ACCOUNTS[current_account]["config"]["file_extension_config"]
                ext = (await ainput("请输入要移除的文件后缀（如 .pdf）： ")).strip().lower()
                if not ext.startswith('.'):
                    ext = '.' + ext
                if ext in cfg:
                    del cfg[ext]
                    print(f"已移除文件后缀 '{ext}' 的配置")
                else:
                    print("未找到该文件后缀配置")

            elif command == 'showext':
                if current_account is None:
                    print("请先切换或添加账号")
                    continue
                cfg = ACCOUNTS[current_account]["config"]["file_extension_config"]
                print("\n=== 当前文件后缀配置 ===")
                for k, v in cfg.items():
                    print(f"{k} : {v}")

            elif command == 'addall':
                if current_account is None:
                    print("请先切换或添加账号")
                    continue
                cfg = ACCOUNTS[current_account]["config"]["all_messages_config"]
                chat_id = int((await ainput("请输入全量监控对话ID: ")).strip())
                print("请选择要监控用户其类型： 1. 用户ID(频道id或Bot id)  2. 用户名  3. 昵称")
                user_option = (await ainput("请输入选项编号（可留空表示全部）： ")).strip()
                users_input = (await ainput("请输入对应用户标识（多个逗号分隔，可留空）： ")).strip()
                if users_input:
                    if user_option == '1':
                        user_set = [int(x.strip()) for x in users_input.split(',') if x.strip().isdigit()]
                    else:
                        user_set = [x.strip() for x in users_input.split(',')]
                else:
                    user_set = []
                auto_forward = (await ainput("启用自动转发？(yes/no): ")).strip().lower() == 'yes'
                email_notify = (await ainput("启用邮件通知？(yes/no): ")).strip().lower() == 'yes'
                if auto_forward:
                    target_ids_input = (await ainput("请输入转发目标对话ID（多个逗号分隔）： ")).strip()
                    target_ids = [int(x.strip()) for x in target_ids_input.split(',')]
                else:
                    target_ids = []
                execution_limit_input = (await ainput("请输入执行次数限制（正整数），直接回车表示不设置： ")).strip()
                if execution_limit_input.isdigit():
                    max_executions = int(execution_limit_input)
                else:
                    max_executions = None
                log_file = (await ainput("请输入baocun消息的文件路径（直接回车则不记录）： ")).strip() or None
                filter_choice = (await ainput("是否设置屏蔽过滤？(yes/no): ")).strip().lower() == 'yes'
                if filter_choice:
                    blocked_users_input = (await ainput("请输入屏蔽用户、频道或Bot（ID，多个逗号分隔）： ")).strip()
                    blocked_users = [x.strip() for x in blocked_users_input.split(',')] if blocked_users_input else []
                else:
                    blocked_users = []
                cfg[chat_id] = {
                    'auto_forward': auto_forward,
                    'email_notify': email_notify,
                    'forward_targets': target_ids,
                    'users': user_set,
                    'user_option': user_option,
                    'log_file': log_file,
                    'max_executions': max_executions,
                    'execution_count': 0,
                    'blocked_users': blocked_users,
                }
                print(f"已添加全量监控配置： {cfg[chat_id]}")

            elif command == 'modifyall':
                if current_account is None:
                    print("请先切换或添加账号")
                    continue
                cfg = ACCOUNTS[current_account]["config"]["all_messages_config"]
                chat_id = int((await ainput("请输入要修改的全量监控对话ID: ")).strip())
                if chat_id in cfg:
                    config = cfg[chat_id]
                    print(f"当前配置：{config}")
                    print("请输入修改项（逗号分隔）： 1. 自动转发  2. 邮件通知  3. 转发目标  4. 用户过滤")
                    print("5. 日志文件  6. 执行次数限制  7. 屏蔽过滤")
                    options = (await ainput("请输入修改项: ")).strip().split(',')
                    options = [x.strip() for x in options]
                    if '1' in options:
                        auto_forward = (await ainput("启用自动转发？(yes/no): ")).strip().lower() == 'yes'
                        config['auto_forward'] = auto_forward
                        if auto_forward:
                            target_ids_input = (await ainput("请输入转发目标对话ID（多个逗号分隔）： ")).strip()
                            config['forward_targets'] = [int(x.strip()) for x in target_ids_input.split(',')]
                        else:
                            config['forward_targets'] = []
                    if '2' in options:
                        email_notify = (await ainput("启用邮件通知？(yes/no): ")).strip().lower() == 'yes'
                        config['email_notify'] = email_notify
                    if '3' in options:
                        if config.get('auto_forward', False):
                            target_ids_input = (await ainput("请输入转发目标对话ID（多个逗号分隔）： ")).strip()
                            config['forward_targets'] = [int(x.strip()) for x in target_ids_input.split(',')]
                        else:
                            print("未启用自动转发")
                    if '4' in options:
                        user_option = (await ainput("请选择要监控用户其类型： 1. 用户ID(频道id或Bot id)  2. 用户名  3. 昵称）： ")).strip()
                        users_input = (await ainput("请输入对应用户标识（多个逗号分隔）： ")).strip()
                        if users_input:
                            if user_option == '1':
                                config['users'] = [int(x.strip()) for x in users_input.split(',') if x.strip().isdigit()]
                            else:
                                config['users'] = [x.strip() for x in users_input.split(',')]
                        else:
                            config['users'] = []
                        config['user_option'] = user_option
                    if '5' in options:
                        log_file = (await ainput("请输入新的保存消息的文件路径（留空则删除）： ")).strip()
                        config['log_file'] = log_file or None
                    if '6' in options:
                        execution_limit_input = (await ainput("请输入新的执行次数限制（正整数），直接回车表示不设置： ")).strip()
                        if execution_limit_input.isdigit():
                            config['max_executions'] = int(execution_limit_input)
                        else:
                            config['max_executions'] = None
                        config['execution_count'] = 0
                    if '7' in options:
                        filter_choice = (await ainput("是否设置屏蔽过滤？(yes/no): ")).strip().lower() == 'yes'
                        if filter_choice:
                            blocked_users_input = (await ainput("请输入屏蔽用户、频道或Bot（ID，多个逗号分隔）： ")).strip()
                            blocked_users = [x.strip() for x in blocked_users_input.split(',')] if blocked_users_input else []
                        else:
                            blocked_users = []
                        config['blocked_users'] = blocked_users
                    print(f"全量监控配置更新为： {config}")
                else:
                    print("未找到该全量监控配置")

            elif command == 'removeall':
                if current_account is None:
                    print("请先切换或添加账号")
                    continue
                cfg = ACCOUNTS[current_account]["config"]["all_messages_config"]
                chat_id = int((await ainput("请输入要移除的全量监控对话ID: ")).strip())
                if chat_id in cfg:
                    del cfg[chat_id]
                    print("已移除全量监控配置")
                else:
                    print("未找到该全量监控配置")

            elif command == 'showall':
                if current_account is None:
                    print("请先切换或添加账号")
                    continue
                cfg = ACCOUNTS[current_account]["config"]["all_messages_config"]
                print("\n=== 当前全量监控配置 ===")
                for k, v in cfg.items():
                    print(f"{k} : {v}")
                    
            elif command == 'addbutton':
                if current_account is None:
                    print("请先切换或添加账号")
                    continue
                cfg = ACCOUNTS[current_account]["config"]["button_keyword_config"]
                b_keyword = (await ainput("请输入按钮关键词: ")).strip().lower()
                chat_ids_input = (await ainput("请输入监听对话ID（多个逗号分隔）： ")).strip()
                chat_ids = [int(x.strip()) for x in chat_ids_input.split(',')]
                print("请选择用户类型： 1. 用户ID  2. 用户名  3. 昵称")
                user_option = (await ainput("请输入选项编号（可留空表示全部）： ")).strip()
                users_input = (await ainput("请输入对应用户标识（多个逗号分隔）： ")).strip()
                if users_input:
                    if user_option == '1':
                        user_set = [int(x.strip()) for x in users_input.split(',') if x.strip().isdigit()]
                    else:
                        user_set = [x.strip() for x in users_input.split(',')]
                else:
                    user_set = []
                cfg[b_keyword] = {
                    'chats': chat_ids,
                    'users': user_set,
                    'user_option': user_option
                }
                print(f"已添加按钮关键词配置： {cfg[b_keyword]}")
            
            elif command == 'modifybutton':
                if current_account is None:
                    print("请先切换或添加账号")
                    continue
                cfg = ACCOUNTS[current_account]["config"]["button_keyword_config"]
                b_keyword = (await ainput("请输入要修改的按钮关键词: ")).strip().lower()
                if b_keyword in cfg:
                    config = cfg[b_keyword]
                    print(f"当前配置：{config}")
                    print("请输入要修改的项（逗号分隔）： 1. 按钮关键词  2. 监听对话ID  3. 用户过滤")
                    options = (await ainput("请输入修改项: ")).strip().split(',')
                    options = [x.strip() for x in options]
                    if '1' in options:
                        new_b_keyword = (await ainput("请输入新的按钮关键词: ")).strip().lower()
                        cfg[new_b_keyword] = cfg.pop(b_keyword)
                        b_keyword = new_b_keyword
                        print(f"按钮关键词修改为： {new_b_keyword}")
                    if '2' in options:
                        chat_ids_input = (await ainput("请输入新的监听对话ID（多个逗号分隔）： ")).strip()
                        cfg[b_keyword]['chats'] = [int(x.strip()) for x in chat_ids_input.split(',')]
                        print("监听对话ID已更新")
                    if '3' in options:
                        user_option = (await ainput("请输入新的用户类型（1/2/3）： ")).strip()
                        users_input = (await ainput("请输入对应用户标识（多个逗号分隔）： ")).strip()
                        if users_input:
                            if user_option == '1':
                                cfg[b_keyword]['users'] = [int(x.strip()) for x in users_input.split(',') if x.strip().isdigit()]
                            else:
                                cfg[b_keyword]['users'] = [x.strip() for x in users_input.split(',')]
                        else:
                            cfg[b_keyword]['users'] = []
                        cfg[b_keyword]['user_option'] = user_option
                    print(f"按钮关键词配置更新为： {cfg[b_keyword]}")
                else:
                    print("未找到该按钮关键词配置")
            
            elif command == 'removebutton':
                if current_account is None:
                    print("请先切换或添加账号")
                    continue
                cfg = ACCOUNTS[current_account]["config"]["button_keyword_config"]
                b_keyword = (await ainput("请输入要移除的按钮关键词: ")).strip().lower()
                if b_keyword in cfg:
                    del cfg[b_keyword]
                    print("已移除按钮关键词配置")
                else:
                    print("未找到该配置")
            
            elif command == 'showbuttons':
                if current_account is None:
                    print("请先切换或添加账号")
                    continue
                cfg = ACCOUNTS[current_account]["config"]["button_keyword_config"]
                print("\n=== 当前按钮关键词配置 ===")
                for k, v in cfg.items():
                    print(f"{k} : {v}")
            
            elif command == 'addlistener':
                if current_account is None:
                    print("请先切换或添加账号")
                    continue
                cfg = ACCOUNTS[current_account]["config"]["image_button_monitor"]
                chat_id = int((await ainput("请输入要监听的对话ID: ")).strip())
                if isinstance(cfg, set):
                    if chat_id not in cfg:
                        cfg.add(chat_id)
                else:
                    if chat_id not in cfg:
                        cfg.append(chat_id)
                print(f"已添加图片+按钮监听对话ID: {chat_id}")

            elif command == 'modifylistener':
                if current_account is None:
                    print("请先切换或添加账号")
                    continue
                cfg_list = ACCOUNTS[current_account]["config"]["image_button_monitor"]
                print(f"当前图片+按钮监听对话ID列表: {list(cfg_list)}")
                new_list_input = (await ainput("请输入新的监听对话ID列表（多个逗号分隔）： ")).strip()
                if new_list_input:
                    try:
                        new_list = [int(x.strip()) for x in new_list_input.split(',')]
                        ACCOUNTS[current_account]["config"]["image_button_monitor"] = new_list
                        print(f"图片+按钮监听对话ID已更新为: {new_list}")
                    except Exception as e:
                        print(f"输入格式有误: {e}")
                else:
                    print("未做任何修改")
            
            elif command == 'removelistener':
                if current_account is None:
                    print("请先切换或添加账号")
                    continue
                cfg_list = ACCOUNTS[current_account]["config"]["image_button_monitor"]
                chat_id = int((await ainput("请输入要移除的监听对话ID: ")).strip())
                if chat_id in cfg_list:
                    cfg_list.remove(chat_id)
                    print(f"已移除图片+按钮监听对话ID: {chat_id}")
                else:
                    print("未找到该监听配置")
            
            elif command == 'showlistener':
                if current_account is None:
                    print("请先切换或添加账号")
                    continue
                cfg_list = ACCOUNTS[current_account]["config"]["image_button_monitor"]
                print("\n=== 当前图片+按钮监听对话ID ===")
                for cid in cfg_list:
                    print(cid)
            
            elif command == 'schedule':
                if current_account is None:
                    print("请先切换或添加账号")
                    continue
                cfg_sched = ACCOUNTS[current_account]["config"]["scheduled_messages"]
                target_id = int((await ainput("请输入目标对话ID: ")).strip())
                message = (await ainput("请输入要发送的消息: ")).strip()
                cron_expression = (await ainput("请输入Cron表达式: ")).strip()
                random_offset_input = (await ainput("请输入随机时间误差（秒），默认为0: ")).strip()
                random_offset = int(random_offset_input) if random_offset_input else 0
                delete_after_sending = (await ainput("是否在发送后删除消息？(yes/no): ")).strip().lower() == 'yes'
                execution_limit_input = (await ainput("请输入执行次数限制（正整数），直接回车表示不设置： ")).strip()
                if execution_limit_input.isdigit():
                    max_executions = int(execution_limit_input)
                else:
                    max_executions = None

                job = schedule_message(target_id, message, cron_expression, random_offset, delete_after_sending, current_account)
                cfg_sched.append({
                    'job_id': job.id,
                    'target_id': target_id,
                    'message': message,
                    'cron': cron_expression,
                    'random_offset': random_offset,
                    'delete_after_sending': delete_after_sending,
                    'account_id': current_account,
                    'max_executions': max_executions,
                    'execution_count': 0
                })
                print(f"已添加定时消息配置，Job ID: {job.id}")
            
            elif command == 'modifyschedule':
                if current_account is None:
                    print("请先切换或添加账号")
                    continue
                job_id = (await ainput("请输入要修改的定时消息的Job ID: ")).strip()
                job = scheduler.get_job(job_id)
                if job:
                    sched = next((s for s in ACCOUNTS[current_account]["config"]["scheduled_messages"] if s['job_id'] == job_id), None)
                    if sched:
                        print(f"当前配置：{sched}")
                        print("请输入修改项（逗号分隔）： 1. 目标对话ID  2. 消息内容  3. Cron表达式  4. 随机时间误差  5. 发送后删除  6. 执行次数限制")
                        options = (await ainput("请输入修改项: ")).strip().split(',')
                        options = [x.strip() for x in options]
                        if '1' in options:
                            sched['target_id'] = int((await ainput("请输入新的目标对话ID: ")).strip())
                        if '2' in options:
                            sched['message'] = (await ainput("请输入新的消息内容: ")).strip()
                        if '3' in options:
                            sched['cron'] = (await ainput("请输入新的Cron表达式: ")).strip()
                        if '4' in options:
                            r = (await ainput("请输入新的随机时间误差（秒）： ")).strip()
                            sched['random_offset'] = int(r) if r else 0
                        if '5' in options:
                            sched['delete_after_sending'] = (await ainput("是否在发送后删除？(yes/no): ")).strip().lower() == 'yes'
                        if '6' in options:
                            execution_limit_input = (await ainput("请输入新的执行次数限制（正整数），直接回车表示不设置： ")).strip()
                            if execution_limit_input.isdigit():
                                sched['max_executions'] = int(execution_limit_input)
                            else:
                                sched['max_executions'] = None
                            sched['execution_count'] = 0
                        try:
                            scheduler.remove_job(job_id)
                        except Exception as e:
                            logger.error(f"删除定时任务时出错: {repr(e)}")
                        new_job = scheduler.add_job(
                            send_scheduled_message,
                            CronTrigger.from_crontab(sched['cron'], timezone=pytz.timezone('Asia/Shanghai')),
                            args=[sched['target_id'], sched['message'], sched.get('random_offset', 0), sched.get('delete_after_sending', False), sched.get('account_id')],
                            id=job_id
                        )
                        print(f"定时消息配置 '{job_id}' 已更新")
                    else:
                        print("未找到该定时消息配置")
                else:
                    print("未找到该定时消息")
            
            elif command == 'removeschedule':
                if current_account is None:
                    print("请先切换或添加账号")
                    continue
                job_id = (await ainput("请输入要删除的定时消息的Job ID: ")).strip()
                try:
                    scheduler.remove_job(job_id)
                    sched_list = ACCOUNTS[current_account]["config"]["scheduled_messages"]
                    ACCOUNTS[current_account]["config"]["scheduled_messages"] = [s for s in sched_list if s['job_id'] != job_id]
                    print(f"已删除定时消息配置，Job ID: {job_id}")
                except Exception as e:
                    logger.error(f"删除定时消息时出错: {repr(e)}")
                    print("未找到该定时消息")
            
            elif command == 'showschedule':
                if current_account is None:
                    print("请先切换或添加账号")
                    continue
                sched_list = ACCOUNTS[current_account]["config"]["scheduled_messages"]
                print("\n=== 当前定时消息配置 ===")
                for s in sched_list:
                    print(s)
            
            elif command == 'start':
                scope = (await ainput("请选择监控开关范围: 1. 当前账号  2. 全局: ")).strip()
                timing = (await ainput("请输入定时开机设置（输入延迟分钟或Cron表达式，直接回车则立即开机）： ")).strip()
                if timing:
                    if timing.isdigit():
                        delay_minutes = int(timing)
                        if scope == '1':
                            scheduler.add_job(lambda: set_account_monitor_active(current_account, True),
                                            'date',
                                            run_date=datetime.now() + timedelta(minutes=delay_minutes))
                            print(f"将在 {delay_minutes} 分钟后自动开启当前账号 {current_account} 的监控")
                        else:
                            scheduler.add_job(lambda: set_monitor_active(True),
                                            'date',
                                            run_date=datetime.now() + timedelta(minutes=delay_minutes))
                            print(f"将在 {delay_minutes} 分钟后自动开启全局监控")
                    else:
                        try:
                            if scope == '1':
                                scheduler.add_job(lambda: set_account_monitor_active(current_account, True),
                                                CronTrigger.from_crontab(timing, timezone=pytz.timezone('Asia/Shanghai')))
                                print(f"已添加周期性开机任务（当前账号），Cron表达式: {timing}")
                            else:
                                scheduler.add_job(lambda: set_monitor_active(True),
                                                CronTrigger.from_crontab(timing, timezone=pytz.timezone('Asia/Shanghai')))
                                print(f"已添加周期性开机任务（全局），Cron表达式: {timing}")
                        except Exception as e:
                            print(f"Cron表达式设置有误：{e}")
                else:
                    if scope == '1':
                        set_account_monitor_active(current_account, True)
                        print(f"当前账号 {current_account} 的监控已立即开启")
                    else:
                        set_monitor_active(True)
                        print("全局监控已立即开启")
            elif command == 'stop':
                scope = (await ainput("请选择监控开关范围: 1. 当前账号  2. 全局: ")).strip()
                timing = (await ainput("请输入定时关机设置（输入延迟分钟或Cron表达式，直接回车则立即关闭）： ")).strip()
                if timing:
                    if timing.isdigit():
                        delay_minutes = int(timing)
                        if scope == '1':
                            scheduler.add_job(lambda: set_account_monitor_active(current_account, False),
                                            'date',
                                            run_date=datetime.now() + timedelta(minutes=delay_minutes))
                            print(f"将在 {delay_minutes} 分钟后自动关闭当前账号 {current_account} 的监控")
                        else:
                            scheduler.add_job(lambda: set_monitor_active(False),
                                            'date',
                                            run_date=datetime.now() + timedelta(minutes=delay_minutes))
                            print(f"将在 {delay_minutes} 分钟后自动关闭全局监控")
                    else:
                        try:
                            if scope == '1':
                                scheduler.add_job(lambda: set_account_monitor_active(current_account, False),
                                                CronTrigger.from_crontab(timing, timezone=pytz.timezone('Asia/Shanghai')))
                                print(f"已添加周期性关机任务（当前账号），Cron表达式: {timing}")
                            else:
                                scheduler.add_job(lambda: set_monitor_active(False),
                                                CronTrigger.from_crontab(timing, timezone=pytz.timezone('Asia/Shanghai')))
                                print(f"已添加周期性关机任务（全局），Cron表达式: {timing}")
                        except Exception as e:
                            print(f"Cron表达式设置有误：{e}")
                else:
                    if scope == '1':
                        set_account_monitor_active(current_account, False)
                        print(f"当前账号 {current_account} 的监控已立即关闭")
                    else:
                        set_monitor_active(False)
                        print("全局监控已立即关闭")

            elif command == 'exit':
                print("正在退出程序...")
                for account in ACCOUNTS.values():
                    await account["client"].disconnect()
                scheduler.shutdown()
                return
            else:
                print("未知命令，请输入 help 查看所有可用命令")
        except Exception as e:
            logger.error(f"执行命令时出错: {repr(e)}")
            print(f"执行命令时出错: {repr(e)}")

async def telegram_login(client):
    logger.info('开始Telegram登录流程...')
    phone = (await ainput('请输入您的Telegram手机号 (格式如: +8613800138000): ')).strip()
    try:
        await client.send_code_request(phone)
        logger.info('验证码已发送到您的Telegram账号')
        code = (await ainput('请输入您收到的验证码: ')).strip()
        try:
            await client.sign_in(phone, code)
        except SessionPasswordNeededError:
            logger.info('检测到两步验证，需要输入密码')
            password = (await ainput('请输入您的两步验证密码: ')).strip()
            await client.sign_in(password=password)
        logger.info('Telegram登录成功！')
    except Exception as e:
        error_message = repr(e)
        logger.error(f'登录过程中发生错误：{error_message}')
        raise


async def main():
    scheduler.start()
    print("\n=== Telegram消息监控程序 ===")
    print("请先设置监控参数")
    await handle_commands()

if __name__ == '__main__':
    monitor_active = False
    scheduler = AsyncIOScheduler()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info('程序被用户中断')
    except Exception as e:
        error_message = repr(e)
        logger.error(f'程序发生错误：{error_message}')
