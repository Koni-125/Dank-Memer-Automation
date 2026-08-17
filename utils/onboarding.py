"""Hardcoded Dank Memer onboarding levels.

Each level lists the commands/objectives needed to clear it and the commands
that unlock once it's cleared. This is the source of truth for onboarding;
the dynamic progress parser in cogs/commands.py fills in anything unknown.
"""

# level -> {
#   "commands": keys of commands the bot must run to progress,
#   "unlocks":   command keys that become available after this level
# }
ONBOARDING_LEVELS = {
    1: {
        "commands": ["beg", "search", "tidy"],
        "unlocks": ["balance", "hunt", "dig", "inventory"],
    },
    2: {
        "commands": ["inventory", "balance", "hunt", "dig"],
        "unlocks": [
            "work",
            "fish",
            "crime",
            "stream",
            "daily",
            "pm",
            "pet",
            "scratch",
            "hl",
            "adventure",
            "dep_all",
            "sell",
            "buy",
        ],
    },
    3: {
        "commands": ["work", "work", "sell", "buy"],
        "unlocks": ["cointoss", "slots", "snakeeyes", "roulette", "blackjack"],
    },
    4: {
        # Reach 250,000 pocket balance (passive; no command to run).
        "commands": [],
        "unlocks": [],
    },
    5: {
        # Lose 50,000 coins in each.
        "commands": ["slots", "cointoss", "snakeeyes"],
        "unlocks": [],
    },
    6: {
        # Use an item from your inventory.
        "commands": ["use", "item"],
        "unlocks": [],
    },
    7: {
        # Equip title, view profile, collect daily, win high-low.
        "commands": ["title", "profile", "daily", "hl"],
        "unlocks": [],
    },
    8: {
        # Use horseshoe, check multipliers, commit crimes, enter giveaway.
        "commands": ["use", "multipliers", "crime", "giveaway"],
        "unlocks": [],
    },
    9: {
        # Craft, plant and harvest a bean seed; trivia already done.
        "commands": ["craft", "farm"],
        "unlocks": [],
    },
    10: {
        # Run 20 more commands (passive), reach 350,000 pocket (passive,
        # already done), check quests, post 3 memes.
        "commands": ["quests", "pm"],
        "unlocks": [],
    },
    11: {
        # Check currencylog, check notifications list, enter the lottery.
        "commands": ["currencylog", "notifications", "lottery"],
        "unlocks": [],
    },
    12: {
        # Run /settings, deposit coins in your bank.
        "commands": ["settings", "dep_all"],
        "unlocks": [],
    },
    13: {
        # Run advancements, achievements, badges, collection, leaderboard,
        # skins view (and any other unlock-view commands shown).
        "commands": [
            "advancements",
            "achievements",
            "badges",
            "collection",
            "leaderboard",
            "skins",
            "play",
        ],
        "unlocks": [],
    },
    14: {
        # Complete an adventure, collect ad revenue from stream.
        "commands": ["adventure", "stream"],
        "unlocks": [],
    },
    15: {
        # Post/sell an item in the market, buy something from the market.
        "commands": ["market"],
        "unlocks": [],
    },
    16: {
        # Catch 15 fish.
        "commands": ["fish"],
        "unlocks": [],
    },
    17: {
        # Rename pet rock (view -> manage), hug pet rock (care), view pet
        # rock's room (rooms).
        "commands": ["pets"],
        "unlocks": [],
    },
    18: {
        # View level via /advancements levels, level up to 50 (passive),
        # use 5 shredded cheese.
        "commands": ["advancements", "use cheese"],
        "unlocks": [],
    },
}
