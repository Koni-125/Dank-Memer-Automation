# solvers/fish_solver.py
import re

class NewFishSolver:
    """Solver for the updated fishing system"""
    
    def __init__(self):
        self.steps = []
    
    def analyze_fishing_response(self, response: dict) -> dict:
        """Analyze fishing response and determine next action"""
        if not response:
            return {'action': 'wait', 'reason': 'No response'}
        
        description = self._get_description(response)
        
        print(f"   🔍 Analyzing: {description[:100]}...")
        
        # Check for different states
        if "go fishing" in description.lower():
            return {'action': 'click_button', 'button_label': 'Go fishing', 'step': 1}
        
        elif any(word in description.lower() for word in ['arrow', 'bomb', 'minigame', 'quick!']):
            return {'action': 'minigame', 'step': 2}
        
        elif "catch" in description.lower() or "reel" in description.lower():
            return {'action': 'click_button', 'button_label': 'Catch', 'step': 3}
        
        elif "caught" in description.lower() or "got away" in description.lower():
            return {'action': 'complete', 'step': 4}
        
        return {'action': 'wait', 'reason': 'Unknown state'}
    
    def _get_description(self, response: dict) -> str:
        """Extract description from response"""
        if not response.get('embeds'):
            return ""
        
        embed = response['embeds'][0]
        return embed.get('description', '').lower()
    
    def get_minigame_strategy(self, response):
        """Get strategy for minigame"""
        if 'components' not in response:
            return {'move': 'wait'}
        
        # Check for bomb position
        description = self._get_description(response)
        
        # Simple strategy: Avoid bomb, move toward center
        return {'move': 'right', 'reason': 'Default safe move'}