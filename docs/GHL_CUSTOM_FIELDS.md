# GHL Custom Fields Setup

The pipeline stores extracted data in GoHighLevel custom fields. You need to create these fields in your GHL location before the pipeline can populate them.

---

## How to Create Custom Fields in GHL

1. Go to **Settings** > **Custom Fields** in your GHL location
2. Click **Add Custom Field** for each field listed below
3. Set the **Field Name** and **Field Type** exactly as shown
4. After creating all fields, you'll need to update the field IDs in the code (see bottom of this page)

---

## Required Custom Fields

Create all of the following custom fields in your GHL location. The **Field Type** must match exactly.

### Business Information

| # | Field Name | Field Type | What It Stores |
|---|-----------|-----------|----------------|
| 1 | EIN | Single Line | Federal EIN (XX-XXXXXXX format) |
| 2 | DBA | Single Line | "Doing Business As" name |
| 3 | Business Start Date | Single Line | Date business was started/incorporated |
| 4 | State of Incorporation | Single Line | 2-letter state code |
| 5 | Industry | Single Line | Business type (Restaurant, Trucking, etc.) |
| 6 | Business Phone | Phone | Business phone number |
| 7 | Funding Requested | Single Line | Dollar amount of funding requested |

### Owner 2 (Second Owner/Partner)

| # | Field Name | Field Type | What It Stores |
|---|-----------|-----------|----------------|
| 8 | Owner 2 Name | Single Line | Second owner/partner full name |
| 9 | Owner 2 Phone | Phone | Second owner phone number |

### Financial Information

| # | Field Name | Field Type | What It Stores |
|---|-----------|-----------|----------------|
| 10 | Monthly Revenue | Single Line | Average monthly revenue/deposits |
| 11 | Avg Daily Balance | Single Line | Average daily bank balance |
| 12 | True Revenue Avg 3mo | Single Line | 3-month average true revenue |

### Credit Information

| # | Field Name | Field Type | What It Stores |
|---|-----------|-----------|----------------|
| 13 | FICO Owner 1 | Single Line | Primary owner credit score |
| 14 | FICO Owner 2 | Single Line | Second owner credit score |
| 15 | Satisfactory Accounts | Single Line | Number of accounts in good standing |
| 16 | Total Tradelines | Single Line | Total number of credit tradelines |
| 17 | Now Delinquent | Single Line | Number of currently delinquent accounts |
| 18 | Num Chargeoffs | Single Line | Number of charge-off accounts |
| 19 | Leverage Pct | Single Line | Credit utilization percentage |

### MCA Position Info

| # | Field Name | Field Type | What It Stores |
|---|-----------|-----------|----------------|
| 20 | Num Positions | Single Line | Number of current MCA positions |
| 21 | Num Existing Positions | Single Line | Total existing funding positions |
| 22 | Statement Number | Single Line | Masked account/statement identifiers |

### Owner 1 Home Address

| # | Field Name | Field Type | What It Stores |
|---|-----------|-----------|----------------|
| 23 | Owner 1 Address | Single Line | Owner home street address |
| 24 | Owner 1 City | Single Line | Owner home city |
| 25 | Owner 1 State | Single Line | Owner home state (2-letter code) |
| 26 | Owner 1 Zip | Single Line | Owner home ZIP code |

### Pipeline Metadata

| # | Field Name | Field Type | What It Stores |
|---|-----------|-----------|----------------|
| 27 | AI Confidence | Single Line | Extraction confidence score (0.00-1.00) |
| 28 | AI Flags | Single Line | Warning flags (LOW_FICO, HIGH_LEVERAGE, etc.) |
| 29 | Batch Date | Single Line | Date the lead was processed (YYYYMMDD) |
| 30 | ISO Name | Single Line | Name of the ISO/broker on the document |
| 31 | Source Platform | Single Line | Where the lead originated |

### Source Documents (File Upload)

| # | Field Name | Field Type | What It Stores |
|---|-----------|-----------|----------------|
| 32 | Source Documents | File Upload | Original lead images/documents |

> **Important:** The "Source Documents" field MUST be created as **File Upload** type. This is where the original images sent to Telegram are stored on the contact.

---

## After Creating Fields: Update the Code

After creating all the custom fields, you need to update the field ID mapping in the code so the pipeline knows where to store each piece of data.

### How to Find Your Custom Field IDs

**Option 1: Via GHL API (Recommended)**

Use this URL in your browser (replace your API key and location ID):

```
https://services.leadconnectorhq.com/locations/{YOUR_LOCATION_ID}/customFields
```

With headers:
- `Authorization: Bearer {YOUR_GHL_API_KEY}`
- `Version: 2021-07-28`

Or use curl:
```bash
curl -s "https://services.leadconnectorhq.com/locations/YOUR_LOCATION_ID/customFields" \
  -H "Authorization: Bearer YOUR_GHL_API_KEY" \
  -H "Version: 2021-07-28" | python3 -m json.tool
```

This returns all your custom fields with their IDs.

**Option 2: Via GHL UI**

