# Telegram Message Monitor Program

[中文版](./README.md)

## Project Overview
This project is a Python-based Telegram message monitoring program that interacts with the Telegram API using the [Telethon](https://github.com/LonamiWebs/Telethon) library.  
In the latest update, the program introduces several new features and improvements, including:

- **Advanced Message Monitoring**  
  Monitor messages in specified conversations based on exact keyword match, partial (keyword) match, or regular expression match rules.  
  When a match is found, the program can automatically forward messages, send email notifications, and log the matched messages to local files.  
  Non-matching messages will no longer generate extraneous log entries, ensuring cleaner logs.

- **File Extension Monitoring**  
  Detect file messages with specified extensions and perform auto-forwarding and email notifications.

- **Full Monitoring & User Filtering**  
  Monitor all messages in selected channels, groups, or conversations, with support for filtering by user ID, username, or nickname.  
  Only messages from the specified users will be processed and logged.

- **Scheduled Messages**  
  Schedule message sending tasks using Cron expressions, with options for random delay and automatic deletion after sending.

- **Button and Image Processing**  
  For messages that include inline buttons and images, the program automatically uploads the image to an AI model for recognition.  
  Based on the AI response, the program will automatically select and click the corresponding button.  
  If the AI model call fails, it will retry once after 10 seconds; if it still fails, the current processing is abandoned and the local image file is deleted.

- **Enhanced Configuration Management**  
  - **Export All Configurations**:  
    A new one-key export feature allows exporting the configurations for all logged-in accounts into a single JSON file.  
    In the exported file, each account's configuration is keyed by its account identifier (phone number).  
  - **Selective Import**:  
    When importing, the program reads the account identifiers from the configuration file and allows you to selectively import configurations for the accounts currently logged in.
    
- **Proxy Support**  
  Users can configure proxy settings (socks5, socks4, or HTTP) to ensure proper connectivity in restricted network environments.

- **Optimized Logging**  
  The log output has been refined to record only events that match monitoring rules (e.g., messages from the specified users).  
  Non-matching events will not clutter the log file, making it easier to track key events and errors.

## Features

- **Keyword Monitoring**  
  Monitor messages in specified conversations based on exact, partial, or regex matching.  
  Options include auto-forwarding, email notifications, local file logging, and even auto-sending regex match results to designated conversations (with configurable delay and auto-deletion).

- **File Extension Monitoring**  
  Automatically detect and process messages containing files with specified extensions, with options for auto-forwarding and email notifications.

- **Full Monitoring & User Filtering**  
  Monitor all messages in selected channels or groups.  
  Use user filtering (by user ID, username, or nickname) to ensure only messages from specific users are processed, reducing unnecessary log entries.

- **Scheduled Messages**  
  Schedule message-sending tasks using Cron expressions, with support for random delay and post-send deletion.

- **Button and Image Processing**  
  When a message contains images with inline buttons, the image is uploaded to an AI model for recognition.  
  The program then automatically clicks the corresponding button based on the AI response.  
  If the first AI call fails, it retries once after 10 seconds; if it still fails, the upload is abandoned and the local image file is deleted immediately.

- **Configuration Management**  
  - **Export All Configurations**:  
    Export all account configurations (including keyword, file extension, full monitoring, button monitoring, image listener, and scheduled tasks) into a single JSON file, where each account is keyed by its phone number.
  - **Selective Import**:  
    Import configurations based on the account identifiers present in the configuration file. This allows you to update configurations for only those accounts that are already logged in.

- **Proxy Support**  
  Enable proxy configuration to work around network restrictions.

- **Optimized Logging**  
  The program now logs only events that match the configured monitoring rules, keeping the log output concise and focused on important events.

## Requirements

- Python 3.7 or above
- Dependencies: Telethon, openai, pytz, apscheduler, PySocks, and others as listed in `requirements.txt`
- Telegram API credentials (`api_id` and `api_hash`)
- SMTP email information (if email notifications are required)
- One/New API credentials (`api_key` and `base_url`) for AI model calls (if image recognition is needed)

## Installation Guide

1. Clone or download the project code:
   ```bash
   git clone https://github.com/djksps1/telegram-monitor.git
```
 
1. Install the dependencies:

```bash
pip install -r requirements.txt
```
 
2. Obtain your Telegram API credentials (`api_id` and `api_hash`).
 
3. Configure the One/NEW API `api_key` and `api_base_url` for AI model services.

4. Configure the SMTP email information if you require email notifications.

## Usage Instructions 
 
1. **Run the Program** :

```bash
python monitor.py
```
 
2. **Login to Telegram** :
On the first run, you will be prompted to enter your `api_id` and `api_hash`, followed by your Telegram phone number and the verification code.
If two-step verification is enabled, you will also need to enter your password.
 
3. **Configure Monitoring Parameters** :
Once started, the program displays an interactive command list.
Use the commands to add/modify monitoring rules for keywords, file extensions, full monitoring, button monitoring, scheduled tasks, and image listeners.
 
4. **Manage Configurations** : 
  - Use the `exportallconfig` command to export the configurations for all accounts into a single JSON file (the account identifier will be the phone number).
 
  - Use the `importallconfig` command to selectively import configurations based on the account identifiers present in the configuration file.
 
5. **Start Monitoring** :
After configuration, enter the `start` command to begin monitoring.

## Available Commands 
 
- **Account Management**  
  - `addaccount` : Add a new account
 
  - `removeaccount` : Remove an account
 
  - `listaccount` : List all accounts
 
  - `switchaccount` : Switch the current working account
 
- **Configuration Management**  
  - `exportallconfig` : Export configurations for all accounts in one file
 
  - `importallconfig` : Import configurations selectively based on account identifiers
 
  - `blockbot` / `unblockbot` : Block or unblock specified Telegram Bots
 
- **Monitoring Configuration**  
  - `addkeyword` / `modifykeyword` / `removekeyword` / `showkeywords` : Manage keyword monitoring
 
  - `addext` / `modifyext` / `removeext` / `showext` : Manage file extension monitoring
 
  - `addall` / `modifyall` / `removeall` / `showall` : Manage full monitoring configuration
 
  - `addbutton` / `modifybutton` / `removebutton` / `showbuttons` : Manage button keyword monitoring
 
  - `addimagelistener` / `removeimagelistener` / `showimagelistener` : Manage image+button listener conversation IDs
 
- **Scheduled Task Management**  
  - `schedule` / `modifyschedule` / `removeschedule` / `showschedule` : Manage scheduled message tasks
 
- **Monitoring Control**  
  - `start` / `stop` : Start or stop monitoring
 
  - `exit` : Exit the program

## Feature Details 
 
- **Keyword Monitoring** 
Specify match types (exact, partial, regex) and configure options for auto-forwarding, email notifications, local file logging, and special handling of regex match results (including delay and auto-deletion).
 
- **File Extension Monitoring** 
Automatically processes messages with specified file extensions, with options for auto-forwarding and email notifications.
 
- **Full Monitoring & User Filtering** 
Monitor all messages in specified channels or groups, filtering by user ID, username, or nickname to process only relevant messages—reducing unnecessary log entries.
 
- **Button Keyword Monitoring** 
Automatically clicks buttons containing specified keywords when messages with inline buttons are detected.
 
- **Image and AI Model Processing** 
Upload images from messages (that include buttons) to an AI model for analysis.
If the AI call fails, the program will retry once after 10 seconds; if it still fails, the processing is abandoned and the local image file is deleted immediately.
 
- **Scheduled Messages** 
Set up scheduled message sending using Cron expressions, with options for random delay and post-send deletion.
 
- **Logging** 
All key events and errors are recorded in `telegram_monitor.log`.
Improved logging ensures that only events meeting the monitoring criteria are logged, keeping the log clean and focused.

## Logging 
 
- **Log File** : `telegram_monitor.log`
This file records program status, error messages, and key events.
With the new updates, only matching events are logged—non-matching messages will not clutter the log file.

## Notes 

- Please comply with Telegram’s terms of service to avoid account restrictions.
 
- Securely store your `api_id`, `api_hash`, and session files to prevent account information leakage.

- Ensure SMTP settings and email authorization codes are configured correctly if email notifications are used.
 
- Configure the One/NEW API `api_key` and `api_base_url` correctly for AI model calls.

## Common Issues 
 
1. **Cannot Connect to Telegram** 
Verify your network and proxy configurations, and ensure your API credentials are correct.
 
2. **Email Sending Failed** 
Check your SMTP settings and email authorization code.
 
3. **AI Model Call Failed** 
The program will auto-retry once. If it still fails, processing is abandoned and the local image is deleted.
 
4. **Scheduled Tasks Not Executing** 
Check your Cron expression and timezone settings, and make sure the scheduler is running.

## Contribution and Support 

Contributions, suggestions, and improvements are welcome. Please submit issues or pull requests for bug fixes or feature enhancements.

## License 

This project is licensed under the MIT License.
