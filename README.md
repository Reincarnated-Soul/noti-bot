# noti-bot
```
├── bot/
│   ├── __init__.py
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

    pip install aiogram aiohttp bs4 lxml python-dotenv

# List of Services

[Railway](https://railway.com/)
- Hours: **500 hours/month**
- Always-On : ✅ **Yes** (until exhausted)	
- Credit Card Needed: ❌ **No**

[Replit](https://replit.com/) 
- For testing purpose only
- Hours: **Limited**
- Always-On : ❌ **No**	
- Credit Card Needed: ❌ **No**

[Fly.io](https://fly.io/)
- Hours: **Unknown**
- Always-On : ✅ **Yes** (with Repl Boosts)
- Credit Card Needed: ✅ **Yes**

[PythonAnywhere](https://www.pythonanywhere.com/)

[Heroku](https://www.heroku.com/)
- offers free hosting Hours: **500 hours/month**
- Always-On : ❌ **No**	
- Credit Card Needed: ✅ **Yes**

[Google Cloud Run](https://cloud.google.com/) 
- free container hosting with 1 GB RAM & 50 hours/month per region.

[Oracle Cloud](https://www.oracle.com/cloud/)

[AWS](https://aws.amazon.com/)
- Pros: 750 hours/month for 12 months


<br><br>

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