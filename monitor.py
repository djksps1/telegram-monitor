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
import shutil
import base64
from openai import OpenAI

# 配置OneAPI
ONEAPI_KEY = "你的 OneAPI 令牌"  # 替换为实际的 OneAPI 令牌
ONEAPI_BASE_URL = "http://你的 OneAPI 地址/v1"  # OneAPI 的服务地址

client_ai = OpenAI(
    api_key=ONEAPI_KEY,
    base_url=ONEAPI_BASE_URL
)

# === 配置部分 ===
SMTP_SERVER = "smtp.qq.com"          # SMTP 服务器，例如 QQ 邮箱
SMTP_PORT = 465                      # SMTP 端口，通常为 465
SENDER_EMAIL = "您的邮箱@example.com"  # 发件人邮箱
EMAIL_PASSWORD = "您的邮箱授权码"      # 邮箱授权码或密码
RECIPIENT_EMAIL = "收件人邮箱@example.com"  # 收件人邮箱
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
KEYWORD_CONFIG = {}
FILE_EXTENSION_CONFIG = {}
SCHEDULED_MESSAGES = []

ALL_MESSAGES_CONFIG = {}
BUTTON_KEYWORD_CONFIG = {}
IMAGE_BUTTON_MONITOR = set()  # 定义IMAGE_BUTTON_MONITOR

processed_messages = set()

monitor_active = False
client = None
scheduler = AsyncIOScheduler()

# === 异步输入函数 ===
async def ainput(prompt: str = '') -> str:
    """自定义异步输入函数，确保正确处理编码"""
    loop = asyncio.get_event_loop()
    print(prompt, end='', flush=True)
    return (await loop.run_in_executor(None, sys.stdin.readline)).rstrip('\n')

def send_email(message_text):
    """发送邮件"""
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