1. Go to **Settings** > **Custom Fields**
2. Click on a field to edit it
3. The field ID is in the URL or shown in the field details

### Where to Update in the Code

Open the file `src/data_merger.py` and find the `GHL_CUSTOM_FIELDS` dictionary near the top (around line 19). Replace each field ID with your own:

```python
GHL_CUSTOM_FIELDS = {
    # Business identifiers
    "ein":                      "YOUR_EIN_FIELD_ID",
    "dba":                      "YOUR_DBA_FIELD_ID",
    "business_start_date":      "YOUR_START_DATE_FIELD_ID",
    "state_of_incorporation":   "YOUR_STATE_INC_FIELD_ID",
    "industry":                 "YOUR_INDUSTRY_FIELD_ID",
    "business_phone":           "YOUR_BIZ_PHONE_FIELD_ID",
    "funding_requested":        "YOUR_FUNDING_REQ_FIELD_ID",

    # Owner 2
    "owner_2_name":             "YOUR_OWNER2_NAME_FIELD_ID",
    "owner_2_phone":            "YOUR_OWNER2_PHONE_FIELD_ID",

    # Financials
    "monthly_revenue":          "YOUR_MONTHLY_REV_FIELD_ID",
    "avg_daily_balance":        "YOUR_AVG_BAL_FIELD_ID",
    "true_revenue_avg_3mo":     "YOUR_TRUE_REV_FIELD_ID",

    # Credit
    "fico_owner1":              "YOUR_FICO1_FIELD_ID",
    "fico_owner2":              "YOUR_FICO2_FIELD_ID",
    "satisfactory_accounts":    "YOUR_SAT_ACCTS_FIELD_ID",
    "total_tradelines":         "YOUR_TRADELINES_FIELD_ID",
    "now_delinquent":           "YOUR_DELINQUENT_FIELD_ID",
    "num_chargeoffs":           "YOUR_CHARGEOFFS_FIELD_ID",
    "leverage_pct":             "YOUR_LEVERAGE_FIELD_ID",

    # MCA positions
    "num_positions":            "YOUR_NUM_POS_FIELD_ID",
    "num_existing_positions":   "YOUR_EXISTING_POS_FIELD_ID",

    # Statement number
    "statement_number":         "YOUR_STMT_NUM_FIELD_ID",

    # Owner 1 home address
    "owner1_address":           "YOUR_OWNER_ADDR_FIELD_ID",
    "owner1_city":              "YOUR_OWNER_CITY_FIELD_ID",
    "owner1_state":             "YOUR_OWNER_STATE_FIELD_ID",
    "owner1_zip":               "YOUR_OWNER_ZIP_FIELD_ID",

    # Metadata
    "ai_confidence":            "YOUR_CONFIDENCE_FIELD_ID",
    "ai_flags":                 "YOUR_FLAGS_FIELD_ID",
    "batch_date":               "YOUR_BATCH_DATE_FIELD_ID",
    "iso_name":                 "YOUR_ISO_FIELD_ID",
    "source_platform":          "YOUR_SOURCE_FIELD_ID",
}
```

Also update the **Source Documents** field ID in `src/main.py` (around line 266):

```python
SOURCE_DOCS_FIELD_ID = "YOUR_SOURCE_DOCS_FIELD_ID"
```

### Quick Verification

After updating the IDs, process a test image. Check the contact in GHL — all custom fields should be populated. If a field is empty, double-check that the field ID matches.

---

## Auto-Generated Tags

The pipeline also automatically adds tags to contacts. These don't require custom field setup — they use GHL's built-in tag system:

| Tag | When Applied |
|-----|-------------|
| `telegram-lead` | Every contact from the pipeline |
| `doc-mca_application` | Document identified as an MCA application |
| `doc-bank_statement` | Document identified as a bank statement |
| `doc-credit_report` | Document identified as a credit report |
| `doc-tax_document` | Document identified as a tax document |
| `doc-business_document` | Document identified as a business document |
| `doc-crm_screenshot` | Document identified as a CRM screenshot |
| `existing-mca` | Lead has existing MCA positions |
| `high-revenue` | Monthly revenue >= $50,000 |
| `fico-700+` | Owner FICO score 700 or above |
| `fico-sub550` | Owner FICO score below 550 |
| `matched-ein` | Matched to existing contact by EIN |
| `matched-phone` | Matched to existing contact by phone |
| `matched-email` | Matched to existing contact by email |
| `matched-name` | Matched to existing contact by business name |

---

## AI Flags Reference

The `AI Flags` custom field may contain these warning flags:

| Flag | Meaning |
|------|---------|
| `LOW_FICO` | Owner FICO score below 550 |
| `HIGH_DELINQUENCY` | More than 3 currently delinquent accounts |
| `HAS_CHARGEOFFS` | One or more charge-off accounts |
| `HIGH_LEVERAGE` | Credit utilization above 80% |
| `3+_POSITIONS` | 3 or more existing MCA positions |
| `LOW_REVENUE` | Monthly revenue below $15,000 |
| `LOW_AI_CONFIDENCE` | AI extraction confidence below 0.70 |
