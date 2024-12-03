import sys
from telethon import TelegramClient, events
from telethon.tl.types import Channel, Chat, MessageMediaDocument
import asyncio
import logging
from datetime import datetime
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

# === 配置部分 ===
# 邮件配置
SMTP_SERVER = "smtp.qq.com"          # SMTP 服务器，例如 QQ 邮箱
SMTP_PORT = 465                      # SMTP 端口，通常为 465
SENDER_EMAIL = "您的邮箱@example.com"  # 发件人邮箱
EMAIL_PASSWORD = "您的邮箱授权码"      # 邮箱授权码或密码
RECIPIENT_EMAIL = "收件人邮箱@example.com"  # 收件人邮箱

# === 日志配置 ===
def setup_logger():
    """配置日志"""
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

# === 数据结构 ===

# 关键词配置，每个关键词对应一个配置字典
KEYWORD_CONFIG = {}  # {keyword: {'chats': [chat_ids], 'match_type': 'exact'/'partial'/'regex', 'auto_forward': True/False, 'email_notify': True/False, 'forward_targets': [target_ids], 'users': set([...])}}

# 文件后缀名配置
FILE_EXTENSION_CONFIG = {}  # {extension: {'chats': [chat_ids], 'auto_forward': True/False, 'forward_targets': [target_ids], 'users': set([...])}}

# 定时消息配置
SCHEDULED_MESSAGES = []  # [{'job_id': str, 'target_id': int, 'message': str, 'cron': str, 'random_offset': int, 'delete_after_sending': bool}]

def send_email(message_text):
    """发送邮件"""
    try:
        # 设置邮件内容
        message = MIMEMultipart()
        message["From"] = SENDER_EMAIL
        message["To"] = RECIPIENT_EMAIL
        message["Subject"] = Header("Telegram 监控消息", "utf-8")  # 邮件主题

        # 添加消息内容到邮件正文
        body = MIMEText(message_text, "plain", "utf-8")
        message.attach(body)

        # 连接到 SMTP 服务器并发送邮件
        server = smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT)
        server.login(SENDER_EMAIL, EMAIL_PASSWORD)
        server.sendmail(SENDER_EMAIL, RECIPIENT_EMAIL, message.as_string())
        logger.info("邮件发送成功")
    except Exception as e:
        logger.error(f"邮件发送失败: {e}")
    finally:
        try:
            server.quit()
        except Exception as e:
            # 忽略在关闭连接时的异常
            pass

# === 自定义异步输入函数 ===
async def ainput(prompt: str = '') -> str:
    """自定义异步输入函数，确保正确处理编码"""
    loop = asyncio.get_event_loop()
    print(prompt, end='', flush=True)
    return (await loop.run_in_executor(None, sys.stdin.readline)).rstrip('\n')

