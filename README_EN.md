# Telegram Message Monitor Program

## Project Overview
This project is a Python-based Telegram message monitoring program that interacts with the Telegram API using the `Telethon` library.
After updates, the program supports the following main features:
- Monitor messages in specified conversations, matching keywords, regular expressions, or file extensions.
- Automatically forward matching messages, send email notifications, and log matching messages to local files.
- Send scheduled messages with optional random delay and post-send deletion.
- For messages with Inline buttons and images, automatically upload images to AI models for recognition and select/click buttons based on AI responses.
- If AI model call fails, retry once after 10 seconds; if still failing, abandon the current processing.
- For regex match results, forward matched text content to specified conversations (supports delay and post-send deletion).
- Full monitoring and user filtering functionality, selectively monitor messages based on user ID, username, or nickname.
- Support for user-configured proxy IP.

## Features
- **Keyword Monitoring**:  
  Monitor messages in specified conversations based on exact match, keyword match, or regular expression match rules.  
  Options include auto-forwarding, email notification, logging to local files, and auto-sending regex match results to specified conversations.
- **File Extension Monitoring**:  
  Monitor file messages of specified types (extensions), with options for auto-forwarding and email notification.
- **Full Monitoring**:  
  Monitor all messages in specified channels, groups, or conversations.
- **User Filtering**:  
  Monitor messages from specific users based on user ID, username, or nickname.
- **Scheduled Messages**:  
  Add scheduled message tasks using Cron expressions, with options for random delay and post-send deletion.
- **Button and Image Processing**:  
  When detecting images with Inline buttons, upload images to AI model for recognition and automatically click corresponding buttons based on model responses.  
  If first model call fails, retry once after 10 seconds; if still failing, abandon upload and delete local image file.
- **Logging**:  
  Log program operation process and error information to log files.

## Requirements
- Python 3.7 or above
- Install dependencies (Telethon, opanai, pytz, apscheduler, etc.)
- Requires Telegram `api_id` and `api_hash`
- SMTP email information (if email notification needed)
- One/New API `api_key` and `base_url` for AI model calls (if image recognition needed)

## Installation Guide
1. Clone or download project code:
```bash
git clone https://github.com/djksps1/tg-monitor.git
```
2. Install dependencies:
```bash
pip install -r requirements.txt
```
3. Obtain Telegram API credentials (`api_id` and `api_hash`).
4. Configure `ONE/NEW API_KEY` and `ONE/NEW API_BASE_URL` for AI model service.
5. Configure SMTP email information (if email notification needed).

## Usage Instructions
1. **Run Program**:
```bash
python monitor.py
```
2. **Login to Telegram**: First-time run requires entering `api_id` and `api_hash`, then enter your Telegram phone number and verification code. If two-step verification is enabled, password input is required.
3. **Set Monitor Parameters**: After startup, available command list will be displayed. Add/modify monitoring keywords, file extension monitoring, full monitoring, scheduled tasks as needed.
4. **Start Monitoring**: After configuration, enter `start` to begin monitoring.

## Available Commands
- `list`: List all conversations
- `addkeyword` / `modifykeyword` / `removekeyword` / `showkeywords`: Manage keyword monitoring
- `addext` / `modifyext` / `removeext` / `showext`: Manage file extension monitoring
- `addall` / `modifyall` / `removeall` / `showall`: Manage full monitoring configuration
- `schedule` / `modifyschedule` / `removeschedule` / `showschedule`: Manage scheduled message tasks
- `addbutton` / `modifybutton` / `removebutton` / `showbuttons`: Manage button keyword monitoring
- `addimagelistener` / `removeimagelistener` / `showimagelistener`: Manage listening conversation IDs for image+button messages
- `start` / `stop`: Start or stop monitoring
- `exit`: Exit program

## Feature Details
- **Keyword Monitoring**: Specify match type (exact, partial, regex), and configure target conversation, delay, and auto-delete options for regex type matches.
- **File Extension Monitoring**: Auto-forward and email notify when detecting specified extension files.
- **Full Monitoring**: Monitor all messages in specified channels or groups, with auto-forward, email notification, and user filtering options.
- **Button Keyword Monitoring**: Automatically click buttons containing specified keywords when detecting messages with Inline buttons.
- **Image and AI Model Processing**: When detecting messages with images and buttons, upload images to AI model for response. Retry once after 10 seconds if failed, abandon if still failing. Auto-click corresponding buttons based on response. Delete local image files immediately after completion.
- **Scheduled Messages**: Specify scheduled message sending time using Cron expressions, with random delay and post-send deletion options.

## Logging
- Log file: `telegram_monitor.log`
- Records program status, error information, and key events.

## Notes
- Please comply with Telegram terms of use to avoid account restrictions.
- Securely store your `api_id`, `api_hash`, and login session files to prevent account information leakage.
- Correctly configure SMTP information and email authorization code if email notification needed.
- Configure One/NEW API `api_key` and `base_url` for model calls.

## Common Issues
1. **Cannot Connect to Telegram**: Check network and proxy configuration, ensure Telegram accessibility.
2. **Email Sending Failed**: Ensure correct SMTP configuration and email authorization code setup.
3. **AI Model Call Failed**: Program will auto-retry once, abandon processing and delete image if still failing.
4. **Scheduled Tasks Not Executing**: Check Cron expression and timezone configuration, ensure `scheduler` is started.

## Contribution and Support
Suggestions and improvements welcome. Submit issues or pull requests for problems or new feature requests.

## License
This project is under MIT license.
