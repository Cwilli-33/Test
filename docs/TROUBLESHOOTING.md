# Troubleshooting Guide

Common issues and how to fix them.

---

## Quick Health Check

Before diving into specific issues, verify the basics:

1. **Is the app running?** Visit `https://your-app.up.railway.app/health`
   - Should return: `{"status": "healthy"}`
   - If it doesn't load, the app is down — check Railway deployment logs

2. **Is the webhook connected?** Visit:
   ```
   https://api.telegram.org/bot{YOUR_BOT_TOKEN}/getWebhookInfo
   ```
   - `url` should show your Railway URL + `/webhook/telegram`
   - `pending_update_count` should be `0` (or a small number)
   - If there are errors listed, check the `last_error_message` field

---

## Images Sent but Nothing Happens in GHL

### The bot isn't receiving messages

**Symptoms:** No new contacts appear in GHL. No errors in Railway logs.

**Check:**
1. Is the bot an **admin** in your Telegram group? (Required to see messages)
2. Did you register the webhook? Try re-registering:
   ```
   https://api.telegram.org/bot{TOKEN}/setWebhook?url=https://{YOUR_URL}/webhook/telegram&secret_token={YOUR_SECRET}
   ```
3. Check webhook status:
   ```
   https://api.telegram.org/bot{TOKEN}/getWebhookInfo
   ```
   Look for `last_error_message` — it will tell you what's wrong.

### The bot sees the message but extraction fails

**Symptoms:** Railway logs show the webhook is received but you see errors.

**Check Railway logs:**
1. Go to your Railway project
2. Click on the service
3. Click **Deployments** > latest deployment > **View Logs**
4. Look for `[PIPELINE]` entries and `ERROR` messages

**Common log entries:**
- `IGNORED: no photo or image document in message` — You sent a text message, not a photo
- `SKIPPED: duplicate fingerprint` — This image was already processed
- `SKIPPED: low confidence` — Claude couldn't read the image well enough
- `ERROR: Claude extraction failed` — Claude API issue (check your API key and credits)

### The image is processed but GHL contact is wrong

**Symptoms:** Contact is created but data is in the wrong fields or missing.

**Check:**
1. Are your custom field IDs correct in `src/data_merger.py`? Each field ID must match your GHL location exactly
2. Did you create all 32 custom fields? Missing fields will cause data to be silently dropped
3. Check the Source Documents field — is it created as **File Upload** type?

---

## Error: 403 Forbidden on Webhook

**Cause:** The webhook secret doesn't match.

**Fix:**
1. Check the `WEBHOOK_SECRET` environment variable in Railway
2. Re-register the webhook with the same secret:
   ```
   https://api.telegram.org/bot{TOKEN}/setWebhook?url=https://{YOUR_URL}/webhook/telegram&secret_token={SAME_SECRET_AS_ENV_VAR}
   ```
3. The `secret_token` in the webhook URL must **exactly match** the `WEBHOOK_SECRET` in your Railway environment variables

---

## Error: Claude API Key Invalid

**Symptoms:** Railway logs show `401 Unauthorized` or `authentication_error` from Claude.

**Fix:**
1. Verify your `CLAUDE_API_KEY` environment variable starts with `sk-ant-api03-`
2. Check your Anthropic account has credits: [console.anthropic.com](https://console.anthropic.com)
3. Make sure the key hasn't been revoked — generate a new one if needed
4. Restart the Railway deployment after updating the variable

---

## Error: GHL API Errors

### 401 Unauthorized

**Cause:** GHL API key is invalid or expired.

**Fix:**
1. Verify `GHL_API_KEY` starts with `pit-` (Private Integration Token)
2. Check that the Private Integration is still active in your GHL settings
3. Verify the integration has the required scopes: `contacts.readonly`, `contacts.write`, `locations.readonly`, `forms.write`

### 422 Unprocessable Entity

**Cause:** Data format issue — usually a phone number or email in the wrong format.

**What to do:** This is usually harmless. The contact will still be created, but the specific field that caused the error will be skipped. Check Railway logs for the specific field.

### 429 Too Many Requests

**Cause:** You're hitting GHL's rate limit.

**What to do:** The pipeline has built-in retry logic with exponential backoff. It will automatically retry up to 3 times. If you're processing a very high volume of images quickly, the retries should handle it.

---

## Duplicate Contacts in GHL

**Symptoms:** The same lead appears multiple times in GHL.

**Possible causes:**
1. **Different images, same lead** — The pipeline matches by EIN, phone, email, and business name. If none of these match between two images, it creates separate contacts
2. **Matching data not visible** — If the extracted phone/email doesn't match what's already in GHL (different formatting, different number), a new contact is created

**How the matching works (in priority order):**
1. EIN match (most reliable)
2. Phone number match
3. Email match
4. Business name + state match (fuzzy)
5. Chat ID match (same Telegram chat = same lead)

**To reduce duplicates:** Send multiple documents for the same lead in sequence. The pipeline uses "batch dedup" — documents sent close together from the same chat are assumed to be the same lead.

---

## Source Documents Not Uploading

**Symptoms:** Contact is created/updated but no files appear in the Source Documents field.

**Check:**
1. Is the Source Documents custom field created as **File Upload** type (not Single Line or Text)?
2. Is the field ID correct in `src/main.py` (line ~266)?
3. Check Railway logs for `IMAGE_UPLOAD_FAILED` entries
4. Verify your GHL Private Integration has the `forms.write` scope

---

## Railway Deployment Issues

### App keeps restarting

**Check:**
1. Railway logs for crash errors
2. All required environment variables are set (TELEGRAM_BOT_TOKEN, CLAUDE_API_KEY, GHL_API_KEY, GHL_LOCATION_ID)
3. If any are missing, the app may crash on startup

### App is slow / timing out

The health check at `/health` must respond within 30 seconds. If the app is slow to start, Railway may kill it.

**Typical startup time:** 5-10 seconds. If it takes longer, check the logs for database initialization issues.

### Deployment fails to build

**Common causes:**
1. `requirements.txt` has a package that can't be installed — check the build logs
2. Dockerfile syntax error — should be unlikely if you haven't modified it

---

## Debug Endpoint

The pipeline has a built-in debug endpoint that shows the last 20 webhook events:

```
GET https://your-app.up.railway.app/admin/debug
Header: X-Api-Key: {YOUR_ADMIN_API_KEY}
```

This returns a JSON log of every webhook received, including all processing steps, errors, and outcomes.

**If you didn't set `ADMIN_API_KEY`:** The app auto-generates one on each startup and prints it in the Railway logs. Look for:
```
Auto-generated ADMIN_API_KEY (set env var to persist): xxxxxxxxxx
```

---

## Cleanup Stale Records

If the pipeline crashed mid-processing, it may leave "PROCESSING" placeholder records that block the same image from being retried. To clean these up:

```
POST https://your-app.up.railway.app/admin/cleanup-fingerprints
Header: X-Api-Key: {YOUR_ADMIN_API_KEY}
```

This removes:
- Old fingerprint records (based on TTL setting)
- Stale "PROCESSING" records older than 10 minutes

---

## Getting Help

If you're stuck:

1. **Check Railway logs** — they contain detailed step-by-step logging for every image processed
2. **Use the debug endpoint** — `/admin/debug` shows the last 20 events with full error details
3. **Test with a simple image** — try a clear, well-lit photo of a document with a visible business name
4. **Verify one piece at a time:**
   - Health endpoint works? (`/health`)
   - Webhook registered? (`getWebhookInfo`)
   - Bot is admin in group?
   - API keys are correct?
   - Custom fields are created?
