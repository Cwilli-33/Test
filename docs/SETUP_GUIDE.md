# Setup Guide

This guide walks you through everything you need to get the Telegram Lead Capture Pipeline running for your business. No coding experience required.

**Time required:** About 30-45 minutes

---

## Overview: What You Need

| Service | What It's For | Cost | What You'll Get From It |
|---------|--------------|------|------------------------|
| **Telegram** | Receives the lead images | Free | Bot Token |
| **Anthropic (Claude)** | AI that reads the images | ~$0.01-0.03/image | API Key |
| **GoHighLevel** | Your CRM where leads are stored | Your existing subscription | API Key + Location ID |
| **Railway.app** | Hosts the application 24/7 | Free tier or ~$5/month | Public URL |

---

## Step 1: Create Your Telegram Bot

The bot is how Telegram forwards images to your pipeline.

1. Open Telegram and search for **@BotFather**
2. Send `/newbot`
3. Choose a name for your bot (e.g., "MCA Lead Bot")
4. Choose a username (must end in "bot", e.g., `mca_leads_bot`)
5. BotFather will reply with your **Bot Token** — it looks like this:
   ```
   1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
   ```
6. **Save this token** — you'll need it in Step 5

### Add the Bot to Your Telegram Group

1. Create a Telegram group (or use an existing one) where you'll send lead images
2. Add your new bot to the group
3. Make the bot an **admin** of the group (this is required so it can see messages)
4. Send a test message in the group to confirm the bot is there

> **Tip:** You can also send images directly to the bot in a private chat — both work.

---

## Step 2: Get Your Claude API Key

Claude is the AI that reads your lead images and extracts the data.

