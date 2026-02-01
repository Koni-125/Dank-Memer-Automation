"""
Crime solver - selects most profitable crimes
"""

from typing import List, Dict, Tuple

class SmartCrimeSolver:
    def __init__(self):
        self.crime_stats = {}
        self.crime_rewards = {
            'hacking': {'min': 2000, 'max': 6000, 'risk': 0.5},
            'tax evasion': {'min': 1500, 'max': 4500, 'risk': 0.4},
            'fraud': {'min': 1000, 'max': 3500, 'risk': 0.3},
            'eating a hot dog sideways': {'min': 500, 'max': 2000, 'risk': 0.2},
            'trespassing': {'min': 800, 'max': 2500, 'risk': 0.35},
            'bank robbing': {'min': 5000, 'max': 15000, 'risk': 0.7},
            'murder': {'min': 3000, 'max': 9000, 'risk': 0.8},
            'stab grandma': {'min': 4000, 'max': 12000, 'risk': 0.75},
            'drug distribution': {'min': 2500, 'max': 7500, 'risk': 0.65},
            'littering': {'min': 300, 'max': 1000, 'risk': 0.1},
            'cyber bullying': {'min': 700, 'max': 2200, 'risk': 0.25},
        }
    
    def analyze_crime_options(self, message: dict) -> Tuple[List[str], Dict[str, float]]:
        if 'components' not in message:
            return [], {}
        
        buttons = message['components'][0]['components']
        available_crimes = []
        crime_scores = {}
        
        for btn in buttons:
            crime_name = btn.get('label', '').lower()
            available_crimes.append(crime_name)
            
            crime_data = self.crime_rewards.get(crime_name, {'min': 1000, 'max': 3000, 'risk': 0.5})
            avg_reward = (crime_data['min'] + crime_data['max']) / 2
            risk = crime_data['risk']
            
            expected_value = avg_reward * (1 - risk)
            score = expected_value
            
            crime_scores[crime_name] = score
        
        return available_crimes, crime_scores
    
    def choose_best_crime(self, available_crimes: List[str], crime_scores: Dict[str, float]) -> str:
        if not available_crimes or not crime_scores:
            return available_crimes[0] if available_crimes else ""
        
        print(f"📊 CRIME SCORES:")
        for crime, score in crime_scores.items():
            print(f"   {crime}: {score:.2f}")
        
        best_crime = max(crime_scores.items(), key=lambda x: x[1])[0]
        return best_crime
    
    def update_stats(self, crime_name: str, success: bool, reward: int = 0):
        if crime_name not in self.crime_stats:
            self.crime_stats[crime_name] = {'attempts': 0, 'successes': 0, 'total_reward': 0}
        
        self.crime_stats[crime_name]['attempts'] += 1
        if success:
            self.crime_stats[crime_name]['successes'] += 1
            self.crime_stats[crime_name]['total_reward'] += reward