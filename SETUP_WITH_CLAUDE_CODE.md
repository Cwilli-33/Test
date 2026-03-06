# Setup with Claude Code

## Step 1: Initial Setup

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy and configure environment
cp .env.example .env
nano .env  # Add your API keys

# Initialize database
python3 -c "from src.database import init_db; init_db()"
```

## Step 2: Expand Modules with Claude Code

The starter files are created. Now use Claude Code to implement each module:

### Expand Claude Extractor

```bash
claude code chat "I have a starter file at src/claude_extractor.py. Please expand it with:
- Full Claude Vision API integration
- Structured data extraction for MCA applications
- Confidence validation
- Error handling
The prompt should extract: business info, owner info, financial data, credit scores, MCA history"
```

### Expand Lead Matcher

```bash
claude code chat "Expand src/lead_matcher.py with:
- Multi-criteria search (EIN, phone, email, business name)
- Priority-based matching (EIN highest, then phone, email, name)
- Phone/EIN/email normalization
- Fuzzy business name matching with state verification"
```

### Expand Data Merger

```bash
claude code chat "Expand src/data_merger.py with:
- Smart field-by-field merging
- Preserve existing data when incoming is empty
- Add new data when existing is empty
- Intelligent conflict resolution (prefer higher revenue, newer credit scores)
- Tag management (append, don't replace)"
```

### Expand GHL Client

```bash
claude code chat "Expand src/ghl_client.py with:
- search_contacts method
- create_contact method
- update_contact method
- Proper error handling
- Custom field array formatting"
```

### Complete Main Application

```bash
claude code chat "Complete the webhook handler in src/main.py:
1. Extract image from Telegram message
2. Check fingerprint for duplicates
3. Download image and convert to base64
4. Extract with Claude
5. Search for existing lead with LeadMatcher
6. If match: merge data and update GHL
7. If no match: create new contact in GHL
8. Log extraction to database
Include full error handling and logging"
```

## Step 3: Add Tests

```bash
claude code chat "Create tests for lead_matcher.py covering:
- Phone normalization
- EIN normalization
- Business name similarity
- Search query building
- Match verification"
```

## Step 4: Test End-to-End

```bash
# Run the app
uvicorn src.main:app --reload

# Test in another terminal
curl http://localhost:8000/health
```

## Step 5: Deploy

Ask Claude Code for deployment help:

```bash
claude code chat "Help me deploy this to Railway. Walk me through:
1. Setting up Railway project
2. Configuring environment variables
3. Deploying the application
4. Setting up the database"
```

## Pro Tips

- Ask Claude Code to add logging to any function
- Ask Claude Code to write tests for new features
- Ask Claude Code to explain any code you don't understand
- Use Claude Code to debug errors by pasting the full error message

## Example Claude Code Workflows

**Add a Feature:**
```bash
claude code chat "Add email notifications when high-confidence leads (>0.85) are created. Use SMTP."
```

**Debug an Error:**
```bash
claude code chat "I'm getting this error when processing images: [paste error]. How do I fix it?"
```

**Improve Code:**
```bash
claude code chat "Review src/lead_matcher.py and suggest performance optimizations"
```

**Add Documentation:**
```bash
claude code chat "Add comprehensive docstrings to all functions in src/data_merger.py"
```