1. Go to [console.anthropic.com](https://console.anthropic.com)
2. Create an account (or sign in)
3. Go to **API Keys** in the left sidebar
4. Click **Create Key**
5. Name it something like "MCA Pipeline"
6. Copy the key — it looks like this:
   ```
   sk-ant-api03-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```
7. **Save this key** — you'll need it in Step 5

### Add Credits

1. In the Anthropic console, go to **Plans & Billing**
2. Add a payment method
3. Add at least $5 in credits to start (this will process ~200-500 images)

> **Cost:** Each image costs roughly $0.01-0.03 to process, depending on image size and complexity. Processing 100 leads per day costs about $1-3/day.

---

## Step 3: Get Your GHL API Key and Location ID

You need a Private Integration API key from GoHighLevel.

### Create a Private Integration

1. Log into your GHL account
2. Go to **Settings** > **Integrations** > **Private Integrations** (or navigate to the Marketplace > Private Integrations)
3. Click **Create Private Integration** (or **+ Create App**)
4. Name it "Telegram Lead Pipeline"
5. Under **Scopes**, enable:
   - `contacts.readonly`
   - `contacts.write`
   - `locations.readonly`
   - `forms.write` (needed for file uploads)
6. Click **Save** and then copy the **API Key** — it starts with `pit-`:
   ```
   pit-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
   ```
7. **Save this key** — you'll need it in Step 5

### Find Your Location ID

1. In GHL, go to **Settings** > **Business Profile** (or **Company**)
2. Look at the URL in your browser — it contains your Location ID:
   ```
   https://app.gohighlevel.com/v2/location/xUrzKPGPYMeo1BSR9a0P/settings
                                              ^^^^^^^^^^^^^^^^^^^^
                                              This is your Location ID
   ```
3. Alternatively, go to **Settings** > **Business Info** and find the Location ID field
4. **Save this ID** — you'll need it in Step 5

### Create Custom Fields in GHL

Before the pipeline can store extracted data, you need to create custom fields in your GHL location. See the **[GHL Custom Fields Guide](GHL_CUSTOM_FIELDS.md)** for the exact list of fields to create.

> **Important:** The custom field IDs in your GHL location will be different from the ones in the code. After creating the fields, you'll need to update the field ID mapping in the code. See the Custom Fields guide for instructions.

---

## Step 4: Deploy to Railway

Railway hosts your application so it runs 24/7.

### Create Your Railway Account

1. Go to [railway.app](https://railway.app)
2. Sign up with your GitHub account (recommended) or email
3. You get $5 free credit per month on the free tier

### Deploy the Application

**Option A: Deploy from GitHub (Recommended)**

1. Fork or upload this repository to your own GitHub account
2. In Railway, click **New Project** > **Deploy from GitHub repo**
3. Select your repository
4. Railway will automatically detect the Dockerfile and start building

**Option B: Deploy with Railway CLI**

1. Install the Railway CLI: `npm install -g @railway/cli`
2. Navigate to this project folder
3. Run:
   ```bash
   railway login
   railway init
   railway up
   ```

### Configure Environment Variables

1. In your Railway project, click on your service
2. Go to the **Variables** tab
3. Add these variables one at a time:

| Variable | Value | Required? |
|----------|-------|-----------|
| `TELEGRAM_BOT_TOKEN` | Your bot token from Step 1 | Yes |
| `CLAUDE_API_KEY` | Your Claude API key from Step 2 | Yes |
| `GHL_API_KEY` | Your GHL Private Integration key from Step 3 | Yes |
| `GHL_LOCATION_ID` | Your GHL Location ID from Step 3 | Yes |
| `WEBHOOK_SECRET` | Any random string (see below) | Yes |
| `LOG_LEVEL` | `INFO` | No (defaults to INFO) |
| `ADMIN_API_KEY` | Any random string for admin access | No (auto-generated) |
| `MIN_CONFIDENCE_THRESHOLD` | `0.25` | No (defaults to 0.25) |

**To generate a random WEBHOOK_SECRET:** Use any password generator, or type random characters. Example: `my-super-secret-webhook-key-2024`

4. Railway will automatically redeploy with your new variables

### Get Your Public URL

1. In Railway, click on your service
2. Go to **Settings** > **Networking**
3. Click **Generate Domain** to get a public URL like:
   ```
   your-app-name.up.railway.app
   ```
4. **Save this URL** — you need it for Step 5

---

## Step 5: Connect Telegram to Your Pipeline

This is the final step — telling Telegram to send messages to your application.

### Register the Webhook

Open your web browser and paste this URL (replacing the placeholders):

```
https://api.telegram.org/bot{YOUR_BOT_TOKEN}/setWebhook?url=https://{YOUR_RAILWAY_URL}/webhook/telegram&secret_token={YOUR_WEBHOOK_SECRET}
```

**Example:**
```
https://api.telegram.org/bot1234567890:ABCdefGHI/setWebhook?url=https://my-app.up.railway.app/webhook/telegram&secret_token=my-super-secret-webhook-key-2024
```

You should see a response like:
```json
{"ok": true, "result": true, "description": "Webhook was set"}
```

### Verify It's Working

1. Open your browser and go to:
   ```
   https://api.telegram.org/bot{YOUR_BOT_TOKEN}/getWebhookInfo
   ```
2. You should see your URL listed and `"pending_update_count": 0`

---

## Step 6: Test It!

1. Send a photo of an MCA application (or any lead document) to your Telegram group
2. Wait 10-30 seconds
3. Check your GHL CRM — a new contact should appear with the extracted data
4. Send the same image again — it should be skipped as a duplicate

### Verify the Pipeline is Running

Visit your Railway URL in a browser:
```
https://your-app.up.railway.app/health
```

You should see:
```json
{"status": "healthy", "database": "connected", "message": "Ready to process images"}
```

---

## You're Done!

Your pipeline is now running. Every time someone sends a lead image to your Telegram group, the data will automatically appear in your GHL CRM.

### What to Do Next

- **Send more images** — the pipeline handles multiple images for the same lead, merging data intelligently
- **Check the debug log** — visit `https://your-app.up.railway.app/admin/debug` (requires your ADMIN_API_KEY in the `X-Api-Key` header)
- **Monitor costs** — check your Anthropic dashboard for API usage
- **Read the [Troubleshooting Guide](TROUBLESHOOTING.md)** if anything isn't working

---

## Updating the Application

When you receive code updates:

1. Push the new code to your GitHub repository
2. Railway will automatically detect the change and redeploy
3. No need to re-register the webhook or change any settings

If deploying manually:
```bash
railway up
```

---

## Monthly Costs Estimate

| Service | Usage | Estimated Cost |
|---------|-------|---------------|
| Railway | Hosting 24/7 | $0-5/month |
| Anthropic Claude | 100 images/day | $30-90/month |
| Telegram | Unlimited | Free |
| GHL | Your existing plan | No additional cost |

> **Total estimated cost:** $30-95/month for moderate usage (100 leads/day)
