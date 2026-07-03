#!/bin/bash

echo "🚀 Spider Bot Starting..."

# Setup virtual environment if not exists
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual env
source venv/bin/activate

# Install dependencies if requirements.txt exists
if [ -f "requirements.txt" ]; then
    echo "📦 Installing dependencies..."
    pip install --no-cache-dir -r requirements.txt
fi

# Create data directory
mkdir -p data

# Create default JSON files
[ -f "data/owners.json" ] || echo '{}' > data/owners.json
[ -f "data/approved_users.json" ] || echo '{}' > data/approved_users.json
[ -f "data/admins.json" ] || echo '{}' > data/admins.json
[ -f "data/resellers.json" ] || echo '{}' > data/resellers.json
[ -f "data/github_tokens.json" ] || echo '[]' > data/github_tokens.json
[ -f "data/attack_history.json" ] || echo '[]' > data/attack_history.json
[ -f "data/pending_users.json" ] || echo '[]' > data/pending_users.json
[ -f "data/users.json" ] || echo '[]' > data/users.json

echo "✅ Data files ready"
echo "🔥 Starting bot..."

# Run bot
python3 main.py
