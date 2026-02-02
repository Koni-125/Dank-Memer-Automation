import asyncio
import time

from discord.ext import commands, tasks


commands_min_cd = {
    "hunt": 20,
    "beg": 40,
    "fish": 12,  # default
    "trivia": 10,
    "dep_all": 0,
    "dig": 20,
    "hl": 10,
    "crime": 40,
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
    cooldowns_list = list(commands_min_cd.values())

    if not cooldowns_list:
        # just in case
        return 1

    # Sort in ascending order
    cooldowns_list = sorted(cooldowns_list)
    result = find_least_gap(cooldowns_list)

    if result:
        return min(result["diff"], min(cooldowns_list))
    else:
        return cooldowns_list[0]


class Commands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.sleep_time = approximate_minimum_cooldown()

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
        if not self.bot.state:
            await asyncio.sleep(0.5)
            return

        shuffled_commands = list(self.bot.commands_dict)[:]
        self.bot.random.shuffle(shuffled_commands)

        for command in shuffled_commands:
            await asyncio.sleep(self.bot.random.uniform(0.5, 2))
            if not self.should_run(command):
                continue
            self.bot.last_ran[command] = time.time()
            if command == "dep_all":
                await self.bot.send_cmd(f"{self.bot.commands_dict[command]} all")
                continue
            if command == "fish":
                await self.bot.send_cmd(f"{self.bot.commands_dict[command]} catch")
                continue
            await self.bot.send_cmd(self.bot.commands_dict[command])
            continue

        await asyncio.sleep(self.sleep_time)


async def setup(bot):
    await bot.add_cog(Commands(bot))