async def message_handler(event):
    global monitor_active, own_user_id, processed_messages

    if not monitor_active:
        return

    chat_id = event.chat_id
    message_id = event.message.id
    message_text = event.raw_text or ''
    message_text_lower = message_text.lower().strip()

    if (chat_id, message_id) in processed_messages:
        return
    processed_messages.add((chat_id, message_id))

    try:
        sender = await event.get_sender()
        sender_id = sender.id if sender else None

        if sender_id == own_user_id:
            return

        # 全量监控
        if chat_id in ALL_MESSAGES_CONFIG:
            config = ALL_MESSAGES_CONFIG[chat_id]
            user_set = config.get('users', set())
            user_option = config.get('user_option')
            if match_user(sender, user_set, user_option):
                if config.get('email_notify'):
                    send_email(f"检测到来自对话 {chat_id} 的消息: {message_text}")
                if config.get('auto_forward'):
                    target_ids = config.get('forward_targets', [])
                    for target_id in target_ids:
                        await client.forward_messages(target_id, event.message)
                        logger.info(f"已转发对话 {chat_id} 的消息到ID: {target_id}")
        else:
            # 关键词监控
            handled = False
            for keyword, config in KEYWORD_CONFIG.items():
                if chat_id in config['chats']:
                    user_set = config.get('users', set())
                    user_option = config.get('user_option')

                    if not match_user(sender, user_set, user_option):
                        continue

                    match_type = config.get('match_type', 'partial')

                    if match_type == 'exact':
                        if message_text_lower == keyword:
                            logger.info(f"检测到完全匹配关键词 '{keyword}' 在对话 {chat_id} 中的消息: {message_text}")
                            if config.get('email_notify'):
                                send_email(f"检测到完全匹配关键词 '{keyword}' 的消息: {message_text}")
                            if config.get('auto_forward'):
                                await auto_forward_message(event, keyword)
                            log_file = config.get('log_file')
                            if log_file:
                                try:
                                    with open(log_file, 'a', encoding='utf-8') as f:
                                        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 对话{chat_id} 完全匹配关键词'{keyword}': {message_text}\n")
                                    logger.info(f"已将匹配关键词 '{keyword}' 的消息写入文件: {log_file}")
                                except Exception as e:
                                    logger.error(f"写入文件 {log_file} 时发生错误：{e}")
                            handled = True
                            break

                    elif match_type == 'partial':
                        if keyword in message_text_lower:
                            logger.info(f"检测到关键词 '{keyword}' 在对话 {chat_id} 中的消息: {message_text}")
                            if config.get('email_notify'):
                                send_email(f"检测到关键词 '{keyword}' 的消息: {message_text}")
                            if config.get('auto_forward'):
                                await auto_forward_message(event, keyword)
                            log_file = config.get('log_file')
                            if log_file:
                                try:
                                    with open(log_file, 'a', encoding='utf-8') as f:
                                        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 对话{chat_id} 关键词'{keyword}': {message_text}\n")
                                    logger.info(f"已将匹配关键词 '{keyword}' 的消息写入文件: {log_file}")
                                except Exception as e:
                                    logger.error(f"写入文件 {log_file} 时发生错误：{e}")
                            handled = True
                            break

                    elif match_type == 'regex':
                        pattern = re.compile(rf'{keyword}')
                        match_obj = pattern.search(message_text)
                        if match_obj:
                            logger.info(f"检测到正则匹配 '{keyword}' 在对话 {chat_id} 中的消息: {message_text}")
                            if config.get('email_notify'):
                                send_email(f"检测到正则匹配 '{keyword}' 的消息: {message_text}")
                            if config.get('auto_forward'):
                                await auto_forward_message(event, keyword)
                            log_file = config.get('log_file')
                            if log_file:
                                try:
                                    with open(log_file, 'a', encoding='utf-8') as f:
                                        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 对话{chat_id} 正则匹配关键词'{keyword}': {message_text}\n")
                                    logger.info(f"已将匹配关键词 '{keyword}' 的消息写入文件: {log_file}")
                                except Exception as e:
                                    logger.error(f"写入文件 {log_file} 时发生错误：{e}")

                            # 新增发送正则匹配内容的逻辑
                            # 提取匹配的文本
                            matched_text = match_obj.group(0)
                            if 'regex_send_target_id' in config:
                                target_id = config['regex_send_target_id']
                                random_offset = config.get('regex_send_random_offset', 0)
                                delete_after_sending = config.get('regex_send_delete', False)
                                await send_regex_matched_message(target_id, matched_text, random_offset, delete_after_sending)

                            handled = True
                            break

            # 文件后缀名监控
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
                        config = FILE_EXTENSION_CONFIG.get(file_extension)
                        if config and chat_id in config['chats']:
                            user_set = config.get('users', set())
                            user_option = config.get('user_option')
                            if not match_user(sender, user_set, user_option):
                                return
                            logger.info(f"检测到文件后缀名 {file_extension} 的文件：{file_name} 在对话 {chat_id} 中")

                            if config.get('email_notify'):
                                send_email(f"检测到文件后缀名 '{file_extension}' 的消息：{file_name}")
                            if config.get('auto_forward'):
                                await auto_forward_file_message(event, file_extension)

        # 检查按钮关键词
        if event.message.buttons:
            for b_keyword, b_config in BUTTON_KEYWORD_CONFIG.items():
                if chat_id in b_config['chats']:
                    if match_user(sender, b_config.get('users', set()), b_config.get('user_option')):
                        for row_i, row in enumerate(event.message.buttons):
                            for col_i, button in enumerate(row):
                                if b_keyword in button.text.lower():
                                    await event.message.click(row_i, col_i)
                                    logger.info(f"已点击对话 {chat_id} 中包含按钮关键词 '{b_keyword}' 的按钮: {button.text}")
                                    return

        # 图片+按钮监听
        if chat_id in IMAGE_BUTTON_MONITOR and event.message.buttons:
            # 下载图片
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
                max_retries = 2  # 最大尝试次数为2次
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
                            # 删除图片文件
                            try:
                                if os.path.exists(image_path):
                                    os.remove(image_path)
                                    logger.info(f"已删除图片文件：{image_path}")
                            except Exception as e:
                                logger.error(f"删除图片文件时发生错误: {e}")
                            return  # 结束此消息处理，不再继续点击按钮流程

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
        error_message = repr(e)
        logger.error(f'处理消息时发生错误：{error_message}')

