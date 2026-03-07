# Telegram Lead Capture Pipeline

Automatically extract MCA (Merchant Cash Advance) lead data from images sent to a Telegram group and push it into GoHighLevel CRM — no manual data entry required.

## What It Does

1. **You send a photo** of an MCA application, bank statement, credit report, or any lead document to your Telegram group
2. **AI reads the image** using Claude Vision and extracts all business info, owner details, financials, credit scores, and MCA history
3. **Smart matching** finds whether the lead already exists in your GHL CRM (by EIN, phone, email, or business name)
4. **Creates or updates** the GHL contact with all extracted data across 30+ custom fields
5. **Attaches the source document** to the contact's file upload field for reference

No duplicates. No manual typing. Works with blurry photos, screenshots, PDFs-as-images — anything Claude Vision can read.

## What Gets Extracted

| Category | Fields |
|----------|--------|
| **Business** | Legal name, DBA, EIN, address, phone, email, website, industry, entity type, start date, state of incorporation |
| **Owner** | First/last name, phone, email, SSN last 4, DOB, ownership %, title, home address |
| **Owner 2** | Full name, phone, ownership %, FICO |
| **Financials** | Monthly revenue, annual revenue, funding requested, avg daily balance, 3-month true revenue |
| **Credit** | FICO score (owner 1 & 2), tradelines, delinquencies, charge-offs, leverage % |
| **MCA History** | Existing positions, number of positions, current funder, daily payment, remaining balance |
| **Statement Numbers** | Masked account/statement identifiers (accumulated across multiple documents) |
| **ISO/Source** | ISO name, source platform |

## How It Works

```
Telegram Group
      |
      v
  [Webhook]  -->  Fingerprint check (skip duplicates)
      |
      v
  Download image from Telegram
      |
      v
  Claude Vision AI extracts structured data
      |
      v
  Search GHL for existing contact (EIN > Phone > Email > Name)
      |
      v
  Match found?
   /        \
  YES        NO
  |           |
  Update     Create
  contact    new contact
      |
      v
  Upload source image to contact
      |
      v
  Done - contact enriched in GHL
```

## Documentation

| Guide | What It Covers |
|-------|---------------|
| **[Setup Guide](docs/SETUP_GUIDE.md)** | Step-by-step: accounts to create, API keys to get, how to deploy |
| **[GHL Custom Fields](docs/GHL_CUSTOM_FIELDS.md)** | Exact custom fields to create in your GHL location |
| **[Troubleshooting](docs/TROUBLESHOOTING.md)** | Common problems and how to fix them |
| **[Environment Variables](docs/ENV_REFERENCE.md)** | Every configuration option explained |

## Quick Facts

- **Language:** Python 3.11+ / FastAPI
- **AI:** Anthropic Claude (Sonnet) for image extraction
- **CRM:** GoHighLevel v2 API (Private Integration)
- **Hosting:** Railway.app (recommended) or any Docker host
- **Database:** SQLite (built-in, no setup needed)
- **Cost:** ~$0.01-0.03 per image processed (Claude API usage)

## Requirements

You will need accounts with:
1. **Telegram** (free) — for the bot that receives images
2. **Anthropic** (pay-as-you-go) — for Claude AI image processing
3. **GoHighLevel** (existing subscription) — your CRM
4. **Railway.app** (free tier available) — to host the application

See the [Setup Guide](docs/SETUP_GUIDE.md) for detailed instructions on each.
