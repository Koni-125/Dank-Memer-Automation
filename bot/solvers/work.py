"""
Work minigame solver
"""

class WorkMinigameSolver:
    async def solve_minigame(self, bot_instance, message: dict) -> bool:
        if not message.get('embeds'):
            return False
        
        if 'components' in message and message['components'][0]['components']:
            button = message['components'][0]['components'][0]
            return await bot_instance.click_button(message, button.get('label', ''))
        
        return False