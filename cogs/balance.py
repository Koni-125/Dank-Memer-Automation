from discord.ext import commands
import re
import components_v2

def extract_net_worth(text):
    coins = re.search(r"Coin:\d+>\s*([\d,]+)", text)
    inventory = re.search(r"Backpack:\d+>\s*([\d,]+)", text)
    total = re.search(r"BankrobIcon:\d+>\s*([\d,]+)", text)

    return {
        "coins": int(coins.group(1).replace(",", "")) if coins else 0,
        "inventory": int(inventory.group(1).replace(",", "")) if inventory else 0,
        "net": int(total.group(1).replace(",", "")) if total else 0,
    }


class Balance(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.message_dispatcher.register(self.log_message)
        self.bot.message_dispatcher.register(self.log_messages_edit, edit=True)

    async def log_message(self, message):
        if message.channel_id != self.bot.channel.id:
            return

        if message.components:
            for component in message.components:
                if component.component_name != "section":
                    continue

                for cmp in component.components:
                    if cmp.component_name == "text_display":
                        if not f"### {self.bot.user.global_name}'s Balances".lower() in cmp.content.lower():
                            break
                        try:
                            await component.accessory.click(
                                self.bot.ws.session_id,
                                self.bot.local_headers,
                                str(self.bot.channel.guild.id)
                            )
                        except Exception:
                            pass
                        break

    async def log_messages_edit(self, message):
        if message.channel_id != self.bot.channel.id:
            return

        texts = components_v2.message.text_display_contents(message)
        if not any(
            f"### {self.bot.user.global_name}'s Net Worth".lower() in text.lower()
            for text in texts
        ):
            return
        # The header and the values live in separate text_displays.
        self.bot.worth.update(extract_net_worth("\n".join(texts)))

async def setup(bot):
    await bot.add_cog(Balance(bot))
