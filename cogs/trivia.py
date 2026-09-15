import json
import os
import random
import re
import sys

from discord.ext import commands

DANK_MEMER_ID = 270904126974590976


def resource_path(relative_path):
    if hasattr(sys, "_MEIPASS"):
        # noinspection PyProtectedMember
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)


with open(resource_path("resources/trivia.json")) as file:
    trivia_dict = json.load(file)


class Trivia(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # self.bot.message_dispatcher.register(self.log_messages)
        self.chance = self.bot.settings_dict["commands"]["trivia"][
            "trivia_correct_chance"
        ]

    @commands.Cog.listener()
    async def on_message(self, message):
        try:
            if message.channel.id != self.bot.channel.id:
                return
        except AttributeError:
            return
        if getattr(getattr(message, "author", None), "id", None) != DANK_MEMER_ID:
            return
        if not message.embeds:
            return
        desc = message.embeds[0].description or ""
        if "seconds to answer" not in desc:
            return
        match = re.search(r"\*\*(.*?)\*\*", desc)
        if not match:
            return
        question = match.group(1)
        try:
            category = message.embeds[0].fields[1].value
        except (IndexError, AttributeError):
            return
        answer = trivia_dict.get(category, {}).get(question, None)
        try:
            children = message.components[0].children
        except (IndexError, AttributeError, TypeError):
            return
        if not children:
            return
        if not answer:
            child = self.bot.random.randint(0, len(children) - 1)
            await self.bot.click(message, 0, child)
            self.bot.log("Triva fail", "red")
            return

        for count, i in enumerate(children):
            if i.label == answer:
                if random.random() <= self.chance:
                    await i.click()
                    self.bot.log("Triva success", "green")
                else:
                    choices = [c for c in range(len(children)) if c != count]
                    await self.bot.click(message, 0, self.bot.random.choice(choices))
                    self.bot.log("Triva fail - intentional", "red")


async def setup(bot):
    await bot.add_cog(Trivia(bot))
