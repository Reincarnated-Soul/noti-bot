# noti-bot
```
├── bot/
│   ├── __init__.py
│   ├── api.py             # Handle API calls
│   ├── config.py          # Configuration loading
│   ├── handlers.py        # Bot command handlers
│   ├── monitoring.py      # Website monitoring logic
│   ├── notifications.py   # Notification sending logic
│   ├── storage.py         # Data storage operations
│   └── utils.py           # Helper functions
├── main.py                # Entry point (simplified)
```

| Secret Name        | Value Example                | Description                                  |
|--------------------|------------------------------|----------------------------------------------|
| TELEGRAM_BOT_TOKEN | your-telegram-bot-token      | Your Telegram bot's API token                |
| URL                | https://your-webpage.com <br> or <br> ["https://your-webpage.com", "https://your-webpage.com"]| The base URL for your website. <br> For Multiple Site Monitoring pass the URL as an array with single or double quotes               |
| CHAT_ID            | your-telegram-chat-id        | Your Telegram chat ID for notifications      |

<br>

    pip install aiogram aiohttp bs4 lxml python-dotenv
<br>

## Hosting Options Comparison

| Platform | Free Hours/Month | Always-On | Credit Card Required | Additional Notes |
|----------|-----------------|-----------|---------------------|------------------|
| Railway | 500 | ✅ Yes* | ❌ No | *Until hours are exhausted |
| Replit | Limited | ❌ No | ❌ No | Good for testing purpose only |
| Fly.io | Unknown | ✅ Yes | ✅ Yes | Requires Repl Boosts |
| Heroku | 500 | ❌ No | ✅ Yes | - |
| Google Cloud Run | - | - | - | 1 GB RAM included |
| AWS | 750 | - | ✅ Yes | Free for 12 months only |
| PythonAnywhere | - | - | - | - |
| Oracle Cloud | - | - | - | - |
| CodeSpace | - | - | - | - |

> Note: "-" indicates information not provided in original documentation

### Key Features to Consider:
- **Hours/Month**: Amount of free compute time
- **Always-On**: Whether the service keeps running continuously
- **Credit Card**: Whether a credit card is required for registration
- **Additional Notes**: Special conditions or limitations

<br>

<!-- # Platform specific Secrets -->


# Commands for Manual Deployment
```
pip install -r requirements.txt
```

- These will download all the deplendencies required for the project to get it `LIVE`

```
python main.py
```
- To Run


## For Firebase Studio
Run the following commands in the terminal

STEP 1:
```
curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py
```
STEP 2:
```
python3 -m venv .venv
```
STEP 3:
```
source .venv/bin/activate
```
STEP 4:
```
pip install -r requirements.txt
```

or merge the `STEP 3` and `STEP 4`
```
source .venv/bin/activate && pip install -r requirements.txt
```

or combine the `STEP 2`, `STEP 3` and `STEP 4`
```
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
```