# === 消息处理函数 ===
async def message_handler(event):
    """处理新消息"""
    global monitor_active, own_user_id  # 引用 own_user_id

    if not monitor_active:
        return

    chat_id = event.chat_id
    message_text = event.raw_text
    message_text_lower = message_text.lower().strip()

    try:
        sender = await event.get_sender()
        # 获取发送者信息
        sender_id = sender.id if sender else None

        # 添加判断，跳过自己发送的消息
        if sender_id == own_user_id:
            return  # 跳过自己发送的消息

        # 定义 sender_username
        sender_username = sender.username.lower() if sender and sender.username else None

        # 将发送者 ID 和用户名存储，用于匹配
        sender_identifiers = set()
        if sender_id:
            sender_identifiers.add(sender_id)
        if sender_username:
            sender_identifiers.add(sender_username)

        # 检查关键词
        for keyword, config in KEYWORD_CONFIG.items():
            if chat_id in config['chats']:
                match_type = config.get('match_type', 'partial')
                user_set = config.get('users', set())
                # 获取配置中的用户类型选项
                user_option = config.get('user_option')

                # 使用 match_user 函数判断是否匹配用户
                if not match_user(sender, user_set, user_option):
                    continue  # 不匹配指定用户，跳过此配置

                # 检查关键词匹配
                if match_type == 'exact':
                    if message_text_lower == keyword:
                        logger.info(f'检测到完全匹配关键词 "{keyword}" 在对话 {chat_id} 中的消息: {message_text}')
                        if config.get('email_notify'):
                            send_email(f"检测到完全匹配关键词 '{keyword}' 的消息: {message_text}")
                        if config.get('auto_forward'):
                            await auto_forward_message(event, keyword)
                        break  # 停止后续的关键词检测
                elif match_type == 'partial':
                    if keyword in message_text_lower:
                        logger.info(f'检测到关键词 "{keyword}" 在对话 {chat_id} 中的消息: {message_text}')
                        if config.get('email_notify'):
                            send_email(f"检测到关键词 '{keyword}' 的消息: {message_text}")
                        if config.get('auto_forward'):
                            await auto_forward_message(event, keyword)
                        break  # 停止后续的关键词检测
                elif match_type == 'regex':
                    pattern = re.compile(rf'{keyword}')
                    if pattern.search(message_text):
                        logger.info(f'检测到正则匹配 "{keyword}" 在对话 {chat_id} 中的消息: {message_text}')
                        if config.get('email_notify'):
                            send_email(f"检测到正则匹配 '{keyword}' 的消息: {message_text}")
                        if config.get('auto_forward'):
                            await auto_forward_message(event, keyword)
                        break  # 停止后续的关键词检测

        else:
            # 如果没有匹配到关键词，继续检查文件后缀名
            if event.message.media and isinstance(event.message.media, MessageMediaDocument):
                # 获取文件名和后缀
                file_attr = event.message.media.document.attributes
                file_name = None
                for attr in file_attr:
                    if hasattr(attr, 'file_name'):
                        file_name = attr.file_name
                        break
                if file_name:
                    file_extension = os.path.splitext(file_name)[1].lower()
                    config = FILE_EXTENSION_CONFIG.get(file_extension)
                    if config and chat_id in config['chats']:
                        user_set = config.get('users', set())

                        # 使用 match_user 函数判断是否匹配用户
                        if not match_user(sender, user_set):
                            return  # 不匹配指定用户，跳过此配置

                        logger.info(f"检测到文件后缀名 {file_extension} 的文件：{file_name} 在对话 {chat_id} 中")
                        if config.get('auto_forward'):
                            await auto_forward_file_message(event, file_extension)

    except Exception as e:
        error_message = repr(e)
        logger.error(f'处理消息时发生错误：{error_message}')

def match_user(sender, user_set, user_option):
    if not user_set:
        return True  # 如果未指定用户，匹配所有人
    if not sender:
        return False  # 无法获取发送者信息，无法匹配

    sender_id = sender.id
    sender_username = sender.username.lower() if sender.username else None
    sender_first_name = sender.first_name if sender.first_name else ''
    sender_last_name = sender.last_name if sender.last_name else ''
    sender_full_name = f"{sender_first_name} {sender_last_name}".strip()

    # 添加日志，输出发送者的信息
    logger.info(f"匹配用户：sender_id={sender_id}, sender_username={sender_username}, sender_full_name={sender_full_name}, user_set={user_set}")

    if user_option == '1':
        # 用户ID匹配
        return sender_id in user_set
    elif user_option == '2':
        # 用户名匹配
        return sender_username in user_set
    elif user_option == '3':
        # 昵称匹配（全名）
        return sender_full_name in user_set
    else:
        # 未指定用户，匹配所有
        return True

# === 自动转发功能 ===
async def auto_forward_message(event, keyword):
    """自动转发包含指定关键词的消息"""
    try:
        config = KEYWORD_CONFIG[keyword]
        target_ids = config.get('forward_targets', [])
        for target_id in target_ids:
            await client.forward_messages(target_id, event.message)
            logger.info(f"已将关键词 '{keyword}' 消息转发到ID: {target_id}")
    except Exception as e:
        error_message = repr(e)
        logger.error(f"自动转发消息时发生错误：{error_message}")

