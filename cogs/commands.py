import asyncio
import time

import components_v2

from discord.ext import commands, tasks

commands_min_cd = {
    # Edit this and add `minimum cooldown` of items as we add new commands
    "hunt": 20,
    "beg": 40,
    "fish": 12,  # default
    "trivia": 10,
    "dep_all": 0,
    "dig": 20,
    "hl": 10,
    "crime": 40,
    "search": 25,
    "tidy": 20,
    "pm": 20,
    "adventure": 60*30,
    "daily": 3600*12,
    "bal": 60,
    "work": 60*30,
    "stream": 60*10,
    "pet": 60*30,
    "scratch": 60*60*3,
}


def find_least_gap(list_to_check):
    if len(list_to_check) < 2:
        return None

    final_result = {
        "min": list_to_check[0],
        "max": list_to_check[1],
        "diff": abs(list_to_check[1] - list_to_check[0]),
    }

    for i in range(len(list_to_check) - 1):
        curr = list_to_check[i]
        next_item = list_to_check[i + 1]
        diff = abs(next_item - curr)

        if diff < final_result["diff"]:
            final_result["min"] = curr
            final_result["max"] = next_item
            final_result["diff"] = diff if diff > 0 else 1

    return final_result


def approximate_minimum_cooldown():
    # A 0 value means "no cooldown" (e.g. deposit) and must not drag the
    # computed resting period down to 0, or the command loop will never sleep
    # between cycles and commands will overlap (triggering Dank Memer's
    # "Hold Tight" response).
    cooldowns_list = sorted(
        cd for cd in commands_min_cd.values() if cd > 0
    )

    if not cooldowns_list:
        # just in case
        return 1

    result = find_least_gap(cooldowns_list)

    if result:
        return max(min(result["diff"], cooldowns_list[0]), 1)
    else:
        return max(cooldowns_list[0], 1)


class Commands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.sleep_time = approximate_minimum_cooldown()
        self.minCommandCD = self.bot.settings_dict["settings"]["cooldowns"]["minCommandDelay"]
        self.maxCommandCD = self.bot.settings_dict["settings"]["cooldowns"]["maxCommandDelay"]
        self.breaks_enabled = self.bot.settings_dict["settings"].get("breaks", False)
        self.min_break_cd = self.bot.settings_dict["settings"]["cooldowns"].get("minBreakCooldown", 3600)
        self.max_break_cd = self.bot.settings_dict["settings"]["cooldowns"].get("maxBreakCooldown", 10800)
        self.min_break_dur = self.bot.settings_dict["settings"]["cooldowns"].get("minBreakDuration", 1800)
        self.max_break_dur = self.bot.settings_dict["settings"]["cooldowns"].get("maxBreakDuration", 18000)
        self.next_break_at = time.time() + self.bot.random.uniform(self.min_break_cd, self.max_break_cd)
        self.bot.message_dispatcher.register(self.log_messages)

    def onboarding_mode(self):
        try:
            return bool(
                self.bot.settings_dict["settings"]["onboarding"]["enabled"]
            )
        except (KeyError, TypeError):
            return False

    async def maybe_take_break(self):
        if not self.breaks_enabled:
            return
        if time.time() < self.next_break_at:
            return
        duration = self.bot.random.uniform(self.min_break_dur, self.max_break_dur)
        self.bot.log(f"taking a break for {int(duration // 60)}m...", "yellow")
        await asyncio.sleep(duration)
        self.bot.log("break over, resuming commands", "green")
        self.next_break_at = time.time() + self.bot.random.uniform(
            self.min_break_cd, self.max_break_cd
        )

    async def log_messages(self, message):
        if message.channel_id != self.bot.channel.id:
            return

        texts = components_v2.message.text_display_contents(message)

        # Onboarding mode is driven by the Onboarding cog. If a locked
        # ("not unlocked yet") message arrives while we're running, hand
        # control over to it by enabling onboarding mode; its loop takes over
        # and ours pauses at the top of commands_handler.
        if any(
            "You have not unlocked this feature yet!" in text for text in texts
        ):
            onboarding = self.bot.get_cog("Onboarding")
            if onboarding is not None:
                onboarding._set_enabled(True)
            return

        if any(
            "You already have a command in progress" in text
            or "Too spicy" in text
            for text in texts
        ):
            self._backoff(message)

    def _backoff(self, message):
        # Previous command still running, or a rate-limit/cooldown notice.
        replied = ""
        if message.referenced_message is not None:
            replied = message.referenced_message.content or ""
        command = self._find_command(replied)
        if command is None:
            return
        # Don't retry this command until its cooldown elapses.
        backoff = self.get_cooldown(command)
        self.bot.last_ran[command] = time.time() + max(backoff, 30)
        self.bot.log(
            f"'{command}' not ready yet (command in progress / cooldown). "
            f"Backing off ~{max(backoff, 30)}s.",
            "yellow",
        )

    def _find_command(self, content):
        for name, trigger in self.bot.commands_dict.items():
            if content and f"pls {trigger}" in content:
                return name
        return None

    async def cog_load(self):
        print(f"starting..., approx min {self.sleep_time}")
        self.commands_handler.start()

    def get_cooldown(self, command_name):
        # User may sometimes put cooldown below minimum cooldowns,
        # Guard against that.
        cd = self.bot.settings_dict["commands"][command_name]["delay"]
        min_cd = commands_min_cd[command_name]
        return cd if cd >= min_cd else min_cd

    def should_run(self, command_name):
        # Checks whether a command must be ran.
        if (
            not self.bot.settings_dict["commands"][command_name]["enabled"]
            or not self.bot.state
        ):
            return False

        if self.bot.hold_command:
            return False

        cd = self.get_cooldown(command_name)

        if time.time() - self.bot.last_ran[command_name] < cd:
            return False
        return True

    @tasks.loop()
    async def commands_handler(self):
        try:
            if not self.bot.state:
                await asyncio.sleep(0.5)
                return

            # Onboarding mode is active: the Onboarding cog is running the
            # account through the onboarding levels, so this loop must NOT
            # run. Pause here and only resume once onboarding completes.
            if self.onboarding_mode():
                await asyncio.sleep(1)
                return

            await self.maybe_take_break()

            shuffled_commands = list(self.bot.commands_dict)[:]
            self.bot.random.shuffle(shuffled_commands)

            for command in shuffled_commands:
                await asyncio.sleep(self.bot.random.uniform(self.minCommandCD, self.maxCommandCD))
                if not self.should_run(command):
                    continue
                self.bot.last_ran[command] = time.time()
                try:
                    if command == "dep_all":
                        await self.bot.send_cmd(f"{self.bot.commands_dict[command]} all")
                        continue
                    if command == "fish":
                        await self.bot.send_cmd(f"{self.bot.commands_dict[command]} catch")
                        continue
                    await self.bot.send_cmd(self.bot.commands_dict[command])
                except Exception as e:
                    self.bot.log(f"Failed to run '{command}': {e}", "red")
                    continue

            await asyncio.sleep(self.sleep_time)
        except Exception as e:
            self.bot.log(f"commands_handler error: {e}", "red")
            await asyncio.sleep(5)


async def setup(bot):
    await bot.add_cog(Commands(bot))
