import random
import asyncio, time

from discord.ext import commands


class Crime(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        pm_config = self.bot.settings_dict["commands"]["pm"]

        self.priority = pm_config["priority"]
        self.second_priority = pm_config["second_priority"]
        self.avoid = pm_config["avoid"]

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.channel.id != self.bot.channel.id:
            return

        if message.embeds:
            if message.embeds[0].title == f"{self.bot.user.name}'s Meme Posting Session":
                await self.bot.select(message, 0, 0, random.randint(0, 3))
                await asyncio.sleep(0.3)
                await self.bot.select(message, 1, 0, random.randint(0, 3))
                await asyncio.sleep(0.3)
                await message.components[2].children[0].click()
                self.bot.last_ran["pm"] = time.time()

                await asyncio.sleep(1)
                embed = message.embeds[0].to_dict()
                if "cannot post another meme for another 3 minutes" in embed["description"]:
                    self.bot.last_ran["pm"] += 185


async def setup(bot):
    await bot.add_cog(Crime(bot))
