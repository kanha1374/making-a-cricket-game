class Player:
    def __init__(self, name, skill_level):
        self.name = name
        self.skill_level = skill_level  # Skill level from 1 to 100
        self.state = 'active'  # can be 'active', 'injured', etc.

    def make_decision(self, situation):
        # Basic decision making based on situation
        if situation['type'] == 'batting':
            if self.skill_level > 50:
                return 'aggressive'
            else:
                return 'defensive'
        elif situation['type'] == 'bowling':
            if self.skill_level > 50:
                return 'fast'
            else:
                return 'spin'

class DecisionMakingEngine:
    def __init__(self, players):
        self.players = players

    def simulate_player_decision(self, situation):
        decisions = {}
        for player in self.players:
            decision = player.make_decision(situation)
            decisions[player.name] = decision
        return decisions

class GameState:
    def __init__(self):
        self.score = 0
        self.overs = 0
        self.players = []  # To store Player instances

    def update_score(self, runs):
        self.score += runs

    def next_over(self):
        self.overs += 1

    def add_player(self, player):
        self.players.append(player)

    def get_game_summary(self):
        return {'score': self.score, 'overs': self.overs, 'players': [p.name for p in self.players]}

# Placeholder for Machine Learning Integration
# def integrate_ml_model():
#     pass  # Function to integrate pre-trained ML models for advanced decision-making.

# Example initialization
if __name__ == '__main__':
    player1 = Player('John Doe', 80)
    player2 = Player('Jane Smith', 60)
    players = [player1, player2]
    decision_engine = DecisionMakingEngine(players)
    game_state = GameState()
    game_state.add_player(player1)
    game_state.add_player(player2)
    # Simulate a batting decision
    print(decision_engine.simulate_player_decision({'type': 'batting'}))
    # Summary of game state
    print(game_state.get_game_summary())