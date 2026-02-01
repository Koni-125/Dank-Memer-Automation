"""
ULTIMATE DANK MEMER BOT - MODULAR VERSION
All commands separated into clean modules
"""

import json
import asyncio
import aiohttp
import time
import random
import re
import hashlib
import sys
import os
from asyncio import Lock
from typing import List, Dict, Tuple, Optional

# Import all modules
from bot.core import SmartDankBot

# ============================================================================
# MAIN FUNCTION
# ============================================================================
async def main():
    print("""
╔═══════════════════════════════════════════════════════╗
║      ULTIMATE DANK MEMER BOT - MODULAR VERSION       ║
║      • Clean folder structure                        ║
║      • Easy to edit commands                        ║
║      • All workers separated                        ║
╚═══════════════════════════════════════════════════════╝
    """)
    
    # DEBUG: Show current directory and files
    print(f"📁 Current directory: {os.getcwd()}")
    print(f"📁 Files: {', '.join([f for f in os.listdir('.') if f.endswith('.json') or f.endswith('.py')])}")
    
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
    except Exception as e:
        print(f"❌ Failed to load config.json: {e}")
        return
    
    if not config.get('accounts'):
        print("❌ No accounts in config")
        return
    
    acc = config['accounts'][0]
    
    bot = SmartDankBot(
        token=acc['token'],
        channel_id=acc['channelID'],
        guild_id=acc.get('guildID')
    )
    
    async with bot:
        await bot.run_smart_system()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        print(f"\n💥 Fatal error: {e}")
        import traceback
        traceback.print_exc()