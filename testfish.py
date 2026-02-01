"""
PREDICTIVE FISHING BOT - Tracks position internally
"""

import asyncio
import json
import time
import aiohttp
import hashlib
import re
import os
from collections import deque

class PredictiveFishingBot:
    def __init__(self, token, channel_id, guild_id=None):
        self.token = token
        self.channel_id = channel_id
        self.guild_id = guild_id
        self.position_map = {
            'top left': [0, 0], 'top middle': [0, 1], 'top right': [0, 2],
            'middle left': [1, 0], 'middle': [1, 1], 'middle right': [1, 2],
            'bottom left': [2, 0], 'bottom middle': [2, 1], 'bottom right': [2, 2]
        }
        
    async def run(self):
        """Main fishing loop"""
        print("🎣 PREDICTIVE FISHING BOT")
        print("="*60)
        
        headers = {"Authorization": self.token}
        
        async with aiohttp.ClientSession(headers=headers) as session:
            while True:
                print(f"\n🔄 ATTEMPT: {time.strftime('%H:%M:%S')}")
                
                # 1. Find and click fishing
                if not await self.click_fishing(session):
                    await asyncio.sleep(30)
                    continue
                
                # 2. Wait for minigame
                await asyncio.sleep(6)
                minigame_msg = await self.get_minigame(session)
                if not minigame_msg:
                    print("❌ No minigame")
                    await asyncio.sleep(10)
                    continue
                
                print("🎮 MINIGAME FOUND!")
                
                # 3. Solve with prediction
                await self.solve_with_prediction(session, minigame_msg)
                
                # 4. Wait
                print("⏳ Waiting 50 seconds...")
                await asyncio.sleep(50)
    
    async def click_fishing(self, session):
        """Click fishing button"""
        messages = await self.get_messages(session, limit=15)
        
        for msg in messages:
            if msg.get('author', {}).get('id') == '270904126974590976':
                msg_str = json.dumps(msg)
                if 'fish-catch-fish' in msg_str and 'You can fish again' not in msg_str:
                    print("✅ Found fishing menu")
                    
                    pattern = r'"custom_id"\s*:\s*"(fish-catch-fish:[^"]+)"'
                    match = re.search(pattern, msg_str)
                    if not match:
                        continue
                    
                    btn_id = match.group(1)
                    print(f"✅ Button: {btn_id[:60]}...")
                    
                    success = await self.click_button(session, msg['id'], btn_id)
                    if success:
                        print("✅ Clicked!")
                        return True
        
        print("❌ No fishing menu")
        return False
    
    async def get_minigame(self, session):
        """Get minigame"""
        messages = await self.get_messages(session, limit=15)
        for msg in messages:
            if msg.get('author', {}).get('id') == '270904126974590976':
                msg_str = json.dumps(msg)
                if 'fish-catch-move' in msg_str:
                    return msg
        return None
    
    async def solve_with_prediction(self, session, minigame_msg):
        """Solve with position prediction"""
        # Get initial state
        initial_positions = self.get_positions(minigame_msg)
        if not initial_positions.get('tool') or not initial_positions.get('shadow'):
            print("❌ Could not read positions")
            return
        
        hook = initial_positions['tool']
        fish = initial_positions['shadow']
        bomb = initial_positions.get('mine')
        
        print(f"📍 Start: Hook {hook}, Fish {fish}")
        if bomb:
            print(f"⚠️  Bomb: {bomb}")
        
        # Calculate complete path
        path = self.calculate_complete_path(hook, fish, bomb)
        if not path:
            print("❌ No path found")
            return
        
        print(f"🧭 Complete path: {' → '.join(path)}")
        
        # Follow the path
        current_msg = minigame_msg
        current_msg_id = minigame_msg['id']
        current_hook = hook[:]  # Copy
        
        for i, move in enumerate(path):
            print(f"\n   Step {i+1}: Moving {move.upper()} from {current_hook}...")
            
            # Get current buttons
            buttons = self.get_buttons(current_msg)
            print(f"   🔍 Buttons: {[b['direction'] for b in buttons]}")
            
            # Find button for this move
            btn_id = None
            for btn in buttons:
                if btn['direction'] == move:
                    btn_id = btn['custom_id']
                    break
            
            if not btn_id:
                print(f"   ❌ No {move.upper()} button")
                return
            
            print(f"   📤 Clicking {move.upper()}...")
            
            # Click button
            success = await self.click_button(session, current_msg_id, btn_id)
            if not success:
                print(f"   ❌ Failed to click")
                return
            
            # Update predicted position
            current_hook = self.move_position(current_hook, move)
            print(f"   ✅ Predicted new position: {current_hook}")
            
            # Wait for animation
            if i < len(path) - 1:  # Not last move
                print(f"   ⏳ Waiting 3 seconds...")
                await asyncio.sleep(3)
                
                # Get updated message for next iteration
                new_msgs = await self.get_messages(session, limit=10)
                for msg in new_msgs:
                    if msg.get('id') == current_msg_id:
                        current_msg = msg
                        break
        
        # After following path, click Catch
        print(f"\n   🎣 Path complete! Hook should be at {current_hook}")
        print(f"   Target fish is at {fish}")
        
        # Wait a bit for final update
        await asyncio.sleep(2)
        
        # Find Catch button
        print(f"   Looking for Catch button...")
        
        latest_msgs = await self.get_messages(session, limit=10)
        catch_msg = None
        for msg in latest_msgs:
            if msg.get('author', {}).get('id') == '270904126974590976':
                msg_str = json.dumps(msg)
                if 'fish-catch-catch' in msg_str:
                    catch_msg = msg
                    break
        
        if catch_msg:
            catch_id = self.extract_button(catch_msg, 'fish-catch-catch')
            if catch_id:
                print(f"   ✅ Found Catch button")
                success = await self.click_button(session, catch_msg['id'], catch_id)
                if success:
                    print("   🎉 CATCH CLICKED!")
                else:
                    print("   ❌ Catch failed")
            else:
                print("   ❌ No Catch button ID")
        else:
            print("   ❌ No Catch message")
    
    def calculate_complete_path(self, start, target, bomb):
        """Calculate complete path with BFS"""
        grid_size = 3
        
        def bfs():
            queue = deque([(start, [])])
            visited = set([tuple(start)])
            
            while queue:
                pos, path = queue.popleft()
                
                if pos == target:
                    return path
                
                # Try moves in order: up, left, right, down
                moves = [(-1, 0, 'u'), (0, -1, 'l'), (0, 1, 'r'), (1, 0, 'd')]
                
                for dr, dc, direction in moves:
                    new_pos = [pos[0] + dr, pos[1] + dc]
                    
                    if (0 <= new_pos[0] < grid_size and 
                        0 <= new_pos[1] < grid_size and
                        tuple(new_pos) not in visited and
                        (bomb is None or new_pos != bomb)):
                        
                        visited.add(tuple(new_pos))
                        queue.append((new_pos, path + [direction]))
            
            return []
        
        return bfs()
    
    def move_position(self, pos, direction):
        """Move position based on direction"""
        moves = {
            'l': [0, -1],  # left
            'u': [-1, 0],  # up
            'r': [0, 1],   # right
            'd': [1, 0]    # down
        }
        
        if direction in moves:
            move = moves[direction]
            new_pos = [pos[0] + move[0], pos[1] + move[1]]
            # Keep in bounds
            new_pos[0] = max(0, min(2, new_pos[0]))
            new_pos[1] = max(0, min(2, new_pos[1]))
            return new_pos
        
        return pos
    
    def get_positions(self, message):
        """Get positions from message"""
        positions = {}
        msg_str = json.dumps(message)
        
        # Look for description
        desc_match = re.search(r'"description"\s*:\s*"([^"]+)"', msg_str)
        if not desc_match:
            return positions
        
        desc = desc_match.group(1).lower()
        
        patterns = [
            (r'tool:\s*([a-z\s]+?)(?:\.|$)', 'tool'),
            (r'shadow:\s*([a-z\s]+?)(?:\.|$)', 'shadow'),
            (r'mine:\s*([a-z\s]+?)(?:\.|$)', 'mine')
        ]
        
        for pattern, key in patterns:
            match = re.search(pattern, desc)
            if match:
                pos_text = match.group(1).strip()
                if pos_text in self.position_map:
                    positions[key] = self.position_map[pos_text]
        
        return positions
    
    def get_buttons(self, message):
        """Get arrow buttons"""
        buttons = []
        msg_str = json.dumps(message)
        
        # Find all fish-catch-move buttons
        pattern = r'"custom_id"\s*:\s*"(fish-catch-move:[^"]+)"'
        matches = re.findall(pattern, msg_str)
        
        for custom_id in matches:
            # Get direction from custom_id
            if ':l"' in custom_id or custom_id.endswith(':l'):
                direction = 'l'
            elif ':u"' in custom_id or custom_id.endswith(':u'):
                direction = 'u'
            elif ':r"' in custom_id or custom_id.endswith(':r'):
                direction = 'r'
            elif ':d"' in custom_id or custom_id.endswith(':d'):
                direction = 'd'
            else:
                continue
            
            buttons.append({
                'custom_id': custom_id.replace('"', ''),
                'direction': direction
            })
        
        return buttons
    
    def extract_button(self, message, pattern):
        """Extract button ID"""
        msg_str = json.dumps(message)
        regex = f'"custom_id"\\s*:\\s*"([^"]*{re.escape(pattern)}[^"]*)"'
        match = re.search(regex, msg_str)
        return match.group(1) if match else None
    
    async def click_button(self, session, message_id, custom_id):
        """Click button"""
        try:
            seed = f"{self.token}{self.channel_id}{int(time.time())}"
            session_id = hashlib.md5(seed.encode()).hexdigest()
            
            payload = {
                "type": 3,
                "nonce": str(int(time.time() * 1000)),
                "channel_id": self.channel_id,
                "message_id": message_id,
                "session_id": session_id,
                "application_id": "270904126974590976",
                "data": {
                    "component_type": 2,
                    "custom_id": custom_id
                },
                "message_flags": 32768
            }
            
            if self.guild_id:
                payload["guild_id"] = self.guild_id
            
            async with session.post(
                "https://discord.com/api/v9/interactions",
                json=payload,
                timeout=10
            ) as resp:
                return resp.status == 204
                
        except Exception as e:
            print(f"      ❌ Error: {e}")
            return False
    
    async def get_messages(self, session, limit=10):
        """Get messages"""
        try:
            async with session.get(
                f"https://discord.com/api/v9/channels/{self.channel_id}/messages?limit={limit}",
                timeout=5
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
        except:
            pass
        return []

async def main():
    print("🎣 PREDICTIVE FISHING BOT")
    print("="*60)
    print("CALCULATES COMPLETE PATH AND FOLLOWS IT")
    print("="*60)
    
    if not os.path.exists('config.json'):
        print("❌ config.json not found!")
        return
    
    with open('config.json', 'r') as f:
        config = json.load(f)
    
    if not config.get('accounts'):
        print("❌ No accounts in config")
        return
    
    acc = config['accounts'][0]
    
    bot = PredictiveFishingBot(
        token=acc['token'],
        channel_id=acc['channelID'],
        guild_id=acc.get('guildID')
    )
    
    print("\n🎯 THIS CALCULATES THE WHOLE PATH FIRST!")
    print("="*60)
    
    input("\nPress Enter for predictive fishing...")
    
    try:
        await bot.run()
    except KeyboardInterrupt:
        print("\n🎣 Predictive fishing complete!")
    except Exception as e:
        print(f"\n💥 Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())