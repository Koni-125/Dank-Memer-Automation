import time

import components_v2

from discord.ext import commands

# One-shot "pick a side" games (button appears in the first response).
_SIDE_CHOICES = {
    "cointoss": ["Heads", "Tails"],
    "roulette": ["Red", "Black"],
}

# "keep playing" action buttons (only clickable on the follow-up/edited message).
_CONTINUE_ACTIONS = {
    "slots": "Spin Again",
    "snakeeyes": "Roll Again",
    "blackjack": "Hit",
}

# How long a session must be inactive before we consider it finished and let a
# different game start.
_SESSION_TIMEOUT = 30


class Gambling(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.message_dispatcher.register(self.log_messages)
        self.bot.message_dispatcher.register(self.log_messages_edit, edit=True)
        self._active_game = None
        self._last_interaction = 0

    def _gambling_enabled(self):
        try:
            return self.bot.settings_dict["settings"]["gambling"]["enabled"]
        except (KeyError, TypeError):
            return False

    def _game_is_active(self, game):
        # Stop playing a game once its onboarding objective is complete.
        onboarding_cog = self.bot.get_cog("Onboarding")
        if onboarding_cog is None:
            return True
        return game in onboarding_cog.active_onboarding_tasks

    def is_busy(self):
        # True while a gambling session is actively running, so the command
        # loop won't fire another gambling command at the same time.
        if not self._gambling_enabled():
            return False
        if self._active_game is None:
            return False
        return time.time() - self._last_interaction < _SESSION_TIMEOUT

    def mark_session_started(self):
        # The command loop just sent a gambling command; reserve this as the
        # active session so no other gambling command is sent until it ends.
        if self._gambling_enabled() and self._active_game is None:
            self._active_game = "pending"
            self._last_interaction = time.time()

    async def _handle(self, message):
        if message.channel_id != self.bot.channel.id:
            return
        if not self._gambling_enabled():
            return

        now = time.time()

        # Only play one game at a time. If a session is active and not stale,
        # ignore every other game's buttons.
        if self._active_game is not None:
            if now - self._last_interaction > _SESSION_TIMEOUT:
                self._active_game = None
            elif self._active_game == "pending":
                # A gambling command was sent but we haven't seen its response
                # yet; find which game this message belongs to and start it.
                for game in list(_SIDE_CHOICES) + list(_CONTINUE_ACTIONS):
                    if await self._handle_game(message, game):
                        self._active_game = game
                        self._last_interaction = now
                        return
                return
            else:
                await self._handle_game(message, self._active_game)
                return

        # Start a session for the first game that has an actionable button.
        for game in list(_SIDE_CHOICES) + list(_CONTINUE_ACTIONS):
            if await self._handle_game(message, game):
                self._active_game = game
                self._last_interaction = now
                return

    async def _handle_game(self, message, game) -> bool:
        # Returns True if we clicked an action for this game.
        if not self._game_is_active(game):
            return False
        choices = _SIDE_CHOICES.get(game)
        if choices:
            for button in message.buttons:
                if button.label in choices and not button.disabled:
                    pick = self.bot.random.choice(choices)
                    target = next(
                        (b for b in message.buttons if b.label == pick and not b.disabled),
                        None,
                    )
                    if target is not None:
                        await self.bot.click_button(target)
                        self._last_interaction = time.time()
                        self.bot.log(
                            f"gambling - {game}: clicked {pick}", "green"
                        )
                        return True
            return False

        label = _CONTINUE_ACTIONS.get(game)
        if label:
            for button in message.buttons:
                if button.label == label and not button.disabled:
                    await self.bot.click_button(button)
                    self._last_interaction = time.time()
                    self.bot.log(
                        f"gambling - {game}: clicked '{label}'", "green"
                    )
                    return True
        return False

    async def log_messages(self, message):
        await self._handle(message)

    async def log_messages_edit(self, message):
        await self._handle(message)


async def setup(bot):
    await bot.add_cog(Gambling(bot))
