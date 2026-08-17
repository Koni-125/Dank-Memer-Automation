import asyncio
import time

import components_v2

from discord.ext import commands


class Misc(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self , message):
        if message.embeds:
            title = message.embeds[0].title
            if title and "Hold Tight!" in title:
                self.bot.log("Hold Tight detected: Waiting 30 seconds", "yellow")
                # Don't retry the command that caused this until it finishes.
                last_sent = self.bot.last_sent_command
                if last_sent:
                    for name, trigger in self.bot.commands_dict.items():
                        if last_sent.endswith(trigger) or trigger in last_sent:
                            self.bot.last_ran[name] = time.time()
                            break
                await self.bot.set_command_hold_stat(True)
                await asyncio.sleep(30)
                if self.bot.hold_command:
                    await self.bot.set_command_hold_stat(False)

        if message.embeds:
            title = message.embeds[0].title
            if title and "Verification Required" in title:
                await self.bot.set_command_hold_stat(True)
                self.bot.state = False
                self.bot.log("Verification Detected: Paused", "red")
                return

        # Enter giveaways shown by "pls giveaway view". These are normal
        # embed + v1 ActionRow buttons, so use dpy-self's native click.
        if message.embeds:
            desc = message.embeds[0].description or ""
            if "Author:" in desc and "Winners:" in desc:
                try:
                    for button in message.components[0].children:
                        if button.label == "Enter" and not button.disabled:
                            await button.click()
                            self.bot.log("giveaway - entered giveaway", "green")
                            return
                except (AttributeError, IndexError):
                    pass

async def setup(bot):
    await bot.add_cog(Misc(bot))
