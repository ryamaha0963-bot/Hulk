#!/bin/bash

echo "🚀 Starting Spider Bot on Railway..."

# Install dependencies manually if needed
pip install --no-cache-dir python-telegram-bot PyGithub python-dotenv aiohttp asyncio colorama ujson uvloop aiofiles httpx tenacity

# Create data directory
mkdir -p data

# Create default JSON files if not exist
[ -f "data/owners.json" ] || echo '{}' > data/owners.json
[ -f "data/approved_users.json" ] || echo '{}' > data/approved_users.json
[ -f "data/admins.json" ] || echo '{}' > data/admins.json
[ -f "data/resellers.json" ] || echo '{}' > data/resellers.json
[ -f "data/github_tokens.json" ] || echo '[]' > data/github_tokens.json
[ -f "data/attack_history.json" ] || echo '[]' > data/attack_history.json
[ -f "data/pending_users.json" ] || echo '[]' > data/pending_users.json
[ -f "data/users.json" ] || echo '[]' > data/users.json

echo "✅ Data files ready"

# Start the bot
python3 main.py
