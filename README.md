# Advance-Tele-Auto-Message 🚀
An advanced, highly resilient Telegram automation bot built with Python and Telethon. Designed for production environments and CI/CD pipelines (GitHub Actions), this bot automates sending scheduled, repeating messages to multiple Telegram groups across multiple accounts simultaneously.
## ✨ Features
 * **Multi-Account & Multi-Group:** Run operations across multiple Telegram sessions and target multiple chat IDs concurrently.
 * **JSON-Driven Configuration:** Easily control intervals, loop limits (finite or infinite), group targets, and distinct account messages via clean JSON profiles.
 * **Production-Ready Resilience:** Automatic reconnection, exponential backoff for network drops, and graceful handling of Telegram's FloodWaitError and RPCError.
 * **Beautiful Rich UI:** Real-time terminal dashboards with progress bars, success rates, and colored logging using the rich library.
 * **Serverless Deployment:** Fully configured to run 24/7 on GitHub Actions with external triggers (e.g., cron-job.org) to bypass internal GitHub schedule limitations.
 * **Zero-Leak Security:** Designed to keep .session files and API credentials strictly in GitHub Secrets.
## 🛠️ Prerequisites
 * Python 3.10+
 * Telegram API ID and API Hash (from my.telegram.org)
 * Generated .session files (SQLite format) via Telethon.
## 📦 Installation & Local Setup
 1. **Clone the repository:**
   ```bash
   git clone https://github.com/YourUsername/Advance-Tele-Auto-Message.git
   cd Advance-Tele-Auto-Message
   
   ```
 2. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   
   ```
   *(Required packages: telethon==1.44.0, rich==13.7.1, pytz==2024.1)*
 3. **Secure your sessions:**
   Ensure your .gitignore includes Session/ and *.session so you do not accidentally commit your private Telegram sessions to the public repository.
## ⚙️ JSON Configuration Guide
Create a JSON file (e.g., visitTejaBot.json) in the root directory to define your execution logic.
```json
{
  "repeat_count": 10,
  "interval_seconds": 15,
  "infinite_loop": false,
  "group_ids": [
    -1003244562411
  ],
  "accounts": [
    {
      "name": "Amanvisit",
      "session": "amanvisit",
      "message": "/visit IND 9692973675"
    }
  ]
}

```
 * **repeat_count**: Number of times to loop through the groups.
 * **interval_seconds**: Delay between complete cycles.
 * **infinite_loop**: Set to true to run forever (ignores repeat_count).
 * **group_ids**: Array of target Telegram chat IDs.
 * **accounts**: Array of account objects containing the display name, the .session filename (without extension), and the specific message to send.
## ☁️ GitHub Actions Deployment
This bot is configured to run on GitHub Actions to provide free, unlimited execution minutes (on public repos) while keeping your sessions private.
### 1. Prepare Your Session Files
Compress all your required .session files into a single .tar.gz archive, then encode it in Base64:
```bash
# Inside your project folder
tar -czf all_sessions.tar.gz Session/
base64 all_sessions.tar.gz

```
*Copy the massive text block output.*
### 2. Configure GitHub Secrets
Go to your Repository **Settings** > **Secrets and variables** > **Actions** > **New repository secret**. Add the following:
 * TELEGRAM_API_ID : Your API ID integer.
 * TELEGRAM_API_HASH : Your API Hash string.
 * ALL_SESSIONS_BASE64 : The Base64 text block copied from the previous step.
## ⏱️ External Trigger Setup (cron-job.org)
To bypass GitHub's unreliable internal cron scheduler, use an external service like cron-job.org to trigger the workflow directly via the GitHub API.
### 1. Get a GitHub Token
 * Go to GitHub **Settings** > **Developer settings** > **Personal access tokens (classic)**.
 * Generate a new token with **No expiration** and the **workflow** scope. Copy this token.
### 2. Create the External Cron Job
In cron-job.org, create a new job pointing to your repository's dispatch URL:
 * **URL:** [https://api.github.com/repos/YourUsername/Advance-Tele-Auto-Message/actions/workflows/telegram_bot.yml/dispatches](https://api.github.com/repos/YourUsername/Advance-Tele-Auto-Message/actions/workflows/telegram_bot.yml/dispatches)
 * **Method:** POST
**Headers Required:**
 1. Accept: application/vnd.github.v3+json
 2. Authorization: Bearer ghp_YourGeneratedTokenHere
**Request Body (Raw JSON):**
```json
{
  "ref": "main",
  "inputs": {
    "time_slot": "visitTejaBot"
  }
}

```
*(Change time_slot to match the name of the JSON configuration file you want to run, without the .json extension).*
