# noti-bot

# List of Services

GitHub + [Railway](https://railway.com/)
- Hours: **500 hours/month**
- Always-On : ✅ **Yes** (until exhausted)	
- Credit Card Needed: ❌ **No**

[Repl.it](https://replit.com/) 
- For testing purpose only
- Hours: **Limited**
- Always-On : ❌ **No**	
- Credit Card Needed: ❌ **No**

[Fly.io](https://fly.io/)
- Credit card required
- Hours: **Unknown**
- Always-On : ✅ **Yes** (with Repl Boosts)
- Credit Card Needed: ✅ **Yes**

[PythonAnywhere](https://www.pythonanywhere.com/)

[Heroku](https://www.heroku.com/)
- offers free hosting Hours: **500 hours/month**
- Always-On : ❌ **No**	
- Credit Card Needed: ✅ **Yes**

[Glitch](https://glitch.com/)

[Google Cloud Run](https://cloud.google.com/) 
- free container hosting with 1 GB RAM & 50 hours/month per region.

[Oracle Cloud](https://www.oracle.com/cloud/)

[AWS](https://aws.amazon.com/)
- Pros: 750 hours/month for 12 months


# Steps to Create a Fine-Grained GitHub Token:

1.    Go to GitHub → Settings → Developer settings → Personal access tokens.
2.    Select Fine-grained tokens.
3.    Click "Generate new token".
4.    Repository Access → Choose your bot’s repository.
5.    ✅ Recommended Expiration: "No expiration"

    This prevents your token from expiring unexpectedly, which could cause the bot to fail when trying to redeploy.
    If you choose a set expiration (e.g., 30 days), you'll need to manually regenerate it before it expires.

Alternative: Set a long expiration (Optional)

If security is a concern, you can set the expiration to **90 days** or more, but remember to renew it before it expires.

6.    Permissions:
        Actions: Read and Write
        Contents: Read and Write

7.    Expiration: Choose "No Expiration" (or set a long duration like 90 days).

8.    Click "Generate token" and copy it immediately.

9.    Store it as **GITHUB_TOKEN** in Railway and GitHub secrets.



# How to Get RAILWAY_SERVICE_ID

Follow these steps to retrieve your **RAILWAY_SERVICE_ID**:

1.    Open your Railway Dashboard.
2.    Navigate to your Project.
3.    Click on the Service you want to get the ID for.
4.    Look at the URL in your browser. It should be in this format:

```https://railway.app/project/{PROJECT_ID}/service/{SERVICE_ID}?environmentId={ENVIRONMENT_ID}```

Copy the **SERVICE_ID** from the URL and use it as **RAILWAY_SERVICE_ID** in your secrets.


# Secrets to Add in Railway

Add these secrets in Railway → Project → Variables:

```
Secret Name	            Value Example

TELEGRAM_BOT_TOKEN	    your-telegram-bot-token

URL	                    https://your-webpage.com

CHAT_ID	                your-telegram-chat-id

CHECK_INTERVAL	        5 (default check interval in seconds)

GITHUB_REPO	            your-username/repo-name

GITHUB_TOKEN	        (Fine-grained token from GitHub)
```

Secrets to Add in GitHub

Go to GitHub → Your Repository → Settings → Secrets and Variables → Actions and add:

```
RAILWAY_SERVICE_ID	    (Your Service ID from Railway URL)
RAILWAY_API_KEY	        (Railway API Key from Railway Dashboard → Settings → API Keys)
```

# Secrets to Add in Replit

Add these secrets in Replit → Project → Variables:

```
Secret Name	            Value Example
TELEGRAM_BOT_TOKEN	    your-telegram-bot-token
URL	                    https://your-webpage.com
CHAT_ID	                your-telegram-chat-id
```