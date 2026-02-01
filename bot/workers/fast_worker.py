"""
Fast command worker - handles beg, dig, hunt, highlow, stream
"""

import asyncio
import time

async def fast_command_worker(bot, cmd_name: str, needs_lock: bool = False):
    print(f"👷 {cmd_name.upper()} Worker started")
    
    while True:
        try:
            last_run = bot.command_last_run.get(cmd_name, 0)
            cooldown = 40
            
            if time.time() - last_run < cooldown:
                await asyncio.sleep(1)
                continue
            
            if needs_lock and bot.global_lock.locked():
                await bot.wait_for_lock(cmd_name)
            
            if needs_lock:
                await bot.acquire_lock(cmd_name)
            
            print(f"\n⚡ [{cmd_name.upper()}] Running...")
            success = await bot.send_command(cmd_name)
            
            if success:
                bot.command_last_run[cmd_name] = time.time()
                
                if needs_lock:
                    response = await bot.monitor_for_response(6)
                    if response and 'components' in response:
                        buttons = response['components'][0]['components']
                        if buttons:
                            await bot.click_button(response, buttons[0].get('label'))
                
                print(f"✅ [{cmd_name.upper()}] Completed")
            
            if needs_lock:
                await bot.release_lock()
            
            await asyncio.sleep(1)
            
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"❌ [{cmd_name.upper()}] Error: {e}")
            if needs_lock and bot.global_lock.locked():
                await bot.release_lock()
            await asyncio.sleep(10)