#!/bin/bash

echo "========================================="
echo "Telegram → GHL Pipeline Setup"
echo "========================================="

# Check Python
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "✅ Python $python_version detected"

# Create virtual environment
echo "Creating virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Create .env
if [ ! -f .env ]; then
    cp .env.example .env
    echo "✅ .env file created - EDIT THIS FILE WITH YOUR API KEYS"
fi

# Initialize database
echo "Initializing database..."
python3 -c "from src.database import init_db; init_db()"

echo ""
echo "========================================="
echo "Setup Complete! 🎉"
echo "========================================="
echo ""
echo "Next steps:"
echo "1. Edit .env with your API keys"
echo "2. Read SETUP_WITH_CLAUDE_CODE.md"
echo "3. Use Claude Code to expand the modules"
echo ""
