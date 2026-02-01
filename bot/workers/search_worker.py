import aiohttp
import asyncio

async def test_token():
    TOKEN = "YOUR_TOKEN_HERE"
    CHANNEL_ID = "YOUR_CHANNEL_ID_HERE"
    
    headers = {
        "Authorization": TOKEN,
        "Content-Type": "application/json"
    }
    
    async with aiohttp.ClientSession(headers=headers) as session:
        # Test 1: Get channel info
        url = f"https://discord.com/api/v9/channels/{CHANNEL_ID}"
        async with session.get(url) as resp:
            print(f"Channel test: {resp.status}")
            if resp.status == 200:
                data = await resp.json()
                print(f"✅ Channel name: {data.get('name', 'Unknown')}")
        
        # Test 2: Get messages
        url = f"https://discord.com/api/v9/channels/{CHANNEL_ID}/messages?limit=1"
        async with session.get(url) as resp:
            print(f"Messages test: {resp.status}")
            if resp.status == 200:
                print("✅ Token is working!")

asyncio.run(test_token())