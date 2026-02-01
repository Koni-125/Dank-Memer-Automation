"""
Blackjack solver - makes decisions in blackjack minigames
"""

import re

class ProfessionalBlackjackSolver:
    def __init__(self):
        self.wins = 0
        self.losses = 0
        self.total_earnings = 0
    
    def extract_card_values(self, emoji_string: str) -> list:
        pattern = r'<:bjFace([0-9JQKA]+)[RB]:[0-9]+>'
        matches = re.findall(pattern, emoji_string)
        return matches if matches else []
    
    def calculate_hand_value(self, cards: list) -> tuple:
        total = 0
        ace_count = 0
        
        for card in cards:
            if card == 'A':
                total += 11
                ace_count += 1
            elif card in ['K', 'Q', 'J']:
                total += 10
            else:
                total += int(card)
        
        while total > 21 and ace_count > 0:
            total -= 10
            ace_count -= 1
        
        return total, (ace_count > 0)
    
    def make_decision(self, player_cards: list, dealer_cards: list, can_surrender: bool, can_double: bool, can_split: bool) -> int:
        player_sum, is_soft = self.calculate_hand_value(player_cards)
        if player_sum >= 17:
            return 1
        else:
            return 0
    
    def extract_net_value(self, description: str) -> int:
        pattern = r'Net:\s\*\*⏣ ([+\-]?[0-9,]+)\*\*'
        match = re.search(pattern, description)
        if not match:
            return 0
        value_str = match.group(1).replace(',', '')
        try:
            return int(value_str)
        except:
            return 0