def match_user(sender, user_set, user_option):
    if not user_set:
        return True
    if not sender:
        return False

    sender_id = sender.id
    sender_username = sender.username.lower() if sender.username else None
    sender_first_name = sender.first_name if sender.first_name else ''
    sender_last_name = sender.last_name if sender.last_name else ''
    sender_full_name = f"{sender_first_name} {sender_last_name}".strip()

    logger.info(f"匹配用户：sender_id={sender_id}, sender_username={sender_username}, sender_full_name={sender_full_name}, user_set={user_set}")

    if user_option == '1':
        return sender_id in user_set
    elif user_option == '2':
        return sender_username in user_set
    elif user_option == '3':
        return sender_full_name in user_set
    else:
        return True

async def send_regex_matched_message(target_id, matched_text, random_offset=0, delete_after_sending=False):
    try:
        if random_offset > 0:
            delay = random.uniform(0, random_offset)
            logger.info(f"等待 {delay:.2f} 秒后发送正则匹配内容到ID: {target_id}")
            await asyncio.sleep(delay)
        sent_message = await client.send_message(target_id, matched_text)
        logger.info(f"已发送正则匹配内容到ID: {target_id}")
        if delete_after_sending:
            await asyncio.sleep(5)
            await client.delete_messages(target_id, sent_message.id)
            logger.info(f"已删除发送的正则匹配内容消息，消息ID: {sent_message.id}")
    except Exception as e:
        error_message = repr(e)
        logger.error(f"发送正则匹配消息时发生错误：{error_message}")

async def auto_forward_message(event, keyword):
    try:
        config = KEYWORD_CONFIG[keyword]
        target_ids = config.get('forward_targets', [])
        
        chat_id = event.chat_id  # 获取当前消息的来源群组ID

        for target_id in target_ids:
            if target_id == chat_id:
                logger.info(f"转发目标ID({target_id})与监控群组({chat_id})相同，跳过转发以避免循环。")
                continue
            await client.forward_messages(target_id, event.message)
            logger.info(f"已将关键词 '{keyword}' 消息转发到ID: {target_id}")
    except Exception as e:
        error_message = repr(e)
        logger.error(f"自动转发消息时发生错误：{error_message}")

async def auto_forward_file_message(event, file_extension):
    try:
        config = FILE_EXTENSION_CONFIG[file_extension]
        target_ids = config.get('forward_targets', [])
        chat_id = event.chat_id  
        for target_id in target_ids:
            # 如果转发目标与当前监控群组是同一个，则跳过
            if target_id == chat_id:
                logger.info(f"转发目标ID({target_id})与监控群组({chat_id})相同，跳过转发以避免循环。")
                continue

            await client.forward_messages(target_id, event.message)
            logger.info(f"已将包含文件{file_extension}的消息转发到ID: {target_id}")
    except Exception as e:
        error_message = repr(e)
        logger.error(f"自动转发文件消息时发生错误：{error_message}")

def schedule_message(target_id, message, cron_expression, random_offset=0, delete_after_sending=False):
    job = scheduler.add_job(
        send_scheduled_message,
        CronTrigger.from_crontab(cron_expression, timezone=pytz.timezone('Asia/Shanghai')),
        args=[target_id, message, random_offset, delete_after_sending]
    )
    logger.info(f"已添加定时消息，Cron表达式: {cron_expression}，目标ID: {target_id}")
    return job

async def send_scheduled_message(target_id, message, random_offset=0, delete_after_sending=False):
    try:
        if random_offset > 0:
            delay = random.uniform(0, random_offset)
            logger.info(f"等待 {delay:.2f} 秒后发送定时消息")
            await asyncio.sleep(delay)
        sent_message = await client.send_message(target_id, message)
        logger.info(f"已发送定时消息到ID: {target_id}")
        if delete_after_sending:
            await asyncio.sleep(5)
            await client.delete_messages(target_id, sent_message.id)
            logger.info(f"已删除发送的定时消息，消息ID: {sent_message.id}")
    except Exception as e:
        error_message = repr(e)
        logger.error(f"发送定时消息时发生错误：{error_message}")

