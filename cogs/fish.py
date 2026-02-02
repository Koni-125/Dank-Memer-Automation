import time
import asyncio
import re

from discord.ext import commands


def shadow_position(text: str):
    """
    Returns column and row from `text` string.
    Dankmemer has colomn:row as suffix for custom_id for fishing buttons
    """
    match = re.search(r"shadow:\s*([a-z]+)\s+([a-z]+)", text, re.IGNORECASE)
    if not match:
        return None

    row_word, col_word = match.group(1).lower(), match.group(2).lower()

    row_map = {"top": 0, "middle": 1, "bottom": 2}

    col_map = {"left": 0, "middle": 1, "right": 2}

    if row_word not in row_map or col_word not in col_map:
        return None

    return col_map[col_word], row_map[row_word]


def fetch_desc(components):
    for item in components:
        if item.component_name == "media_gallery":
            return item.items[0].description


class Fish(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.message_dispatcher.register(self.log_messages)
        self.bot.message_dispatcher.register(self.log_messages_edit, edit=True)
        self.simple_fishing = self.bot.settings_dict["commands"]["fish"][
            "simpleFishing"
        ]

    async def log_messages(self, message):
        if message.channel_id != self.bot.channel.id:
            return

        if message.components:
            for component in message.components:
                """Current Location"""
                if component.component_name == "text_display":
                    if "Current Location" in component.content:
                        if self.simple_fishing:
                            # We are not on simple fishing, need to switch back simple fishing
                            self.bot.last_ran["fish"] = (
                                time.time() + 12
                            )  # ensure command not reran
                            await asyncio.sleep(self.bot.random.uniform(12, 13))
                            self.bot.log(
                                "fishing - attempting to switching back to simple mode",
                                "yellow",
                            )
                            await self.bot.set_command_hold_stat(True)
                            self.bot.last_ran["fish"] = time.time()
                            await self.bot.send_cmd("fish settings")
                        else:
                            # Click fish catch button
                            for btn in message.buttons:
                                if btn.label == "Go Fishing":
                                    self.bot.log(
                                        "fishing - clicking go fishing btn", "yellow"
                                    )
                                    await asyncio.sleep(
                                        self.bot.random.uniform(0.3, 0.5)
                                    )
                                    stat = await btn.click(
                                        self.bot.ws.session_id,
                                        self.bot.local_headers,
                                        str(self.bot.channel.guild.id),
                                    )
                                    if stat:
                                        self.bot.log(
                                            "fishing - clicked go fishing btn", "yellow"
                                        )
                                    else:
                                        self.bot.log(
                                            "fishing - clicking go fish failed", "red"
                                        )

                    elif "Simple fishing mode" in component.content:
                        if not self.simple_fishing:
                            # We are on simple fishing, need to switch back main
                            self.bot.last_ran["fish"] = (
                                time.time() + 12
                            )  # ensure command not reran
                            await asyncio.sleep(self.bot.random.uniform(12, 13))
                            self.bot.log(
                                "fishing - attempting to switching back to normal mode",
                                "yellow",
                            )
                            await self.bot.set_command_hold_stat(True)
                            self.bot.last_ran["fish"] = time.time()
                            await self.bot.send_cmd("fish settings")

                    elif "Are you sure you want to sell this fish" in component.content:
                        for btn in message.buttons:
                            if btn.label == "Confirm":
                                await asyncio.sleep(self.bot.random.uniform(0.3, 0.5))
                                stat = await btn.click(
                                    self.bot.ws.session_id,
                                    self.bot.local_headers,
                                    str(self.bot.channel.guild.id),
                                )
                                if stat:
                                    self.bot.log("fishing - sold fish", "green")
                                else:
                                    self.bot.log(
                                        "fishing - failed to sell fish", "green"
                                    )

    async def log_messages_edit(self, message):
        if message.channel_id != self.bot.channel.id:
            return

        if message.components:
            for component in message.components:
                if component.component_name == "text_display":
                    if component.content == "### Fishing...":
                        self.bot.log("fishing - attempting to catch fish", "yellow")
                        # Main fishing area (normal)
                        desc = fetch_desc(message.components)
                        col, row = shadow_position(desc)
                        # Click button:
                        for btn in message.buttons:
                            # Check last 3 chars match column row combo
                            if f"{col}:{row}" == btn.custom_id[-3:]:
                                await asyncio.sleep(self.bot.random.uniform(0.3, 0.5))
                                stat = await btn.click(
                                    self.bot.ws.session_id,
                                    self.bot.local_headers,
                                    str(self.bot.channel.guild.id),
                                )
                                if stat:
                                    self.bot.log("fishing - caught fish!", "green")
                                else:
                                    self.bot.log("fishing - caught fish?", "red")

                elif component.component_name == "section":
                    if "### You caught a" in component.components[0].content:
                        sell_settings = self.bot.settings_dict["commands"]["fish"][
                            "sell"
                        ]
                        if sell_settings["enabled"]:
                            btn_emoji_name = (
                                "FishToken" if not sell_settings["asCash"] else "Coin"
                            )
                            for btn in message.buttons:
                                if btn.emoji and btn.emoji.name == btn_emoji_name:
                                    await asyncio.sleep(
                                        self.bot.random.uniform(0.3, 0.5)
                                    )
                                    await btn.click(
                                        self.bot.ws.session_id,
                                        self.bot.local_headers,
                                        str(self.bot.channel.guild.id),
                                    )

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
                await asyncio.sleep(self.bot.random.uniform(0.3, 0.5))
                btn = after.components[1].children[1 if self.simple_fishing else 0]
                if btn and not btn.disabled:
                    await btn.click()

                await self.bot.set_command_hold_stat(False)


async def setup(bot):
    await bot.add_cog(Fish(bot))
