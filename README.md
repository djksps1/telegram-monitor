Telegram 消息监控程序
一个基于 Python 的 Telegram 消息监控程序，可用于监控指定的关键词、文件后缀名和文件名关键词，支持自动转发、邮件通知和定时消息发送等功能。

功能介绍
关键词监控：监控指定对话中的关键词，当检测到消息包含关键词时，可进行自动转发和邮件通知。
文件后缀名监控：监控指定对话中的特定文件类型，支持自动转发功能。
文件名关键词监控：监控文件名中包含特定关键词的文件，支持自动转发功能。
定时消息发送：使用 Cron 表达式定时向指定对话发送消息。
命令行交互：通过命令行界面进行配置和管理，支持添加、修改、删除和显示各种监控配置。
安装说明
1. 克隆或下载项目
bash
复制代码
git clone https://github.com/yourusername/telegram-monitor.git
cd telegram-monitor
2. 安装依赖库
请确保您的 Python 版本为 3.7 或以上。安装所需的 Python 库：

bash
复制代码
pip install -r requirements.txt
requirements.txt 文件内容：

复制代码
telethon
apscheduler
pytz
3. 获取 Telegram API ID 和 Hash
登录 Telegram API 开发者平台。
进入 "API development tools"。
创建一个新的应用，获取 api_id 和 api_hash。
使用指南
1. 配置邮件功能（可选）
如果需要使用邮件通知功能，编辑脚本中的邮件配置部分：

python
复制代码
# 邮件配置
SMTP_SERVER = "smtp.qq.com"          # SMTP 服务器，例如 QQ 邮箱
SMTP_PORT = 465                      # SMTP 端口，通常为 465
SENDER_EMAIL = "您的邮箱@example.com"  # 发件人邮箱
EMAIL_PASSWORD = "您的邮箱授权码"      # 邮箱授权码或密码
RECIPIENT_EMAIL = "收件人邮箱@example.com"  # 收件人邮箱
2. 运行程序
bash
复制代码
python telegram_monitor.py
3. 登录 Telegram
按照程序提示：

输入您的 api_id 和 api_hash。
输入您的 Telegram 手机号（需包含国际区号，例如 +8613800138000）。
输入收到的验证码或密码（如果启用了两步验证）。
4. 配置监控参数
在主菜单中，可以使用以下命令进行配置：

可用命令
list - 列出所有对话
addkeyword - 添加关键词监控
modifykeyword - 修改关键词监控
removekeyword - 移除关键词监控
showkeywords - 显示所有关键词及其配置
addext - 添加文件后缀名监控
modifyext - 修改文件后缀名监控
removeext - 移除文件后缀名监控
showext - 显示所有文件后缀名及其配置
addfilenamekeyword - 添加文件名关键词监控
modifyfilenamekeyword - 修改文件名关键词监控
removefilenamekeyword - 移除文件名关键词监控
showfilenamekeywords - 显示所有文件名关键词及其配置
schedule - 添加定时消息
modifyschedule - 修改定时消息
removeschedule - 删除定时消息
showschedule - 显示所有定时消息
start - 开始监控
stop - 停止监控
exit - 退出程序
5. 示例操作
添加关键词监控
bash
复制代码
请输入命令: addkeyword
请输入关键词，多个关键词用逗号分隔: 抽奖,中奖
请输入要监听的对话ID，多个ID用逗号分隔: -1001234567890,-1009876543210
是否启用自动转发功能？(yes/no): yes
是否启用邮件通知功能？(yes/no): yes
请输入自动转发的目标对话ID，多个ID用逗号分隔: -1001122334455
添加文件后缀名监控
bash
复制代码
请输入命令: addext
请输入文件后缀名，多个后缀名用逗号分隔 (例如: .pdf,.docx): .pdf,.docx
请输入要监听的对话ID，多个ID用逗号分隔: -1001234567890
是否启用自动转发功能？(yes/no): yes
请输入自动转发的目标对话ID，多个ID用逗号分隔: -1001122334455
添加文件名关键词监控
bash
复制代码
请输入命令: addfilenamekeyword
请输入文件名关键词，多个关键词用逗号分隔: 报告,总结
请输入要监听的对话ID，多个ID用逗号分隔: -1001234567890
是否启用自动转发功能？(yes/no): yes
请输入自动转发的目标对话ID，多个ID用逗号分隔: -1001122334455
添加定时消息
bash
复制代码
请输入命令: schedule
请输入目标对话ID: -1001234567890
请输入要发送的消息: 每日提醒：请及时提交日报。
请输入Cron表达式: 0 9 * * *  # 每天早上9点
开始监控
bash
复制代码
请输入命令: start
监控已启动
注意事项
权限要求：您的 Telegram 账号需要对监听的对话和自动转发的目标对话有足够的权限，尤其是发送和转发消息的权限。
Cron 表达式：定时消息使用 Cron 表达式，请确保格式正确。您可以使用在线工具生成 Cron 表达式。
日志查看：程序运行日志保存在 telegram_monitor.log 文件中，可用于调试和查看程序运行状态。
常见问题
1. 如何获取对话 ID？
使用 list 命令可以列出所有对话的名称和对应的 ID。
2. 程序报编码错误，如何解决？
请确保您的终端环境使用 UTF-8 编码。
在程序中已处理了编码问题，如仍有错误，请检查输入内容是否包含特殊字符。
3. 程序无法发送邮件，怎么办？
请检查您的邮件配置是否正确，特别是 SMTP 服务器、端口、邮箱和授权码。
有些邮箱需要开启 SMTP 服务或生成专用的授权码。
贡献
欢迎提交 Issue 和 Pull Request，帮助改进该项目。

许可证
MIT License

联系方式
如有任何疑问或建议，请联系 your_email@example.com。
