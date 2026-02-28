import random
import asyncio
import time

from discord.ext import commands


class Pm(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.embeds:
            embed = message.embeds[0]
            if embed.author and f"{self.bot.user.global_name}'s Meme" in embed.author.name:
                self.bot.log("Attempting Postmeme", "yellow")
                await self.bot.set_command_hold_stat(True)
                await self.bot.select(message, 0, 0, random.randint(0, 3))
                await asyncio.sleep(0.3)
                await self.bot.select(message, 1, 0, random.randint(0, 3))
                await asyncio.sleep(0.3)
                await self.bot.click(message, 2 ,0)
                await self.bot.set_command_hold_stat(False)
                self.bot.last_ran["pm"] = time.time()

                await asyncio.sleep(1)

                if (
                    "You posted a dead meme, you cannot post another meme for another 2 minutes"
                    in embed.description
                ):
                    # 3m = 180s
                    self.bot.log("can't pm for 2 min", "red")
                    self.bot.last_ran["pm"] += 125
                


async def setup(bot):
    await bot.add_cog(Pm(bot))
