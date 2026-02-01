"""
Crime command worker
"""

import asyncio
import time

async def crime_worker(bot):
    print("👷 Smart Crime Worker started")
    
    while True:
        try:
            last_run = bot.command_last_run.get('crime', 0)
            cooldown = 40
            
            if time.time() - last_run < cooldown:
                await asyncio.sleep(1)
                continue
            
            if bot.global_lock.locked():
                await bot.wait_for_lock("crime")
            
            await bot.acquire_lock("crime")
            
            print(f"\n🔫 [CRIME] Running smart crime...")
            success = await bot.send_command("crime")
            
            if success:
                bot.command_last_run['crime'] = time.time()
                response = await bot.monitor_for_response(6)
                
                if response and 'components' in response:
                    available_crimes, crime_scores = bot.crime_solver.analyze_crime_options(response)
                    
                    if available_crimes:
                        best_crime = bot.crime_solver.choose_best_crime(available_crimes, crime_scores)
                        print(f"⚖️ Crimes: {', '.join(available_crimes)}")
                        print(f"🏆 SELECTING: {best_crime}")
                        
                        click_success = await bot.click_button(response, best_crime)
                        
                        if click_success:
                            print(f"✅ [CRIME] Attempting {best_crime}")
                            await asyncio.sleep(3)
                
                print(f"✅ [CRIME] Completed")
            
            await bot.release_lock()
            await asyncio.sleep(5)
            
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"❌ [CRIME] Error: {e}")
            if bot.global_lock.locked():
                await bot.release_lock()
            await asyncio.sleep(30)