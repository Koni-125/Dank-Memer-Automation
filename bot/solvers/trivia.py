"""
Trivia solver - reads trivia.json and finds answers
"""

import json
import os
import re

class TriviaSolver:
    def __init__(self):
        self.trivia_data = {}
        self.load_trivia_data()
    
    def load_trivia_data(self):
        try:
            if not os.path.exists('trivia.json'):
                print("❌ trivia.json file NOT FOUND in current directory!")
                print(f"📁 Current directory: {os.getcwd()}")
                return
            
            print(f"✅ Found trivia.json at: {os.path.abspath('trivia.json')}")
            
            with open('trivia.json', 'r', encoding='utf-8') as f:
                data = json.load(f)
                
                if isinstance(data, dict):
                    self.trivia_data = data
                    print(f"✅ Loaded {len(self.trivia_data)} trivia questions")
                else:
                    print("❌ trivia.json is not in correct format (should be dict)")
                    
        except json.JSONDecodeError as e:
            print(f"❌ Invalid JSON in trivia.json: {e}")
        except Exception as e:
            print(f"❌ Error loading trivia.json: {e}")
    
    def find_answer(self, question: str) -> str:
        if not self.trivia_data:
            return ""
        
        clean_question = question.strip()
        clean_question = re.sub(r'\*\*|\*|`', '', clean_question)
        
        if clean_question in self.trivia_data:
            return self.trivia_data[clean_question]
        
        question_lower = clean_question.lower()
        for q, a in self.trivia_data.items():
            if q.lower() == question_lower:
                return a
        
        for q, a in self.trivia_data.items():
            if q in clean_question or clean_question in q:
                return a
        
        question_words = set(question_lower.split())
        for q, a in self.trivia_data.items():
            q_words = set(q.lower().split())
            if len(question_words.intersection(q_words)) >= 3:
                return a
        
        return ""