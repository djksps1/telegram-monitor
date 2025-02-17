# Telegram Message Monitoring Program

[中文](./README.md)

## Project Introduction

This project is a Telegram message monitoring program based on Python, using the [Telethon](https://github.com/LonamiWebs/Telethon) library to interact with the Telegram API.  
In the latest version, the program introduces and improves the following main features:

- **Message Monitoring**  
  The program can monitor messages in specified conversations, supporting keyword matching, regular expression matching, and file extension matching.  
  When a match is found, the program can automatically forward the message, send an email notification, or log the result to a local file.  
  Additionally, a **reply feature** has been added:  
  When a keyword is detected, the program can randomly select a reply from a set of pre-configured phrases and reply directly in the same conversation.  
  Users can also set a random delay before the reply (within a specified time range), making the reply feel more natural.
  
- **Document suffix monitoring**
  Automatically process messages with specific file extensions (e.g. `.pdf`, `.docx`, etc.), supporting automatic forwarding and email notification.
  A new user filtering feature has also been added, allowing messages to be filtered based on user ID, username or nickname.
  Added file saving function, can save to local specified folder, can specify the scope of the saved file

- **Full Monitoring and User Filtering**  
  The program can monitor all messages in specified channels, groups, or conversations and supports filtering based on user ID, username, or nickname.  
  It only processes messages that meet the conditions, avoiding irrelevant log outputs.  
  Furthermore, it supports saving matched messages to local files.

- **Scheduled Messages**  
  Users can configure scheduled message tasks using Cron expressions, with options for random delays and automatic message deletion after sending.  
  A new scheduled power on/off feature has been added, allowing the program to be turned on/off at specified times, also supporting Cron expressions.

- **Button and Image Handling**  
  For messages with Inline buttons and images, the program will automatically call an AI model to recognize the image content,  
  and based on the AI feedback, automatically select and click the corresponding button.  
  If the AI model call fails, the program will retry (up to once), and if it still fails, it will skip the processing and delete the local image.

- **Account Management (Numeric Serial Number Management)**  
  Account management has been optimized:  
  - The system assigns a numeric serial number to each account based on the order of addition (starting from 1, with earlier additions having smaller numbers).  
  - The account list will show both the serial number and the phone number;  
  - When switching accounts, users can simply input the corresponding serial number to switch, making the operation more intuitive.

- **Configuration Management**  
  - **One-click Export All Account Configurations**: Export the configuration information (including keywords, file extensions, full monitoring, button monitoring, image listening, and scheduled task configurations) of all logged-in accounts to a JSON file, with the account identifier (phone number) as the key.  
  - **Selective Import of Configurations**: Supports importing configurations for the currently logged-in accounts based on the account identifier in the exported file. The newly added reply feature configuration items (reply switch, reply phrases, reply delay range) will also be imported, and missing items will be automatically filled with default values.

- **Proxy Support**  
  Supports user-configured proxies (socks5, socks4, or HTTP) for connecting to Telegram in restricted network environments.

- **Log Recording**  
  The program records key events, error information, and the matching processing process in log files.  
  The improved log output only records actual matched and processed events, avoiding redundant logs, making the log content clearer.

- **New Feature: Run a Specified Number of Times**  
  All monitoring configurations now support specifying the number of runs. After the specified number of runs, the program will automatically delete the configuration.

## Environment Requirements

- Python 3.7 or higher  
- Dependencies: Telethon, openai, pytz, apscheduler, PySocks, smtplib, etc.  
- Telegram `api_id` and `api_hash` are required  
- SMTP email information (if email notifications are needed)  
- One/NEW API's `api_key` and `api_base_url` for AI model services (if image recognition is required)

## Installation Guide

1. Clone or download the project code:
   ```bash
   git clone https://github.com/djksps1/telegram-monitor.git
```
 
1. Install dependencies:


```bash
pip install -r requirements.txt
```
 
2. Obtain Telegram API credentials (`api_id` and `api_hash`).
 
3. Configure One/NEW API's `api_key` and `api_base_url` for AI model services.
 
4. Configure SMTP email information (if email notifications are needed).

## Usage Instructions 
 
1. **Run the Program** 
Start the program:

```bash
python monitor.py
```
 
2. **Login to Telegram** 
When running the program for the first time, it will prompt you to enter `api_id`, `api_hash`, phone number, and verification code (if two-step verification is enabled, a password is also required).
 
3. **Configure Monitoring Parameters** 
After the program starts, it enters an interactive command mode where users can add or modify various monitoring configurations (including keyword monitoring, file extension monitoring, full monitoring, button monitoring, scheduled tasks, and image listening).
Note: In the keyword configuration, you can enable the reply feature, configure reply phrases, and set the reply delay range. The program will automatically reply with a random reply in the same conversation when the keyword is detected.
 
4. **Configuration Management**  
  - Use the `exportallconfig` command to export all account configurations, generating a JSON file that includes the full monitoring parameters (including the new reply feature configurations).
 
  - Use the `importallconfig` command to import configurations based on the account identifier (phone number) in the exported file, and it will automatically fill in the missing reply feature fields (such as `reply_enabled`, `reply_texts`, `reply_delay_min`, `reply_delay_max`).
 
5. **Account Management**  
  - In the `listaccount` command, all logged-in accounts will be displayed with numeric serial numbers and corresponding phone numbers;
 
  - When switching accounts, simply input the displayed numeric serial number (e.g., input `1` to switch to the first added account).
 
6. **Start Monitoring** 
After configuration, enter the `start` command to begin monitoring messages.

## Available Commands List 
 
- **Account Management**  
  - `addaccount`: Add a new account
 
  - `removeaccount`: Remove an account
 
  - `listaccount`: List all accounts (displayed by numeric serial number)
 
  - `switchaccount`: Switch to the current working account by entering the numeric serial number
 
- **Configuration Management**  
  - `exportallconfig`: Export all account configurations
 
  - `importallconfig`: Selectively import configurations (supports automatic filling of new fields)
 
  - `blockbot` / `unblockbot`: Block or unblock a specified Telegram Bot
 
- **Monitoring Configuration Management**  
  - `addkeyword` / `modifykeyword` / `removekeyword` / `showkeywords`: Manage keyword monitoring
 
  - `addext` / `modifyext` / `removeext` / `showext`: Manage file extension monitoring (supports user filtering)
 
  - `addall` / `modifyall` / `removeall` / `showall`: Manage full monitoring configurations (supports saving messages to local files)
 
  - `addbutton` / `modifybutton` / `removebutton` / `showbuttons`: Manage button keyword monitoring
 
  - `addimagelistener` / `removeimagelistener` / `showimagelistener`: Manage image + button listening conversation IDs
 
- **Scheduled Task Management**  
  - `schedule` / `modifyschedule` / `removeschedule` / `showschedule`: Manage scheduled message tasks (supports random delays and automatic deletion)
 
- **Monitoring Control**  
  - `start` / `stop`: Start or stop monitoring
 
  - `exit`: Exit the program


## Notes 

- Please comply with Telegram's terms of use to avoid account limitations due to improper use of monitoring features.
 
- Safeguard your `api_id`, `api_hash`, and session files to prevent account information leakage.

- If you require email notifications, please configure the SMTP information and authorization code correctly.
 
- Configure One/NEW API's `api_key` and `api_base_url` to use AI model services for image recognition.
 
- When blocking or monitoring a specific channel or bot in a group chat, input the channel ID without the leading "-100", for example, if the channel ID is `-1001234567`, enter `1234567`. For bots, input the `bot_id`. When monitoring channels, enter the channel ID normally.

## Frequently Asked Questions 
 
1. **Unable to connect to Telegram** 
Check the network, proxy configuration, and API credentials.
 
2. **Email sending failure** 
Ensure that the SMTP configuration is correct and the correct email authorization code is set.
 
3. **AI model call failure** 
The program will retry once, and if it fails again, it will skip the processing and delete the local image.
 
4. **Scheduled task not executing** 
Check the Cron expression, time zone settings, and ensure the scheduler is running.

## Contributions and Support 

We welcome suggestions and improvements. If you have any questions or wish to request new features, please submit an Issue or Pull Request.

## License 

This project is licensed under the MIT License.
