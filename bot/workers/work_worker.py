"""
Work command worker
"""

import asyncio
import time

async def work_worker(bot):
    print("👷 Work Worker started")
    
    while True:
        try:
            last_run = bot.command_last_run.get('work', 0)
            cooldown = 3600
            
            if time.time() - last_run < cooldown:
                wait = cooldown - (time.time() - last_run)
                if wait > 300:
                    await asyncio.sleep(300)
                    continue
                else:
                    await asyncio.sleep(wait)
            
            if bot.global_lock.locked():
                await bot.wait_for_lock("work")
            
            await bot.acquire_lock("work")
            
            print(f"\n💼 [WORK] Starting work shift...")
            success = await bot.send_command("work", subcommand="shift")
            
            if success:
                bot.command_last_run['work'] = time.time()
                print(f"✅ [WORK] Started shift")
                
                for game_num in range(1, 4):
                    print(f"   🎮 Minigame {game_num}/3...")
                    response = await bot.monitor_for_response(10)
                    
                    if response:
                        solved = await bot.work_solver.solve_minigame(bot, response)
                        if solved:
                            print(f"   ✅ Solved")
                    
                    await asyncio.sleep(2)
                
                print(f"✅ [WORK] Completed")
            
            await bot.release_lock()
            await asyncio.sleep(10)
            
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"❌ [WORK] Error: {e}")
            if bot.global_lock.locked():
                await bot.release_lock()
            await asyncio.sleep(30)