async def handle_commands(client):
    global monitor_active, KEYWORD_CONFIG, FILE_EXTENSION_CONFIG, SCHEDULED_MESSAGES, ALL_MESSAGES_CONFIG, BUTTON_KEYWORD_CONFIG

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
        print("14. addall - 添加全量监控的频道或群组")
        print("15. modifyall - 修改全量监控配置")
        print("16. removeall - 移除全量监控配置")
        print("17. showall - 显示所有全量监控配置")
        print("18. start - 开始监控")
        print("19. stop - 停止监控")
        print("20. exit - 退出程序")
        # 新增按钮关键词相关命令
        print("21. addbutton - 添加按钮关键词监控")
        print("22. modifybutton - 修改按钮关键词监控")
        print("23. removebutton - 移除按钮关键词监控")
        print("24. showbuttons - 显示所有按钮关键词监控")
        # 新增列出bot对话ID命令
        print("25. listbotchats - 列出与bot的对话chat_id")
        print("26. addimagelistener - 添加监听图片+按钮的对话ID")
        print("27. removeimagelistener - 移除监听图片+按钮的对话ID")
        print("28. showimagelistener - 显示所有监听的对话ID")


        command = (await ainput("\n请输入命令: ")).strip().lower()

        try:
            if command == 'list':
                print("\n=== 所有对话 ===")
                async for dialog in client.iter_dialogs():
                    if isinstance(dialog.entity, (Channel, Chat)):
                        print(f"ID: {dialog.id}, 名称: {dialog.name}, 类型: {'频道' if isinstance(dialog.entity, Channel) else '群组'}")
            elif command == 'addimagelistener':
                chat_id = int((await ainput("请输入要监听的对话ID: ")).strip())
                IMAGE_BUTTON_MONITOR.add(chat_id)
                print(f"已添加监听对话ID: {chat_id}")

            elif command == 'removeimagelistener':
                chat_id = int((await ainput("请输入要移除监听的对话ID: ")).strip())
                if chat_id in IMAGE_BUTTON_MONITOR:
                    IMAGE_BUTTON_MONITOR.remove(chat_id)
                    print(f"已移除监听对话ID: {chat_id}")
                else:
                    print("该对话ID不在监听列表中")

            elif command == 'showimagelistener':
                print("\n=== 当前监听图片+按钮的对话ID列表 ===")
                for cid in IMAGE_BUTTON_MONITOR:
                    print(cid)

            elif command == 'listbotchats':
                print("\n=== 与Bot的对话 ===")
                async for dialog in client.iter_dialogs():
                    if dialog.is_user and dialog.entity.bot:
                        print(f"Bot Name: {dialog.name}")
                        print(f"Chat ID: {dialog.id}")

            elif command == 'addbutton':
                b_keyword = (await ainput("请输入按钮关键词: ")).strip().lower()
                chat_ids_input = (await ainput("请输入要监听的对话ID，多个ID用逗号分隔: ")).strip()
                chat_ids = [int(tid.strip()) for tid in chat_ids_input.split(',')]

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
                                if u.isdigit():
                                    user_set.add(int(u))
                                else:
                                    print(f"用户ID应为数字，输入无效：{u}")
                            elif user_option == '2':
                                user_set.add(u.lower())
                            elif user_option == '3':
                                user_set.add(u)
                    else:
                        user_set = set()
                else:
                    user_option = None
                    user_set = set()

                BUTTON_KEYWORD_CONFIG[b_keyword] = {
                    'chats': chat_ids,
                    'users': user_set,
                    'user_option': user_option
                }
                print(f"已添加按钮关键词 '{b_keyword}'，配置：{BUTTON_KEYWORD_CONFIG[b_keyword]}")

            elif command == 'modifybutton':
                b_keyword = (await ainput("请输入要修改的按钮关键词: ")).strip().lower()
                if b_keyword in BUTTON_KEYWORD_CONFIG:
                    config = BUTTON_KEYWORD_CONFIG[b_keyword]
                    print(f"当前配置：{config}")

                    print("\n可修改的项：")
                    print("1. 按钮关键词")
                    print("2. 监听的对话ID")
                    print("3. 用户过滤")

                    options = (await ainput("请输入要修改的项，多个项用逗号分隔（例如：1,2）: ")).strip()
                    options = [opt.strip() for opt in options.split(',')]

                    if '1' in options:
                        new_b_keyword = (await ainput("请输入新的按钮关键词: ")).strip().lower()
                        BUTTON_KEYWORD_CONFIG[new_b_keyword] = BUTTON_KEYWORD_CONFIG.pop(b_keyword)
                        b_keyword = new_b_keyword
                        print(f"按钮关键词已修改为：{new_b_keyword}")

                    if '2' in options:
                        chat_ids_input = (await ainput("请输入新的监听的对话ID，多个ID用逗号分隔: ")).strip()
                        chat_ids = [int(tid.strip()) for tid in chat_ids_input.split(',')]
                        BUTTON_KEYWORD_CONFIG[b_keyword]['chats'] = chat_ids
                        print(f"监听的对话ID已更新为：{chat_ids}")

                    if '3' in options:
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
                                        if u.isdigit():
                                            user_set.add(int(u))
                                        else:
                                            print(f"用户ID应为数字，输入无效：{u}")
                                    elif user_option == '2':
                                        user_set.add(u.lower())
                                    elif user_option == '3':
                                        user_set.add(u)
                            else:
                                user_set = set()
                        else:
                            user_option = None
                            user_set = set()

                        BUTTON_KEYWORD_CONFIG[b_keyword]['users'] = user_set
                        BUTTON_KEYWORD_CONFIG[b_keyword]['user_option'] = user_option
                        print(f"用户过滤已更新为：{user_set if user_set else '所有用户'}")

                    print(f"按钮关键词 '{b_keyword}' 的新配置：{BUTTON_KEYWORD_CONFIG[b_keyword]}")
                else:
                    print("该按钮关键词未在列表中")

            elif command == 'removebutton':
                b_keyword = (await ainput("请输入要移除的按钮关键词: ")).strip().lower()
                if b_keyword in BUTTON_KEYWORD_CONFIG:
                    del BUTTON_KEYWORD_CONFIG[b_keyword]
                    print(f"已移除按钮关键词: {b_keyword}")
                else:
                    print("该按钮关键词未在列表中")

            elif command == 'showbuttons':
                print("\n=== 当前按钮关键词及配置 ===")
                for b_keyword, config in BUTTON_KEYWORD_CONFIG.items():
                    print(f"按钮关键词: {b_keyword}, 配置: {config}")
            elif command == 'addall':
                chat_id = int((await ainput("请输入要全量监控的对话ID（频道或群组ID）: ")).strip())
                
                print("\n请选择要指定的用户类型：")
                print("1. 用户ID")
                print("2. 用户名")
                print("3. 昵称")
                user_option = (await ainput("请输入选项编号（1/2/3，直接回车表示监听所有用户）: ")).strip()

                if user_option in ['1', '2', '3']:
                    users_input = (await ainput("请输入对应的用户标识，多个用逗号分隔（留空表示所有用户）: ")).strip()
                    if users_input:
                        user_list = [u.strip() for u in users_input.split(',')]
                        user_set = set()
                        for u in user_list:
                            if user_option == '1':
                                if u.isdigit():
                                    user_set.add(int(u))
                                else:
                                    print(f"用户ID应为数字，输入无效：{u}")
                            elif user_option == '2':
                                user_set.add(u.lower())
                            elif user_option == '3':
                                user_set.add(u)
                    else:
                        user_set = set()
                else:
                    user_option = None
                    user_set = set()

                auto_forward = (await ainput("是否启用自动转发功能？(yes/no): ")).strip().lower() == 'yes'
                email_notify = (await ainput("是否启用邮件通知功能？(yes/no): ")).strip().lower() == 'yes'

                if auto_forward:
                    target_ids_input = (await ainput("请输入自动转发的目标对话ID，多个ID用逗号分隔: ")).strip()
                    target_ids = [int(tid.strip()) for tid in target_ids_input.split(',')]
                else:
                    target_ids = []

                ALL_MESSAGES_CONFIG[chat_id] = {
                    'auto_forward': auto_forward,
                    'email_notify': email_notify,
                    'forward_targets': target_ids,
                    'users': user_set,
                    'user_option': user_option
                }
                print(f"已添加对话 {chat_id} 的全量监控配置：{ALL_MESSAGES_CONFIG[chat_id]}")

            elif command == 'modifyall':
                chat_id = int((await ainput("请输入要修改的全量监控的对话ID: ")).strip())
                if chat_id in ALL_MESSAGES_CONFIG:
                    config = ALL_MESSAGES_CONFIG[chat_id]
                    print(f"当前配置：{config}")

                    print("\n可修改的项：")
                    print("1. 自动转发设置")
                    print("2. 邮件通知设置")
                    print("3. 转发目标")
                    print("4. 用户过滤")

                    options = (await ainput("请输入要修改的项，多个项用逗号分隔（例如：1,3）: ")).strip()
                    options = [opt.strip() for opt in options.split(',')]

                    if '1' in options:
                        auto_forward = (await ainput("是否启用自动转发功能？(yes/no): ")).strip().lower() == 'yes'
                        ALL_MESSAGES_CONFIG[chat_id]['auto_forward'] = auto_forward
                        if auto_forward:
                            target_ids_input = (await ainput("请输入自动转发的目标对话ID，多个ID用逗号分隔: ")).strip()
                            target_ids = [int(tid.strip()) for tid in target_ids_input.split(',')]
                            ALL_MESSAGES_CONFIG[chat_id]['forward_targets'] = target_ids
                            print(f"自动转发目标ID已更新为：{target_ids}")
                        else:
                            ALL_MESSAGES_CONFIG[chat_id]['forward_targets'] = []
                            print("已关闭自动转发功能")

                    if '2' in options:
                        email_notify = (await ainput("是否启用邮件通知功能？(yes/no): ")).strip().lower() == 'yes'
                        ALL_MESSAGES_CONFIG[chat_id]['email_notify'] = email_notify
                        print(f"邮件通知功能已更新为：{'启用' if email_notify else '禁用'}")

                    if '3' in options:
                        # 修改转发目标
                        if ALL_MESSAGES_CONFIG[chat_id].get('auto_forward', False):
                            target_ids_input = (await ainput("请输入自动转发的目标对话ID，多个ID用逗号分隔: ")).strip()
                            target_ids = [int(tid.strip()) for tid in target_ids_input.split(',')]
                            ALL_MESSAGES_CONFIG[chat_id]['forward_targets'] = target_ids
                            print(f"自动转发目标ID已更新为：{target_ids}")
                        else:
                            print("当前未启用自动转发功能，请先启用后再设置目标。")

                    if '4' in options:
                        # 修改用户过滤
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
                                        if u.isdigit():
                                            user_set.add(int(u))
                                        else:
                                            print(f"用户ID应为数字，输入无效：{u}")
                                    elif user_option == '2':
                                        user_set.add(u.lower())
                                    elif user_option == '3':
                                        user_set.add(u)
                            else:
                                user_set = set()
                        else:
                            user_option = None
                            user_set = set()

                        ALL_MESSAGES_CONFIG[chat_id]['users'] = user_set
                        ALL_MESSAGES_CONFIG[chat_id]['user_option'] = user_option
                        print(f"监听的用户已更新为：{user_set if user_set else '所有用户'}")

                    print(f"对话 {chat_id} 的全量监控新配置：{ALL_MESSAGES_CONFIG[chat_id]}")
                else:
                    print("该对话未在全量监控列表中")

            elif command == 'removeall':
                chat_id = int((await ainput("请输入要移除全量监控的对话ID: ")).strip())
                if chat_id in ALL_MESSAGES_CONFIG:
                    del ALL_MESSAGES_CONFIG[chat_id]
                    print(f"已移除对话 {chat_id} 的全量监控配置")
                else:
                    print("该对话未在全量监控列表中")

            elif command == 'showall':
                print("\n=== 当前全量监控及配置 ===")
                for c_id, config in ALL_MESSAGES_CONFIG.items():
                    print(f"对话ID: {c_id}, 配置: {config}")

            elif command == 'addkeyword':
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

                log_to_file = (await ainput("是否将匹配的消息文本写入指定的.txt文件？(yes/no): ")).strip().lower() == 'yes'
                if log_to_file:
                    log_file = (await ainput("请输入要记录消息的文本文件名称（例如 matched_messages.txt）: ")).strip()
                else:
                    log_file = None

                if auto_forward:
                    target_ids_input = (await ainput("请输入自动转发的目标对话ID，多个ID用逗号分隔: ")).strip()
                    target_ids = [int(tid.strip()) for tid in target_ids_input.split(',')]
                else:
                    target_ids = []

                # 新增当 match_type == 'regex' 时，询问是否将匹配到的内容发送到指定对话，并设置延时删除选项
                regex_send_target_id = None
                regex_send_random_offset = 0
                regex_send_delete = False
                if match_type == 'regex':
                    regex_send = (await ainput("是否将正则匹配到的内容发送到指定对话？(yes/no): ")).strip().lower() == 'yes'
                    if regex_send:
                        regex_send_target_id = int((await ainput("请输入发送匹配结果的目标对话ID: ")).strip())
                        random_offset_input = (await ainput("请输入随机延时（秒），默认为0: ")).strip()
                        regex_send_random_offset = int(random_offset_input) if random_offset_input else 0
                        regex_send_delete = (await ainput("是否在发送后删除该消息？(yes/no): ")).strip().lower() == 'yes'

                for keyword in keywords:
                    config = {
                        'chats': chat_ids,
                        'auto_forward': auto_forward,
                        'email_notify': email_notify,
                        'match_type': match_type,
                        'users': user_set,
                        'user_option': user_option
                    }
                    if auto_forward:
                        config['forward_targets'] = target_ids
                        print(f"已设置关键词 '{keyword}' 的自动转发目标ID: {target_ids}")

                    if log_file:
                        config['log_file'] = log_file
                        print(f"匹配的消息将记录到文件: {log_file}")

                    # 如果是正则匹配类型并且用户选择了发送匹配内容的功能，则记录下来
                    if match_type == 'regex' and regex_send_target_id is not None:
                        config['regex_send_target_id'] = regex_send_target_id
                        config['regex_send_random_offset'] = regex_send_random_offset
                        config['regex_send_delete'] = regex_send_delete
                        print(f"正则匹配结果将发送到ID: {regex_send_target_id}, 随机延时: {regex_send_random_offset}秒, 发送后删除: {regex_send_delete}")

                    KEYWORD_CONFIG[keyword] = config
                    print(f"已添加关键词 '{keyword}'，配置：{config}")


            elif command == 'modifykeyword':
                keyword_input = (await ainput("请输入要修改的关键词: ")).strip()
                if keyword_input in KEYWORD_CONFIG:
                    config = KEYWORD_CONFIG[keyword_input]
                    print(f"当前配置：{config}")

                    # 增加修改项说明
                    print("\n可修改的项：")
                    print("1. 关键词")
                    print("2. 监听的对话ID")
                    print("3. 自动转发设置")
                    print("4. 邮件通知设置")
                    print("5. 匹配类型")
                    print("6. 监听的用户")
                    print("7. 记录到文件的设置")  

                    if config.get('match_type') == 'regex':
                        print("8. 正则匹配内容发送设置")  # 新增选项

                    options = (await ainput("请输入要修改的项，多个项用逗号分隔（例如：1,3）: ")).strip()
                    options = [opt.strip() for opt in options.split(',')]

                    if '1' in options:
                        match_type = config.get('match_type', 'partial')
                        if match_type != 'regex':
                            new_keyword = (await ainput("请输入新的关键词: ")).strip()
                        else:
                            new_keyword = (await ainput("请输入新的正则表达式模式: ")).strip()
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
                            new_match_type = 'exact'
                        elif match_option == '2':
                            new_match_type = 'partial'
                        elif match_option == '3':
                            new_match_type = 'regex'
                        else:
                            print("无效的匹配类型，默认使用关键词匹配")
                            new_match_type = 'partial'
                        KEYWORD_CONFIG[keyword_input]['match_type'] = new_match_type
                        print(f"匹配类型已更新为：{new_match_type}")

                        # 如果从非regex转为regex，需要清理或新增正则相关配置
                        # 可以根据需要清理或保留此前的regex_send_*字段
                        if new_match_type != 'regex':
                            # 非regex类型则删除regex发送相关配置
                            KEYWORD_CONFIG[keyword_input].pop('regex_send_target_id', None)
                            KEYWORD_CONFIG[keyword_input].pop('regex_send_random_offset', None)
                            KEYWORD_CONFIG[keyword_input].pop('regex_send_delete', None)

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
                                        if u.isdigit():
                                            user_set.add(int(u))
                                        else:
                                            print(f"用户ID应为数字，输入无效：{u}")
                                    elif user_option == '2':
                                        user_set.add(u.lower())  # 用户名统一转换为小写
                                    elif user_option == '3':
                                        user_set.add(u)
                            else:
                                user_set = set()
                        else:
                            user_option = None
                            user_set = set()  # 未选择或直接回车，监听所有用户

                        KEYWORD_CONFIG[keyword_input]['users'] = user_set
                        KEYWORD_CONFIG[keyword_input]['user_option'] = user_option
                        print(f"监听的用户已更新为：{user_set if user_set else '所有用户'}")

                    if '7' in options:
                        log_to_file = (await ainput("是否将匹配的消息文本写入.txt文件？(yes/no): ")).strip().lower() == 'yes'
                        if log_to_file:
                            log_file = (await ainput("请输入要记录消息的文本文件名称: ")).strip()
                            KEYWORD_CONFIG[keyword_input]['log_file'] = log_file
                            print(f"匹配的消息将记录到文件: {log_file}")
                        else:
                            if 'log_file' in KEYWORD_CONFIG[keyword_input]:
                                del KEYWORD_CONFIG[keyword_input]['log_file']
                            print("已取消记录消息到文件的功能。")

                    # 如果当前是regex类型，并且用户选择了选项8，则修改正则发送相关配置
                    if '8' in options and KEYWORD_CONFIG[keyword_input].get('match_type') == 'regex':
                        regex_send = (await ainput("是否将正则匹配到的内容发送到指定对话？(yes/no): ")).strip().lower() == 'yes'
                        if regex_send:
                            regex_send_target_id = int((await ainput("请输入发送匹配结果的目标对话ID: ")).strip())
                            random_offset_input = (await ainput("请输入随机延时（秒），默认为0: ")).strip()
                            regex_send_random_offset = int(random_offset_input) if random_offset_input else 0
                            regex_send_delete = (await ainput("是否在发送后删除该消息？(yes/no): ")).strip().lower() == 'yes'
                            KEYWORD_CONFIG[keyword_input]['regex_send_target_id'] = regex_send_target_id
                            KEYWORD_CONFIG[keyword_input]['regex_send_random_offset'] = regex_send_random_offset
                            KEYWORD_CONFIG[keyword_input]['regex_send_delete'] = regex_send_delete
                            print(f"正则匹配结果将发送到ID: {regex_send_target_id}, 随机延时: {regex_send_random_offset}秒, 发送后删除: {regex_send_delete}")
                        else:
                            # 不发送则删除相关字段
                            KEYWORD_CONFIG[keyword_input].pop('regex_send_target_id', None)
                            KEYWORD_CONFIG[keyword_input].pop('regex_send_random_offset', None)
                            KEYWORD_CONFIG[keyword_input].pop('regex_send_delete', None)
                            print("已取消正则匹配结果的发送。")

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
                                user_set.add(u.lower())
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

                for extension in extensions:
                    config = {
                        'chats': chat_ids,
                        'auto_forward': auto_forward,
                        'email_notify': email_notify,  # 新增
                        'users': user_set,
                        'user_option': user_option
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
                                        user_set.add(u.lower())
                                    elif user_option == '3':
                                        # 昵称
                                        user_set.add(u)
                            else:
                                user_set = set()
                        else:
                            user_option = None
                            user_set = set()  # 未选择或直接回车，监听所有用户

                        FILE_EXTENSION_CONFIG[extension_input]['users'] = user_set
                        FILE_EXTENSION_CONFIG[extension_input]['user_option'] = user_option
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
    global monitor_active, client, scheduler, own_user_id

    logger.info('启动Telegram监控程序...')
    api_id = int(input('请输入您的 api_id: ').strip())
    api_hash = input('请输入您的 api_hash: ').strip()
    client = TelegramClient('session_name', api_id, api_hash)

    try:
        await client.connect()
        if not await client.is_user_authorized():
            await telegram_login(client)
        me = await client.get_me()
        own_user_id = me.id

        client.add_event_handler(message_handler, events.NewMessage())

        scheduler.start()

        print("\n=== Telegram消息监控程序 ===")
        print("请先设置监控参数")

        await asyncio.gather(
            handle_commands(client),
            client.run_until_disconnected()
        )

    except Exception as e:
        error_message = repr(e)
        logger.error(f'运行时发生错误：{error_message}')
    finally:
        await client.disconnect()
        scheduler.shutdown()
        logger.info('程序已退出')

if __name__ == '__main__':
    monitor_active = False
    client = None
    scheduler = AsyncIOScheduler()

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info('程序被用户中断')
    except Exception as e:
        error_message = repr(e)
        logger.error(f'程序发生错误：{error_message}')
