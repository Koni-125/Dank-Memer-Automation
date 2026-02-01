"""
Trivia command worker
"""

import asyncio
import time
import re

async def trivia_worker(bot):
    print("👷 Trivia Worker started")
    
    while True:
        try:
            last_run = bot.command_last_run.get('trivia', 0)
            cooldown = 40
            
            if time.time() - last_run < cooldown:
                await asyncio.sleep(1)
                continue
            
            if bot.global_lock.locked():
                await bot.wait_for_lock("trivia")
            
            await bot.acquire_lock("trivia")
            
            print(f"\n❓ [TRIVIA] Running trivia...")
            success = await bot.send_command("trivia")
            
            if success:
                bot.command_last_run['trivia'] = time.time()
                response = await bot.monitor_for_response(8)
                
                if response and 'embeds' in response:
                    embed = response['embeds'][0]
                    description = embed.get('description', '')
                    
                    lines = description.split('\n')
                    question = ""
                    for line in lines:
                        line = line.strip()
                        if line and not line.startswith('**'):
                            question = line
                            break
                    
                    if not question and lines:
                        question = lines[0]
                    
                    question = re.sub(r'\*\*|\*|`', '', question).strip()
                    
                    print(f"📝 Question: {question[:80]}...")
                    
                    answer = bot.trivia_solver.find_answer(question)
                    
                    if answer:
                        print(f"✅ Database answer: {answer}")
                        if 'components' in response:
                            clicked = False
                            for row in response['components']:
                                for btn in row.get('components', []):
                                    btn_label = btn.get('label', '')
                                    if answer.lower() in btn_label.lower() or btn_label.lower() in answer.lower():
                                        await bot.click_button(response, btn_label)
                                        print(f"✅ Clicked: {btn_label}")
                                        clicked = True
                                        break
                                if clicked:
                                    break
                            
                            if not clicked and response['components'][0]['components']:
                                btn = response['components'][0]['components'][0]
                                await bot.click_button(response, btn.get('label'))
                                print(f"⚠️ Couldn't match, clicked: {btn.get('label')}")
                    else:
                        print(f"⚠️ No answer in database")
                        if 'components' in response and response['components'][0]['components']:
                            btn = response['components'][0]['components'][0]
                            await bot.click_button(response, btn.get('label'))
                            print(f"🤔 Guessed: {btn.get('label')}")
            
            await bot.release_lock()
            await asyncio.sleep(5)
            
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"❌ [TRIVIA] Error: {e}")
            if bot.global_lock.locked():
                await bot.release_lock()
            await asyncio.sleep(30)
            