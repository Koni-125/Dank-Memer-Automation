import random
import asyncio
import time

from discord.ext import commands

DANK_MEMER_ID = 270904126974590976


class Pm(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        if not message.embeds:
            return
        embed = message.embeds[0]
        author_name = embed.author.name if embed.author else ""
        if f"{self.bot.user.global_name}'s Meme" not in (author_name or ""):
            return
        self.bot.log("Attempting Postmeme", "yellow")
        await self.bot.set_command_hold_stat(True)
        try:
            await self.bot.select(message, 0, 0, random.randint(0, 3))
            await asyncio.sleep(0.3)
            await self.bot.select(message, 1, 0, random.randint(0, 3))
            await asyncio.sleep(0.3)
            await self.bot.click(message, 2, 0)
            self.bot.last_ran["pm"] = time.time()
        finally:
            if self.bot.hold_command:
                await self.bot.set_command_hold_stat(False)

        # The dead-meme cooldown arrives in Dank Memer's follow-up
        # response, not the picker embed above -- wait for it here.
        def _dead_meme(msg):
            try:
                if msg.author.id != DANK_MEMER_ID:
                    return False
                if msg.channel.id != self.bot.channel.id:
                    return False
            except AttributeError:
                return False
            try:
                desc = msg.embeds[0].description or ""
            except (IndexError, AttributeError):
                return False
            return "You posted a dead meme" in desc

        try:
            await self.bot.wait_for("message", check=_dead_meme, timeout=20)
        except asyncio.TimeoutError:
            return
        # Dead meme: can't post for ~2 minutes (+5s buffer).
        self.bot.log("can't pm for 2 min", "red")
        self.bot.last_ran["pm"] = time.time() + 125



async def setup(bot):
    await bot.add_cog(Pm(bot))
