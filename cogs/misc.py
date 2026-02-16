import discord
import asyncio
from discord.ext import commands


class Misc(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self , message):
        if message.channel.id != int(self.bot.channel_id):
            return

        if message.embeds:
            title = message.embeds[0].title
            if "Hold Tight!" in title:
                await self.bot.set_command_hold_stat(True)
                self.bot.log(f"Hold Tight detected: Waiting 15 seconds", "yellow")
                await asyncio.sleep(15)
                if self.bot.hold_command:
                    await self.bot.set_command_hold_stat(False)
    
        if message.embeds:
            title = message.embeds[0].title
            if "Verification Required" in title:
                await self.bot.set_command_hold_stat(True)
                self.bot.state = False
                self.bot.log("Verification Detected: Paused", "red")
                return

async def setup(bot):
    await bot.add_cog(Misc(bot))
