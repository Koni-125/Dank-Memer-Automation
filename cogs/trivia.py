import json
import os
import random
import re
import sys

from discord.ext import commands


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

    """async def log_messages(self, message):
        print(message.content, "from trivia")
        if message.channel_id == self.bot.channel_id:
            if message.components:
                for component in message.components:
                    """

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.embeds:
            desc = message.embeds[0].description
            if "seconds to answer" in desc:
                question = re.search(r"\*\*(.*?)\*\*", desc)[1]
                category = message.embeds[0].fields[1].value
                answer = trivia_dict[category].get(question, None)
                self.bot.log("Triva recieved", "yellow")
                if not answer:
                    child = self.bot.random.randint(0, 3)
                    message.components[0].children[child].click()
                    self.bot.log("Triva fail", "red")
                    return

                for count, i in enumerate(message.components[0].children):
                    if i.label == answer:
                        self.bot.log("Triva attempting success", "yellow")
                        if random.random() <= self.chance:
                            await i.click()
                            self.bot.log("Triva success", "green")
                        else:
                            self.bot.log("Triva attempting fail", "yellow")
                            message.components[0].children[
                                self.bot.random.choice([0, 1, 2, 3].pop(count))
                            ].click()
                            self.bot.log("Triva fail - intentional", "red")


async def setup(bot):
    await bot.add_cog(Trivia(bot))
