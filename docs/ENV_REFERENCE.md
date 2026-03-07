# Environment Variables Reference

All configuration is done through environment variables. Set these in Railway (or in a `.env` file for local development).

---

## Required Variables

These must be set or the application will not work.

| Variable | Description | Example | Where to Get It |
|----------|-------------|---------|----------------|
| `TELEGRAM_BOT_TOKEN` | Your Telegram bot's API token | `1234567890:ABCdefGHI...` | @BotFather on Telegram |
| `CLAUDE_API_KEY` | Anthropic API key for Claude Vision | `sk-ant-api03-xxxxx...` | [console.anthropic.com](https://console.anthropic.com) |
| `GHL_API_KEY` | GoHighLevel Private Integration key | `pit-xxxxxxxx-xxxx-...` | GHL Settings > Integrations > Private Integrations |
| `GHL_LOCATION_ID` | Your GHL location identifier | `xUrzKPGPYMeo1BSR9a0P` | GHL Settings > Business Profile (or from the URL) |
| `WEBHOOK_SECRET` | Secret token to authenticate Telegram webhooks | Any random string | You create this yourself |

---

## Optional Variables

These have sensible defaults. Only change them if you need to.

### Security

| Variable | Default | Description |
|----------|---------|-------------|
| `ADMIN_API_KEY` | Auto-generated each boot | API key for admin endpoints (`/admin/debug`, `/admin/cleanup-fingerprints`). Set this to a fixed value so it persists across restarts. |

### Claude AI Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `CLAUDE_MODEL` | `claude-sonnet-4-20250514` | Which Claude model to use. Sonnet is recommended for cost/quality balance. |
| `CLAUDE_MAX_TOKENS` | `4000` | Maximum response length from Claude. 4000 is sufficient for all extractions. |
| `CLAUDE_TIMEOUT` | `60` | Seconds to wait for Claude to respond before timing out. |

### Processing Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `MIN_CONFIDENCE_THRESHOLD` | `0.25` | Minimum AI confidence score (0.0-1.0) to accept an extraction. Images below this threshold are skipped. Lower = accept more (potentially noisy) results. Higher = stricter quality. |
| `IMAGE_FINGERPRINT_TTL_HOURS` | `24` | How many hours to remember processed images for deduplication. After this time, the same image can be processed again. |
| `EXTRACTION_CACHE_TTL_DAYS` | `7` | How many days to keep extraction records in the local database. |

### Application Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_LEVEL` | `INFO` | Logging verbosity. Options: `DEBUG`, `INFO`, `WARNING`, `ERROR`. Use `DEBUG` when troubleshooting, `INFO` for normal operation. |
| `ENV` | `development` | Environment label. Set to `production` in Railway. |
| `DEBUG` | `false` | Enable debug mode. |

### Database

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///./telegram_ghl.db` | Database connection string. SQLite works out of the box. For production with persistent storage, use PostgreSQL: `postgresql://user:pass@host:5432/dbname` |

### Optional Services

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | Not set | Redis connection URL for caching. Not required — the pipeline works fine without Redis. |
| `SENTRY_DSN` | Not set | Sentry error tracking DSN. Optional monitoring integration. |

---

## Setting Variables in Railway

1. Go to your Railway project
2. Click on your service
3. Go to the **Variables** tab
4. Click **+ New Variable** for each one
5. Railway automatically restarts the app when you save

---

## Setting Variables Locally

For local development, copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

Then edit `.env` with your favorite text editor. The application reads this file automatically on startup.

> **Never commit the `.env` file to git.** It's already in `.gitignore` to prevent this.
