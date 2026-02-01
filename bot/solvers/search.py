"""
Search solver - chooses optimal search locations
"""

from typing import List, Dict, Tuple

class SmartSearchSolver:
    def __init__(self):
        self.location_stats = {}
        self.priority_locations = ["dresser", "attic", "couch", "laundry", "coat", "pocket"]
        self.secondary_locations = ["mailbox", "discord", "sewer", "grass", "tree"]
        self.avoid_locations = ["bank", "manhole", "trash"]
    
    def analyze_message(self, message: dict) -> Tuple[List[str], Dict[str, float]]:
        if 'components' not in message:
            return [], {}
        
        buttons = message['components'][0]['components']
        available_locations = []
        location_scores = {}
        
        for btn in buttons:
            location = btn.get('label', '').lower()
            available_locations.append(location)
            
            score = 0
            if location in self.priority_locations:
                score += 100
            elif location in self.secondary_locations:
                score += 50
            elif location in self.avoid_locations:
                score -= 100
            else:
                score += 10
            
            location_scores[location] = score
        
        return available_locations, location_scores
    
    def choose_best_location(self, available_locations: List[str], location_scores: Dict[str, float]) -> str:
        if not available_locations:
            return ""
        
        best_location = max(location_scores, key=location_scores.get)
        return best_location
    
    def update_stats(self, location: str, success: bool):
        if location not in self.location_stats:
            self.location_stats[location] = {'attempts': 0, 'successes': 0}
        
        self.location_stats[location]['attempts'] += 1
        if success:
            self.location_stats[location]['successes'] += 1