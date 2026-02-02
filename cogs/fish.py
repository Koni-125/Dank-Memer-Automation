import time
import asyncio

from discord.ext import commands


class Fish(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.message_dispatcher.register(self.log_messages)
        self.simple_fishing = self.bot.settings_dict["commands"]["fish"][
            "simpleFishing"
        ]

    async def log_messages(self, message):
        if message.channel_id != self.bot.channel.id:
            return

        if self.simple_fishing:
            if message.components:
                for component in message.components:
                    """Current Location"""
                    if (
                        component.component_name == "text_display"
                        and "Current Location" in component.content
                    ):
                        # We are not on simple fishing, need to switch back.abs
                        # Task : Hold control.
                        self.bot.log("fish - simple mode detected", "yellow")
                        await self.bot.set_command_hold_stat(True)
                        await self.bot.send_cmd("fish settings")
                        self.bot.last_ran["fish"] = time.time()
                    else:
                        self.bot.log(component.component_name, "yellow")

                    """if component.component_name == "select_menu":
                        if "fish-settings" in component.custom_id:
                            # Fish settings component, we will check if simple fishing is enabled.abs"""

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.channel.id != self.bot.channel.id:
            return

        if message.embeds:
            embed = message.embeds[0]
            if "Auto-Sell Trash" in embed.title:
                await asyncio.sleep(self.bot.random.uniform(0.3, 0.5))
                select_menu = message.components[0].children[0]
                await select_menu.choose(select_menu.options[9])
                self.bot.log("fish - choose simple fish option", "yellow")

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if before.channel.id != self.bot.channel.id:
            return

        if after.embeds:
            embed = after.embeds[0]
            if "Simple Fishing" in embed.title:
                self.bot.log("fish - btn reached", "yellow")
                await asyncio.sleep(self.bot.random.uniform(0.3, 0.5))
                btn = after.components[1].children[1]
                if btn and not btn.disabled:
                    await btn.click()

                self.bot.log("fish - btn", "yellow")
                await self.bot.set_command_hold_stat(False)


async def setup(bot):
    await bot.add_cog(Fish(bot))
