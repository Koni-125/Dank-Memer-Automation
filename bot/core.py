"""
Main bot class - handles Discord API and coordination
"""

import json
import asyncio
import aiohttp
import time
import hashlib
import re
import os
from asyncio import Lock
from typing import List, Dict, Tuple, Optional

# Import solvers
from bot.solvers.trivia import TriviaSolver
from bot.solvers.blackjack import ProfessionalBlackjackSolver
from bot.solvers.search import SmartSearchSolver
from bot.solvers.crime import SmartCrimeSolver
from bot.solvers.work import WorkMinigameSolver
from bot.solvers.adventure import AdventureSolver
from bot.solvers.fish_solver import NewFishSolver

# Import workers
from bot.workers.search_worker import search_worker
from bot.workers.crime_worker import crime_worker
from bot.workers.trivia_worker import trivia_worker
from bot.workers.postmemes_worker import postmemes_worker
from bot.workers.work_worker import work_worker
from bot.workers.fast_worker import fast_command_worker
from bot.workers.fish_worker import FishWorker

class SmartDankBot:
    def __init__(self, token, channel_id, guild_id=None):
        self.token = token
        self.channel_id = channel_id
        self.guild_id = guild_id
        self.session = None
        self.commands = self.load_commands()
        self.config = self.load_config()
        self.command_last_run = {}
        
        seed = f"{token}{channel_id}"
        self.session_id = hashlib.md5(seed.encode()).hexdigest()
        
        # Initialize all solvers
        self.blackjack_solver = ProfessionalBlackjackSolver()
        self.search_solver = SmartSearchSolver()
        self.crime_solver = SmartCrimeSolver()
        self.trivia_solver = TriviaSolver()
        self.work_solver = WorkMinigameSolver()
        self.adventure_solver = AdventureSolver()
        
        self.global_lock = Lock()
        self.lock_owner = None
        self.currently_running = set()
        
        self.last_api_call = 0
        self.min_request_gap = 2.0  # Increased to avoid rate limits
        
        print(f"🤖 Bot initialized with modular architecture")
    
    def load_config(self):
        try:
            with open('config.json', 'r') as f:
                config = json.load(f)
                return config
        except Exception as e:
            print(f"❌ Error loading config: {e}")
            return {"commands": {}}
    
    def load_commands(self):
        try:
            with open('dank_commands.json', 'r') as f:
                commands = json.load(f)
                return {cmd['name'].lower(): cmd for cmd in commands}
        except Exception as e:
            print(f"❌ Error loading commands: {e}")
            return {}
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(headers={
            "Authorization": self.token,
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def wait_rate_limit(self):
        now = time.time()
        if now - self.last_api_call < self.min_request_gap:
            wait_time = self.min_request_gap - (now - self.last_api_call)
            # print(f"⏳ Rate limit wait: {wait_time:.2f}s")
            await asyncio.sleep(wait_time)
        self.last_api_call = time.time()
    
    async def acquire_lock(self, command_name: str):
        if not self.global_lock.locked():
            self.lock_owner = command_name
            await self.global_lock.acquire()
            self.currently_running.add(command_name)
            return True
        return False
    
    async def release_lock(self):
        if self.global_lock.locked():
            if self.lock_owner:
                self.currently_running.discard(self.lock_owner)
            self.lock_owner = None
            self.global_lock.release()
    
    async def wait_for_lock(self, command_name: str, timeout: int = 10):
        if self.global_lock.locked():
            print(f"⏸️ [{command_name}] Waiting for {self.lock_owner} to finish...")
            try:
                await asyncio.wait_for(self.global_lock.acquire(), timeout=timeout)
                self.global_lock.release()
                print(f"✅ [{command_name}] Lock released, continuing...")
            except asyncio.TimeoutError:
                print(f"⚠️ [{command_name}] Lock timeout, proceeding anyway")
    
    async def send_command(self, command_name: str, subcommand: str = None, **kwargs) -> bool:
        await self.wait_rate_limit()
        
        cmd_data = self.commands.get(command_name.lower())
        if not cmd_data:
            print(f"❌ Command '{command_name}' not found in dank_commands.json")
            return False
        
        payload = {
            "type": 2,
            "application_id": "270904126974590976",
            "channel_id": self.channel_id,
            "session_id": self.session_id,
            "nonce": str(int(time.time() * 1000)),
            "data": {
                "version": cmd_data.get('version', '1'),
                "id": cmd_data['id'],
                "name": command_name,
                "type": 1
            }
        }
        
        # Add subcommand for fish
        if subcommand:
            payload["data"]["options"] = [{
                "type": 1,  # Subcommand
                "name": subcommand
            }]
        elif kwargs.get('bet'):
            payload["data"]["options"] = [{
                "type": 3,
                "name": "bet",
                "value": kwargs['bet']
            }]
        elif kwargs.get('amount'):
            payload["data"]["options"] = [{
                "type": 3,
                "name": "amount",
                "value": kwargs['amount']
            }]
        
        if self.guild_id:
            payload["guild_id"] = self.guild_id
        
        try:
            async with self.session.post(
                "https://discord.com/api/v9/interactions",
                json=payload,
                timeout=10
            ) as resp:
                if resp.status == 204:
                    return True
                elif resp.status == 429:
                    error_text = await resp.text()
                    retry_match = re.search(r'"retry_after":\s*([0-9.]+)', error_text)
                    if retry_match:
                        retry_time = float(retry_match.group(1))
                        print(f"⏳ Rate limited! Waiting {retry_time}s...")
                        await asyncio.sleep(retry_time)
                    return False
                else:
                    print(f"❌ Command failed: {resp.status}")
                    return False
        except Exception as e:
            print(f"❌ Network error: {e}")
            return False
    
    async def click_button(self, message_data: dict, button_label: str = None) -> bool:
        await self.wait_rate_limit()
        
        try:
            target_btn = None
            for row in message_data.get('components', []):
                for btn in row.get('components', []):
                    if btn.get('type') == 2:
                        if button_label:
                            if btn.get('label', '').lower() == button_label.lower():
                                target_btn = btn
                                break
                        else:
                            target_btn = btn
                            break
                if target_btn:
                    break
            
            if not target_btn:
                return False
            
            payload = {
                "type": 3,
                "nonce": str(int(time.time() * 1000)),
                "guild_id": message_data.get('guild_id', self.guild_id),
                "channel_id": self.channel_id,
                "message_id": message_data['id'],
                "session_id": self.session_id,
                "application_id": "270904126974590976",
                "data": {"component_type": 2, "custom_id": target_btn['custom_id']}
            }
            
            async with self.session.post(
                "https://discord.com/api/v9/interactions",
                json=payload,
                timeout=10
            ) as resp:
                return resp.status == 204
        except Exception as e:
            print(f"❌ Button click error: {e}")
            return False
    
    async def monitor_for_response(self, timeout: int = 10) -> dict:
        """Monitor for Dank Memer response with better detection"""
        start_time = time.time()
        last_message_id = None
        
        while time.time() - start_time < timeout:
            try:
                await self.wait_rate_limit()
                async with self.session.get(
                    f"https://discord.com/api/v9/channels/{self.channel_id}/messages?limit=10",
                    timeout=5
                ) as resp:
                    if resp.status == 200:
                        messages = await resp.json()
                        for msg in messages:
                            # Check if it's from Dank Memer
                            if msg.get('author', {}).get('id') == '270904126974590976':
                                # Only return if it's a new message
                                if last_message_id is None or msg['id'] != last_message_id:
                                    return msg
            except Exception as e:
                # print(f"Debug: Error getting messages: {e}")
                pass
            
            await asyncio.sleep(0.5)
        
        return None
    
    async def get_messages(self, limit: int = 10) -> list:
        """Get recent messages"""
        try:
            await self.wait_rate_limit()
            async with self.session.get(
                f"https://discord.com/api/v9/channels/{self.channel_id}/messages?limit={limit}",
                timeout=5
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
        except:
            pass
        return []
    
    async def wait_for_response(self, timeout=10):
        """Wait for Dank Memer response"""
        return await self.monitor_for_response(timeout)
    
    async def run_smart_system(self):
        print("\n" + "="*50)
        print("🤖 ULTIMATE DANK MEMER BOT - MODULAR VERSION")
        print("="*50)
        print(f"🕒 Started at: {time.strftime('%H:%M:%S')}")
        print("="*50)
        
        enabled_commands = []
        for cmd_name, cmd_config in self.config.get('commands', {}).items():
            if cmd_config.get('state', True):
                enabled_commands.append(cmd_name)
        
        print(f"📊 Enabled commands: {', '.join(enabled_commands)}")
        print("\n🧠 MODULES LOADED:")
        print("  • 🔍 Smart Search Worker")
        print("  • 🔫 Smart Crime Worker")
        print("  • ❓ Trivia Worker")
        print("  • 📱 Postmemes Worker")
        print("  • 💼 Work Worker")
        print("  • 🎣 Fish Worker")
        print("  • ⚡ Fast Command Workers")
        print("="*50)
        
        tasks = []
        
        # Start all enabled workers
        if 'search' in enabled_commands:
            tasks.append(asyncio.create_task(search_worker(self)))
            print("✅ Smart Search Worker started")
        
        if 'crime' in enabled_commands:
            tasks.append(asyncio.create_task(crime_worker(self)))
            print("✅ Smart Crime Worker started")
        
        if 'trivia' in enabled_commands:
            tasks.append(asyncio.create_task(trivia_worker(self)))
            print("✅ Trivia Worker started")
        
        if 'postmemes' in enabled_commands:
            tasks.append(asyncio.create_task(postmemes_worker(self)))
            print("✅ Postmemes Worker started")
        
        if 'work' in enabled_commands:
            tasks.append(asyncio.create_task(work_worker(self)))
            print("✅ Work Worker started")
        
        # 🎣 FISH WORKER
        if 'fish' in enabled_commands:
            fish_worker_instance = FishWorker(self)
            tasks.append(asyncio.create_task(fish_worker_instance.run()))
            print("✅ Fish Worker started")
        
        # Fast commands
        fast_commands = {
            'beg': False,
            'dig': False,
            'hunt': False,
            'highlow': True,
            'stream': False,
        }
        
        for cmd_name, needs_lock in fast_commands.items():
            if cmd_name in enabled_commands:
                tasks.append(asyncio.create_task(
                    fast_command_worker(self, cmd_name, needs_lock=needs_lock)
                ))
                print(f"✅ {cmd_name.upper()} Worker started")
        
        print(f"\n🎯 Total workers: {len(tasks)}")
        print("="*50)
        print("🚀 ALL SYSTEMS GO! Bot is running...")
        print("="*50)
        
        try:
            await asyncio.gather(*tasks)
        except KeyboardInterrupt:
            print("\n🛑 Stopping all workers...")
            for task in tasks:
                task.cancel()
            await asyncio.sleep(1)
            print("👋 Goodbye!")