async def auto_forward_file_message(event, file_extension):
    """自动转发包含指定文件后缀名的消息"""
    try:
        config = FILE_EXTENSION_CONFIG[file_extension]
        target_ids = config.get('forward_targets', [])
        for target_id in target_ids:
            await client.forward_messages(target_id, event.message)
            logger.info(f"已将包含文件{file_extension}的消息转发到ID: {target_id}")
    except Exception as e:
        error_message = repr(e)
        logger.error(f"自动转发文件消息时发生错误：{error_message}")

# === 定时发送功能 ===
def schedule_message(target_id, message, cron_expression, random_offset=0, delete_after_sending=False):
    """使用APScheduler定时发送消息"""
    job = scheduler.add_job(
        send_scheduled_message,
        CronTrigger.from_crontab(cron_expression, timezone=pytz.timezone('Asia/Shanghai')),
        args=[target_id, message, random_offset, delete_after_sending]
    )
    logger.info(f"已添加定时消息，Cron表达式: {cron_expression}，目标ID: {target_id}")
    return job

async def send_scheduled_message(target_id, message, random_offset=0, delete_after_sending=False):
    """发送定时消息"""
    try:
        if random_offset > 0:
            delay = random.uniform(0, random_offset)
            logger.info(f"等待 {delay:.2f} 秒后发送定时消息")
            await asyncio.sleep(delay)
        sent_message = await client.send_message(target_id, message)
        logger.info(f"已发送定时消息到ID: {target_id}")
        if delete_after_sending:
            await asyncio.sleep(5)  # 等待一段时间再删除，防止消息还未完全发送
            await client.delete_messages(target_id, sent_message.id)
            logger.info(f"已删除发送的定时消息，消息ID: {sent_message.id}")
    except Exception as e:
        error_message = repr(e)
        logger.error(f"发送定时消息时发生错误：{error_message}")

