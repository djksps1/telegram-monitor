# Telegram Message Monitor Program

[中文版](./README.md)

## Project Overview
This project is a Python-based Telegram message monitoring program that interacts with the Telegram API using the [Telethon](https://github.com/LonamiWebs/Telethon) library.  
In the latest update, the program introduces several new features and improvements, including:

- **Advanced Message Monitoring**  
  Monitor messages in specified conversations using exact, partial, or regular expression matching rules.  
  When a match is found, the program can automatically forward messages, send email notifications, and log the matched messages to local files.  
  Additionally, a **new reply feature** has been added:  
  When a keyword is detected, the program will wait for a configurable random delay and then reply to the original message in the same conversation.  
  The reply content is chosen at random from a set of pre-configured reply phrases.

- **File Extension Monitoring**  
  Detect file messages with specified extensions and perform auto-forwarding and email notifications.

- **Full Monitoring & User Filtering**  
  Monitor all messages in selected channels, groups, or conversations with support for filtering by user ID, username, or nickname.  
  Only messages from the specified users will be processed and logged, reducing unnecessary log entries.

- **Scheduled Messages**  
  Schedule message-sending tasks using Cron expressions, with options for random delay and automatic deletion after sending.

- **Button and Image Processing**  
  For messages that include inline buttons and images, the program automatically uploads the image to an AI model for recognition.  
  Based on the AI response, the program will automatically select and click the corresponding button.  
  If the AI call fails, it retries once after 10 seconds; if it still fails, processing is abandoned and the local image file is deleted immediately.

- **Enhanced Account Management (Numeric Sequence Management)**  
  Accounts are now managed by the order in which they are added.  
  Each account is assigned a numeric identifier starting from 1 (the earlier the account is added, the lower its number).  
  The account list displays both the sequence number and the associated phone number, and switching accounts can be done by simply entering the corresponding number.

- **Enhanced Configuration Management**  
  - **Export All Configurations**:  
    A one-key export feature allows you to export the configurations for all logged-in accounts into a single JSON file.  
    In the exported file, each account’s configuration is keyed by its account identifier (phone number).  
  - **Selective Import**:  
    When importing, the program reads the account identifiers from the configuration file and allows you to selectively import configurations for the currently logged-in accounts.  
    The export/import process now fully supports the new reply functionality fields (reply enabled flag, reply phrases, and reply delay range).

- **Proxy Support**  
  Users can configure proxy settings (socks5, socks4, or HTTP) to ensure proper connectivity in restricted network environments.

- **Optimized Logging**  
  The log output has been refined to record only events that match the monitoring rules, keeping the log file clean and focused on key events and errors.

## Features

- **Keyword Monitoring**  
  Monitor messages in specified conversations based on exact, partial, or regex matching.  
  Options include auto-forwarding, email notifications, and local file logging.  
  **New Reply Feature:** When a keyword is detected, the program waits for a user-defined random delay and then replies to the original message with one randomly chosen reply phrase from a pre-configured list.

- **File Extension Monitoring**  
  Automatically detects and processes messages containing files with specified extensions, with options for auto-forwarding and email notifications.

- **Full Monitoring & User Filtering**  
  Monitor all messages in specified channels or groups and filter by user ID, username, or nickname so that only relevant messages are processed.

- **Scheduled Messages**  
  Schedule message-sending tasks using Cron expressions, with support for random delay and post-send deletion.

- **Button and Image Processing**  
  When a message contains images with inline buttons, the image is uploaded to an AI model for recognition, and the corresponding button is clicked automatically based on the AI response.  
  If the initial AI call fails, the program retries once after 10 seconds; if it still fails, the local image file is immediately deleted.

- **Account Management**  
  Accounts are displayed and managed by a numeric sequence based on the order of addition (starting from 1).  
  The account list shows both the sequence number and the phone number, and switching accounts is as simple as entering the corresponding number.

- **Configuration Management**  
  - **Export All Configurations**:  
    Export all account configurations (including keyword, file extension, full monitoring, button monitoring, image listener, and scheduled tasks) into a single JSON file.  
  - **Selective Import**:  
    Import configurations based on account identifiers, with support for automatically filling in new reply-related fields if they are missing.

- **Proxy Support**  
  Enable proxy configuration to work around network restrictions.

- **Optimized Logging**  
  Only events that meet the monitoring criteria are logged in `telegram_monitor.log`, ensuring a focused and uncluttered log file.

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
 
4. Configure the SMTP email information if email notifications are required.

## Usage Instructions 
 
1. **Run the Program** 
Start the program with:

```bash
python monitor.py
```
 
2. **Login to Telegram** 
On the first run, you will be prompted to enter your `api_id`, `api_hash`, and your Telegram phone number along with the verification code.
If two-step verification is enabled, you will also need to enter your password.
 
3. **Configure Monitoring Parameters** 
After startup, the program enters an interactive command mode.
Use the available commands to add or modify monitoring rules for keywords, file extensions, full monitoring, button monitoring, scheduled tasks, and image listeners.
*Note:* In keyword monitoring configuration, you can enable the reply feature, set reply phrases, and configure the reply delay range. When a keyword is detected, the program will automatically reply to the original message in the same conversation.
 
4. **Manage Configurations**  
  - Use the `exportallconfig` command to export all account configurations into a single JSON file.
The exported file includes complete monitoring settings (including the new reply fields) keyed by phone number.
 
  - Use the `importallconfig` command to selectively import configurations based on the account identifiers in the configuration file.
During import, any missing reply-related fields will be automatically filled with default values.
 
5. **Account Management**  
  - The `listaccount` command displays all logged-in accounts with a numeric sequence and associated phone number.
 
  - To switch accounts, use the `switchaccount` command and enter the corresponding numeric sequence (e.g., entering `1` switches to the first account).
 
6. **Start Monitoring** 
After configuration, enter the `start` command to begin monitoring messages.

## Available Commands 
 
- **Account Management**  
  - `addaccount` : Add a new account
 
  - `removeaccount` : Remove an account
 
  - `listaccount` : List all accounts (displayed with numeric sequence)
 
  - `switchaccount` : Switch the current working account by entering its numeric sequence
 
- **Configuration Management**  
  - `exportallconfig` : Export configurations for all accounts into one file
 
  - `importallconfig` : Selectively import configurations based on account identifiers
 
  - `blockbot` / `unblockbot` : Block or unblock specified Telegram Bots
 
- **Monitoring Configuration**  
  - `addkeyword` / `modifykeyword` / `removekeyword` / `showkeywords` : Manage keyword monitoring
(Note: When adding or modifying keyword configurations, you can set options for auto-forwarding, email notifications, local logging, and the new reply feature.)
 
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
Supports multiple matching modes (exact, partial, regex).
In addition to auto-forwarding, email notifications, and logging, the **new reply feature**  allows the program to wait for a random delay (as configured) and then reply to the original message with one randomly chosen reply phrase from the configured list.
 
- **File Extension Monitoring** 
Automatically processes messages with specified file extensions, with options for auto-forwarding and email notifications.
 
- **Full Monitoring & User Filtering** 
Monitor all messages in selected channels or groups and filter by user ID, username, or nickname so that only relevant messages are processed.
 
- **Button Keyword Monitoring** 
Automatically clicks buttons containing specified keywords when messages with inline buttons are detected.
 
- **Image and AI Model Processing** 
Upload images from messages (that include buttons) to an AI model for analysis.
The program then automatically clicks the corresponding button based on the AI response.
If the first AI call fails, it retries once after 10 seconds; if it still fails, the local image file is deleted immediately.
 
- **Scheduled Messages** 
Set up scheduled message-sending tasks using Cron expressions, with options for random delay and post-send deletion.
 
- **Logging** 
All key events and errors are recorded in `telegram_monitor.log`.
Improved logging ensures that only events meeting the monitoring criteria are logged, keeping the log file concise and focused.

## Logging 
 
- **Log File** : `telegram_monitor.log`
This file records program status, error messages, and key events.
With the new updates, only matching events are logged—non-matching messages will not clutter the log file.

## Notes 

- Please comply with Telegram’s terms of service to avoid account restrictions.
 
- Securely store your `api_id`, `api_hash`, and session files to prevent account information leakage.

- Ensure SMTP settings and email authorization codes are configured correctly if email notifications are used.
 
- Configure the One/NEW API `api_key` and `api_base_url` properly for AI model calls.

## Common Issues 
 
1. **Cannot Connect to Telegram** 
Verify your network, proxy configurations, and API credentials.
 
2. **Email Sending Failed** 
Check your SMTP settings and email authorization code.
 
3. **AI Model Call Failed** 
The program will auto-retry once; if it still fails, processing is abandoned and the local image file is deleted.
 
4. **Scheduled Tasks Not Executing** 
Check your Cron expression, timezone settings, and ensure that the scheduler is running.

## Contribution and Support 

Contributions, suggestions, and improvements are welcome. Please submit issues or pull requests for bug fixes or feature enhancements.

## License 

This project is licensed under the MIT License.
