# Telegram → GHL Pipeline

Production-grade Python/FastAPI application for automated MCA lead processing.

## Quick Start

```bash
# 1. Copy .env.example to .env and add your API keys
cp .env.example .env
nano .env

# 2. Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Initialize database
python3 -c "from src.database import init_db; init_db()"

# 5. Run application
uvicorn src.main:app --reload
```

## Next Steps with Claude Code

The starter files are created. Now use Claude Code to expand the implementation:

```bash
# In Claude Code, ask:
claude code chat "Expand src/claude_extractor.py with the full Claude Vision implementation"
claude code chat "Expand src/lead_matcher.py with multi-criteria matching logic"
claude code chat "Expand src/data_merger.py with smart merge functionality"
claude code chat "Expand src/ghl_client.py with complete GHL API integration"
claude code chat "Complete the webhook handler in src/main.py"
```

## Features

- ✅ Image fingerprinting (prevents duplicates)
- ✅ Database models and migrations
- ✅ Docker support
- ⏳ Claude Vision extraction (expand with Claude Code)
- ⏳ Multi-criteria matching (expand with Claude Code)
- ⏳ Smart data merging (expand with Claude Code)
- ⏳ GHL API integration (expand with Claude Code)

## Documentation

Full implementation details were provided in the original codebase.
Use Claude Code to implement each module step by step.

## Architecture

```
Telegram → Fingerprint → Download → Extract (Claude) →
Match (Multi-criteria) → Merge (Smart) → GHL (Create/Update)
```

For full documentation, ask Claude Code to generate it based on the implementation.