# === 命令处理函数 ===
async def handle_commands(client):
    """处理用户输入的命令"""
    global monitor_active, KEYWORD_CONFIG, FILE_EXTENSION_CONFIG, SCHEDULED_MESSAGES

    while True:
        print("\n=== 可用命令 ===")
        print("1. list - 列出所有对话")
        print("2. addkeyword - 添加关键词")
        print("3. modifykeyword - 修改关键词")
        print("4. removekeyword - 移除关键词")
        print("5. showkeywords - 显示所有关键词及其配置")
        print("6. addext - 添加文件后缀名监控")
        print("7. modifyext - 修改文件后缀名监控")
        print("8. removeext - 移除文件后缀名监控")
        print("9. showext - 显示所有文件后缀名及其配置")
        print("10. schedule - 添加定时消息")
        print("11. modifyschedule - 修改定时消息")
        print("12. removeschedule - 删除定时消息")
        print("13. showschedule - 显示所有定时消息")
        print("14. start - 开始监控")
        print("15. stop - 停止监控")
        print("16. exit - 退出程序")

        command = (await ainput("\n请输入命令: ")).strip().lower()

        try:
            if command == 'list':
                print("\n=== 所有对话 ===")
                async for dialog in client.iter_dialogs():
                    if isinstance(dialog.entity, (Channel, Chat)):
                        print(f"ID: {dialog.id}, 名称: {dialog.name}, 类型: {'频道' if isinstance(dialog.entity, Channel) else '群组'}")

            elif command == 'addkeyword':
                # 选择匹配类型
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
                    keywords = [keywords_input.strip()]  # 不再按逗号分隔

                chat_ids_input = (await ainput("请输入要监听的对话ID，多个ID用逗号分隔: ")).strip()
                chat_ids = [int(tid.strip()) for tid in chat_ids_input.split(',')]

                # 添加用户类型选择
                print("\n请选择要指定的用户类型：")
                print("1. 用户ID")
                print("2. 用户名")
                print("3. 昵称")
                user_option = (await ainput("请输入选项编号（1/2/3，直接回车表示监听所有用户）: ")).strip()

                if user_option in ['1', '2', '3']:
                    users_input = (await ainput("请输入对应的用户标识，多个用逗号分隔: ")).strip()
                    if users_input:
                        user_list = [u.strip() for u in users_input.split(',')]
                        user_set = set()
                        for u in user_list:
                            if user_option == '1':
                                # 用户ID
                                if u.isdigit():
                                    user_set.add(int(u))
                                else:
                                    print(f"用户ID应为数字，输入无效：{u}")
                            elif user_option == '2':
                                # 用户名
                                user_set.add(u.lower())  # 用户名统一转换为小写
                            elif user_option == '3':
                                # 昵称
                                user_set.add(u)
                    else:
                        user_set = set()
                else:
                    user_option = None
                    user_set = set()  # 未选择或直接回车，监听所有用户

                auto_forward = (await ainput("是否启用自动转发功能？(yes/no): ")).strip().lower() == 'yes'
                email_notify = (await ainput("是否启用邮件通知功能？(yes/no): ")).strip().lower() == 'yes'

                # 如果启用了自动转发，设置转发目标
                if auto_forward:
                    target_ids_input = (await ainput("请输入自动转发的目标对话ID，多个ID用逗号分隔: ")).strip()
                    target_ids = [int(tid.strip()) for tid in target_ids_input.split(',')]
                else:
                    target_ids = []

                for keyword in keywords:
                    config = {
                        'chats': chat_ids,
                        'auto_forward': auto_forward,
                        'email_notify': email_notify,
                        'match_type': match_type,
                        'users': user_set,
                        'user_option': user_option  # 保存用户类型选项
                    }
                    if auto_forward:
                        config['forward_targets'] = target_ids
                        print(f"已设置关键词 '{keyword}' 的自动转发目标ID: {target_ids}")
                    KEYWORD_CONFIG[keyword] = config
                    print(f"已添加关键词 '{keyword}'，配置：{config}")
            elif command == 'modifykeyword':
                keyword_input = (await ainput("请输入要修改的关键词: ")).strip()
                if keyword_input in KEYWORD_CONFIG:
                    config = KEYWORD_CONFIG[keyword_input]
                    print(f"当前配置：{config}")

                    # 提示用户选择要修改的项
                    print("\n可修改的项：")
                    print("1. 关键词")
                    print("2. 监听的对话ID")
                    print("3. 自动转发设置")
                    print("4. 邮件通知设置")
                    print("5. 匹配类型")
                    print("6. 监听的用户")

                    options = (await ainput("请输入要修改的项，多个项用逗号分隔（例如：1,3）: ")).strip()
                    options = [opt.strip() for opt in options.split(',')]

                    if '1' in options:
                        match_type = config.get('match_type', 'partial')
                        if match_type != 'regex':
                            new_keyword = (await ainput("请输入新的关键词: ")).strip()
                        else:
                            new_keyword = (await ainput("请输入新的正则表达式模式: ")).strip()
                        # 删除旧的关键词配置，添加新的
                        KEYWORD_CONFIG[new_keyword] = KEYWORD_CONFIG.pop(keyword_input)
                        keyword_input = new_keyword  # 更新关键词变量
                        print(f"关键词已修改为：{new_keyword}")

                    # 修改监听的对话ID
                    if '2' in options:
                        chat_ids_input = (await ainput("请输入新的监听的对话ID，多个ID用逗号分隔: ")).strip()
                        chat_ids = [int(tid.strip()) for tid in chat_ids_input.split(',')]
                        KEYWORD_CONFIG[keyword_input]['chats'] = chat_ids
                        print(f"监听的对话ID已更新为：{chat_ids}")

                    # 修改自动转发设置
                    if '3' in options:
                        auto_forward = (await ainput("是否启用自动转发功能？(yes/no): ")).strip().lower() == 'yes'
                        KEYWORD_CONFIG[keyword_input]['auto_forward'] = auto_forward
                        if auto_forward:
                            target_ids_input = (await ainput("请输入自动转发的目标对话ID，多个ID用逗号分隔: ")).strip()
                            target_ids = [int(tid.strip()) for tid in target_ids_input.split(',')]
                            KEYWORD_CONFIG[keyword_input]['forward_targets'] = target_ids
                            print(f"自动转发目标ID已更新为：{target_ids}")
                        else:
                            KEYWORD_CONFIG[keyword_input]['forward_targets'] = []
                            print("已关闭自动转发功能")

                    # 修改邮件通知设置
                    if '4' in options:
                        email_notify = (await ainput("是否启用邮件通知功能？(yes/no): ")).strip().lower() == 'yes'
                        KEYWORD_CONFIG[keyword_input]['email_notify'] = email_notify
                        print(f"邮件通知功能已更新为：{'启用' if email_notify else '禁用'}")

                    # 修改匹配类型
                    if '5' in options:
                        print("\n请选择新的匹配类型：")
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
                        KEYWORD_CONFIG[keyword_input]['match_type'] = match_type
                        print(f"匹配类型已更新为：{match_type}")

                    # 修改监听的用户
                    if '6' in options:
                        print("\n请选择要指定的用户类型：")
                        print("1. 用户ID")
                        print("2. 用户名")
                        print("3. 昵称")
                        user_option = (await ainput("请输入选项编号（1/2/3，直接回车表示监听所有用户）: ")).strip()

                        if user_option in ['1', '2', '3']:
                            users_input = (await ainput("请输入对应的用户标识，多个用逗号分隔: ")).strip()
                            if users_input:
                                user_list = [u.strip() for u in users_input.split(',')]
                                user_set = set()
                                for u in user_list:
                                    if user_option == '1':
                                        # 用户ID
                                        if u.isdigit():
                                            user_set.add(int(u))
                                        else:
                                            print(f"用户ID应为数字，输入无效：{u}")
                                    elif user_option == '2':
                                        # 用户名
                                        user_set.add(u.lower())  # 用户名统一转换为小写
                                    elif user_option == '3':
                                        # 昵称
                                        user_set.add(u)
                            else:
                                user_set = set()
                        else:
                            user_option = None
                            user_set = set()  # 未选择或直接回车，监听所有用户

                        KEYWORD_CONFIG[keyword_input]['users'] = user_set
                        KEYWORD_CONFIG[keyword_input]['user_option'] = user_option
                        print(f"监听的用户已更新为：{user_set if user_set else '所有用户'}")

                    print(f"关键词 '{keyword_input}' 的新配置：{KEYWORD_CONFIG[keyword_input]}")
                else:
                    print("该关键词未在列表中")

            elif command == 'removekeyword':
                keyword_input = (await ainput("请输入要移除的关键词: ")).strip()
                if keyword_input in KEYWORD_CONFIG:
                    del KEYWORD_CONFIG[keyword_input]
                    print(f"已移除关键词: {keyword_input}")
                else:
                    print("该关键词未在列表中")

            elif command == 'showkeywords':
                print("\n=== 当前关键词及配置 ===")
                for keyword, config in KEYWORD_CONFIG.items():
                    print(f"关键词: {keyword}, 配置: {config}")

            elif command == 'addext':
                extensions_input = (await ainput("请输入文件后缀名，多个后缀名用逗号分隔 (例如: .pdf,.docx): ")).strip().lower()
                extensions = [ext.strip() for ext in extensions_input.split(',')]
                extensions = ['.' + ext if not ext.startswith('.') else ext for ext in extensions]

                chat_ids_input = (await ainput("请输入要监听的对话ID，多个ID用逗号分隔: ")).strip()
                chat_ids = [int(tid.strip()) for tid in chat_ids_input.split(',')]

                users_input = (await ainput("是否只监听指定用户发送的文件？输入用户名或用户ID，多个用逗号分隔（留空表示监听所有用户）: ")).strip()
                if users_input:
                    user_list = [u.strip().lower() for u in users_input.split(',')]
                    user_set = set()
                    for u in user_list:
                        if u.isdigit():
                            user_set.add(int(u))  # 用户ID
                        else:
                            user_set.add(u)  # 用户名
                else:
                    user_set = set()

                auto_forward = (await ainput("是否启用自动转发功能？(yes/no): ")).strip().lower() == 'yes'

                # 如果启用了自动转发，设置转发目标
                if auto_forward:
                    target_ids_input = (await ainput("请输入自动转发的目标对话ID，多个ID用逗号分隔: ")).strip()
                    target_ids = [int(tid.strip()) for tid in target_ids_input.split(',')]
                else:
                    target_ids = []

                for extension in extensions:
                    config = {
                        'chats': chat_ids,
                        'auto_forward': auto_forward,
                        'users': user_set
                    }
                    if auto_forward:
                        config['forward_targets'] = target_ids
                        print(f"已设置文件后缀名 '{extension}' 的自动转发目标ID: {target_ids}")
                    FILE_EXTENSION_CONFIG[extension] = config
                    print(f"已添加文件后缀名 '{extension}'，配置：{config}")

            elif command == 'modifyext':
                extension_input = (await ainput("请输入要修改的文件后缀名 (例如: .pdf): ")).strip().lower()
                if not extension_input.startswith('.'):
                    extension_input = '.' + extension_input
                if extension_input in FILE_EXTENSION_CONFIG:
                    config = FILE_EXTENSION_CONFIG[extension_input]
                    print(f"当前配置：{config}")

                    # 提示用户选择要修改的项
                    print("\n可修改的项：")
                    print("1. 文件后缀名")
                    print("2. 监听的对话ID")
                    print("3. 自动转发设置")
                    print("4. 监听的用户")

                    options = (await ainput("请输入要修改的项，多个项用逗号分隔（例如：1,3）: ")).strip()
                    options = [opt.strip() for opt in options.split(',')]

                    # 修改文件后缀名
                    if '1' in options:
                        new_extension = (await ainput("请输入新的文件后缀名 (例如: .docx): ")).strip().lower()
                        if not new_extension.startswith('.'):
                            new_extension = '.' + new_extension
                        # 删除旧的后缀名配置，添加新的
                        FILE_EXTENSION_CONFIG[new_extension] = FILE_EXTENSION_CONFIG.pop(extension_input)
                        extension_input = new_extension  # 更新后缀名变量
                        print(f"文件后缀名已修改为：{new_extension}")

                    # 修改监听的对话ID
                    if '2' in options:
                        chat_ids_input = (await ainput("请输入新的监听的对话ID，多个ID用逗号分隔: ")).strip()
                        chat_ids = [int(tid.strip()) for tid in chat_ids_input.split(',')]
                        FILE_EXTENSION_CONFIG[extension_input]['chats'] = chat_ids
                        print(f"监听的对话ID已更新为：{chat_ids}")

                    # 修改自动转发设置
                    if '3' in options:
                        auto_forward = (await ainput("是否启用自动转发功能？(yes/no): ")).strip().lower() == 'yes'
                        FILE_EXTENSION_CONFIG[extension_input]['auto_forward'] = auto_forward
                        if auto_forward:
                            target_ids_input = (await ainput("请输入自动转发的目标对话ID，多个ID用逗号分隔: ")).strip()
                            target_ids = [int(tid.strip()) for tid in target_ids_input.split(',')]
                            FILE_EXTENSION_CONFIG[extension_input]['forward_targets'] = target_ids
                            print(f"自动转发目标ID已更新为：{target_ids}")
                        else:
                            FILE_EXTENSION_CONFIG[extension_input]['forward_targets'] = []
                            print("已关闭自动转发功能")

                    # 修改监听的用户
                    if '4' in options:
                        users_input = (await ainput("请输入新的用户名或用户ID，多个用逗号分隔（留空表示监听所有用户）: ")).strip()
                        if users_input:
                            user_list = [u.strip().lower() for u in users_input.split(',')]
                            user_set = set()
                            for u in user_list:
                                if u.isdigit():
                                    user_set.add(int(u))
                                else:
                                    user_set.add(u)
                        else:
                            user_set = set()
                        FILE_EXTENSION_CONFIG[extension_input]['users'] = user_set
                        print(f"监听的用户已更新为：{user_set if user_set else '所有用户'}")

                    print(f"文件后缀名 '{extension_input}' 的新配置：{FILE_EXTENSION_CONFIG[extension_input]}")
                else:
                    print("该文件后缀名未在列表中")

            elif command == 'removeext':
                extension = (await ainput("请输入要移除的文件后缀名 (例如: .pdf): ")).strip().lower()
                if not extension.startswith('.'):
                    extension = '.' + extension
                if extension in FILE_EXTENSION_CONFIG:
                    del FILE_EXTENSION_CONFIG[extension]
                    print(f"已移除文件后缀名: {extension}")
                else:
                    print("该文件后缀名未在列表中")

            elif command == 'showext':
                print("\n=== 当前文件后缀名及配置 ===")
                for ext, config in FILE_EXTENSION_CONFIG.items():
                    print(f"文件后缀名: {ext}, 配置: {config}")

            elif command == 'schedule':
                # 添加定时消息
                target_id = int((await ainput("请输入目标对话ID: ")).strip())
                message = (await ainput("请输入要发送的消息: ")).strip()
                cron_expression = (await ainput("请输入Cron表达式: ")).strip()
                random_offset_input = (await ainput("请输入随机时间误差（秒），默认为0: ")).strip()
                random_offset = int(random_offset_input) if random_offset_input else 0
                delete_after_sending = (await ainput("是否在发送后删除消息？(yes/no): ")).strip().lower() == 'yes'
                job = schedule_message(target_id, message, cron_expression, random_offset, delete_after_sending)
                SCHEDULED_MESSAGES.append({
                    'job_id': job.id,
                    'target_id': target_id,
                    'message': message,
                    'cron': cron_expression,
                    'random_offset': random_offset,
                    'delete_after_sending': delete_after_sending
                })
                print(f"已添加定时消息，Cron表达式: {cron_expression}，目标ID: {target_id}，Job ID: {job.id}")

            elif command == 'modifyschedule':
                # 修改定时消息
                job_id = (await ainput("请输入要修改的定时消息的Job ID: ")).strip()
                job = scheduler.get_job(job_id)
                if job:
                    # 查找定时消息配置
                    sched = next((s for s in SCHEDULED_MESSAGES if s['job_id'] == job_id), None)
                    if sched:
                        print(f"当前配置：{sched}")

                        # 提示用户选择要修改的项
                        print("\n可修改的项：")
                        print("1. 目标对话ID")
                        print("2. 消息内容")
                        print("3. Cron表达式")
                        print("4. 随机时间误差")
                        print("5. 发送后删除消息")

                        options = (await ainput("请输入要修改的项，多个项用逗号分隔（例如：1,3）: ")).strip()
                        options = [opt.strip() for opt in options.split(',')]

                        # 修改目标对话ID
                        if '1' in options:
                            target_id = int((await ainput("请输入新的目标对话ID: ")).strip())
                            sched['target_id'] = target_id
                            print(f"目标对话ID已更新为：{target_id}")

                        # 修改消息内容
                        if '2' in options:
                            message = (await ainput("请输入新的消息内容: ")).strip()
                            sched['message'] = message
                            print("消息内容已更新")

                        # 修改Cron表达式
                        if '3' in options:
                            cron_expression = (await ainput("请输入新的Cron表达式: ")).strip()
                            sched['cron'] = cron_expression
                            print(f"Cron表达式已更新为：{cron_expression}")

                        # 修改随机时间误差
                        if '4' in options:
                            random_offset_input = (await ainput("请输入新的随机时间误差（秒），默认为0: ")).strip()
                            random_offset = int(random_offset_input) if random_offset_input else 0
                            sched['random_offset'] = random_offset
                            print(f"随机时间误差已更新为：{random_offset} 秒")

                        # 修改发送后删除消息
                        if '5' in options:
                            delete_after_sending = (await ainput("是否在发送后删除消息？(yes/no): ")).strip().lower() == 'yes'
                            sched['delete_after_sending'] = delete_after_sending
                            print(f"发送后删除消息已更新为：{'是' if delete_after_sending else '否'}")

                        # 移除旧的Job并重新调度
                        job.remove()
                        new_job = scheduler.add_job(
                            send_scheduled_message,
                            CronTrigger.from_crontab(sched['cron'], timezone=pytz.timezone('Asia/Shanghai')),
                            args=[
                                sched['target_id'],
                                sched['message'],
                                sched.get('random_offset', 0),
                                sched.get('delete_after_sending', False)
                            ],
                            id=job_id
                        )
                        print(f"定时消息 '{job_id}' 已更新")
                    else:
                        print("未找到指定的定时消息配置")
                else:
                    print("未找到指定的定时消息")

            elif command == 'removeschedule':
                job_id = (await ainput("请输入要删除的定时消息的Job ID: ")).strip()
                job = scheduler.get_job(job_id)
                if job:
                    job.remove()
                    SCHEDULED_MESSAGES = [s for s in SCHEDULED_MESSAGES if s['job_id'] != job_id]
                    print(f"已删除定时消息，Job ID: {job_id}")
                else:
                    print("未找到指定的定时消息")

            elif command == 'showschedule':
                print("\n=== 定时消息列表 ===")
                for sched in SCHEDULED_MESSAGES:
                    print(f"Job ID: {sched['job_id']}, 目标ID: {sched['target_id']}, 消息: {sched['message']}, Cron: {sched['cron']}, 随机时间误差: {sched.get('random_offset', 0)} 秒, 发送后删除: {'是' if sched.get('delete_after_sending', False) else '否'}")

            elif command == 'start':
                monitor_active = True
                print("监控已启动")

            elif command == 'stop':
                monitor_active = False
                print("监控已停止")

            elif command == 'exit':
                print("正在退出程序...")
                scheduler.shutdown()
                await client.disconnect()
                return

            else:
                print("未知命令，请重新输入")

        except Exception as e:
            error_message = repr(e)
            logger.error(f"执行命令时出错: {error_message}")
            print(f"执行命令时出错: {error_message}")

