"""
Postmemes command worker
"""

import asyncio
import time

async def postmemes_worker(bot):
    print("👷 Postmemes Worker started")
    
    while True:
        try:
            last_run = bot.command_last_run.get('postmemes', 0)
            cooldown = 300
            
            if time.time() - last_run < cooldown:
                await asyncio.sleep(1)
                continue
            
            if bot.global_lock.locked():
                await bot.wait_for_lock("postmemes")
            
            await bot.acquire_lock("postmemes")
            
            print(f"\n📱 [POSTMEMES] Posting meme...")
            success = await bot.send_command("postmemes")
            
            if success:
                bot.command_last_run['postmemes'] = time.time()
                response = await bot.monitor_for_response(6)
                
                if response and 'components' in response:
                    buttons = response['components'][0]['components']
                    if buttons:
                        await bot.click_button(response, buttons[0].get('label'))
                        print(f"✅ [POSTMEMES] Selected {buttons[0].get('label')}")
                        
                        await asyncio.sleep(3)
                
                print(f"✅ [POSTMEMES] Completed")
            
            await bot.release_lock()
            await asyncio.sleep(5)
            
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"❌ [POSTMEMES] Error: {e}")
            if bot.global_lock.locked():
                await bot.release_lock()
            await asyncio.sleep(30)