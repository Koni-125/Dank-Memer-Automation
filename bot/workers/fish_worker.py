# diagnose_buttons.py
import asyncio
import json
import aiohttp
import time

async def diagnose():
    print("🔍 DIAGNOSTIC: Compare Search vs Fishing Buttons")
    print("="*60)
    
    # Load config
    with open('config.json', 'r') as f:
        config = json.load(f)
    
    acc = config['accounts'][0]
    token = acc['token']
    channel_id = acc['channelID']
    
    headers = {"Authorization": token}
    
    async with aiohttp.ClientSession(headers=headers) as session:
        # Get recent messages
        async with session.get(
            f"https://discord.com/api/v9/channels/{channel_id}/messages?limit=20"
        ) as resp:
            messages = await resp.json()
        
        print(f"📊 Found {len(messages)} messages")
        
        # Analyze each Dank Memer message
        for msg in messages:
            if msg.get('author', {}).get('id') == '270904126974590976':
                print(f"\n📨 Message ID: {msg['id']}")
                print(f"📅 Time: {msg.get('timestamp')}")
                
                # Check if it's search or fishing
                is_search = 'search' in str(msg).lower() or any(
                    'search' in str(comp).lower() for comp in msg.get('components', [])
                )
                
                is_fishing = 'fish' in str(msg).lower() or any(
                    'fish' in str(comp).lower() for comp in msg.get('components', [])
                )
                
                if is_search:
                    print("🔍 SEARCH MESSAGE")
                elif is_fishing:
                    print("🎣 FISHING MESSAGE")
                else:
                    print("❓ OTHER MESSAGE")
                
                # Analyze component structure
                if msg.get('components'):
                    print(f"🎮 Components structure:")
                    
                    # Function to print structure
                    def print_structure(data, indent=0, path=""):
                        if isinstance(data, dict):
                            comp_type = data.get('type')
                            label = data.get('label', '')
                            custom_id = data.get('custom_id', '')
                            
                            if comp_type:
                                type_name = {
                                    1: "Action Row",
                                    2: "Button",
                                    3: "Select Menu",
                                    9: "??? (Type 9)",
                                    10: "??? (Type 10)",
                                    11: "??? (Type 11)",
                                    14: "??? (Type 14)",
                                    17: "Container (Type 17)"
                                }.get(comp_type, f"Type {comp_type}")
                                
                                print(f"{'  ' * indent}{type_name}: {label or ''} {custom_id[:20] or ''}")
                            
                            for key, value in data.items():
                                if key not in ['type', 'label', 'custom_id']:
                                    print_structure(value, indent + 1, f"{path}.{key}")
                        
                        elif isinstance(data, list):
                            for i, item in enumerate(data):
                                print_structure(item, indent, f"{path}[{i}]")
                    
                    print_structure(msg['components'])
                    
                    # Extract ALL buttons
                    all_buttons = []
                    def extract_buttons(data):
                        if isinstance(data, dict):
                            if data.get('type') == 2:
                                all_buttons.append({
                                    'label': data.get('label'),
                                    'custom_id': data.get('custom_id'),
                                    'style': data.get('style'),
                                    'type': data.get('type')
                                })
                            for key, value in data.items():
                                extract_buttons(value)
                        elif isinstance(data, list):
                            for item in data:
                                extract_buttons(item)
                    
                    extract_buttons(msg)
                    
                    print(f"\n🎯 Found {len(all_buttons)} buttons:")
                    for btn in all_buttons:
                        print(f"  • '{btn['label']}'")
                        print(f"    ID: {btn['custom_id']}")
                        print(f"    Style: {btn['style']}")
                        print(f"    Type: {btn['type']}")
                        
                        # Try to click it and see what happens
                        if btn['label'] == 'Go Fishing':
                            print(f"\n    🧪 TESTING CLICK...")
                            
                            # Try different interaction types
                            for interaction_type in [2, 3, 5]:
                                payload = {
                                    "type": interaction_type,
                                    "nonce": str(int(time.time() * 1000)),
                                    "channel_id": channel_id,
                                    "message_id": msg['id'],
                                    "session_id": "test_" + str(int(time.time())),
                                    "application_id": "270904126974590976",
                                    "data": {
                                        "component_type": 2,
                                        "custom_id": btn['custom_id']
                                    }
                                }
                                
                                try:
                                    async with session.post(
                                        "https://discord.com/api/v9/interactions",
                                        json=payload,
                                        timeout=5
                                    ) as click_resp:
                                        print(f"      Type {interaction_type}: Status {click_resp.status}")
                                        if click_resp.status != 204:
                                            error = await click_resp.text()
                                            print(f"      Error: {error[:100]}")
                                except Exception as e:
                                    print(f"      Type {interaction_type} error: {e}")
                                
                                await asyncio.sleep(1)
                else:
                    print("📝 No components")
                
                print("-"*40)

if __name__ == "__main__":
    asyncio.run(diagnose())