# === Telegram登录处理 ===
async def telegram_login(client):
    """处理Telegram登录流程"""
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

# === 主程序 ===
async def main():
    """主程序"""
    global monitor_active, client, scheduler, own_user_id  # 声明全局变量，包括 own_user_id

    logger.info('启动Telegram监控程序...')

    # 在运行时获取 api_id 和 api_hash
    api_id = int(input('请输入您的 api_id: ').strip())
    api_hash = input('请输入您的 api_hash: ').strip()

    # 创建并启动客户端
    client = TelegramClient('session_name', api_id, api_hash)

    try:
        # 先连接客户端
        await client.connect()

        # 检查是否需要登录
        if not await client.is_user_authorized():
            await telegram_login(client)

        # 获取当前用户的 ID
        me = await client.get_me()
        own_user_id = me.id  # 保存当前用户的 ID

        # 注册消息处理器，不使用 chats 参数
        client.add_event_handler(message_handler, events.NewMessage())

        # 启动APScheduler
        scheduler.start()

        print("\n=== Telegram消息监控程序 ===")
        print("请先设置监控参数")

        # 运行 handle_commands 和 client.run_until_disconnected
        await asyncio.gather(
            handle_commands(client),
            client.run_until_disconnected()
        )

    except Exception as e:
        error_message = repr(e)
        logger.error(f'运行时发生错误：{error_message}')
    finally:
        # 确保在程序结束时断开连接
        await client.disconnect()
        scheduler.shutdown()
        logger.info('程序已退出')

# === 程序入口 ===
if __name__ == '__main__':
    # 初始化全局变量
    monitor_active = False
    client = None            # Telegram 客户端实例
    scheduler = AsyncIOScheduler()  # 初始化APScheduler

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info('程序被用户中断')
    except Exception as e:
        error_message = repr(e)
        logger.error(f'程序发生错误：{error_message}')
