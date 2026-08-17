import asyncio
import re

import components_v2

from discord.ext import commands


class Craft(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Item to craft (from the current onboarding objective).
        self.target_item = "bean seed"
        self._selected = False
        self.bot.message_dispatcher.register(self.log_messages)
        self.bot.message_dispatcher.register(self.log_farm)
        self.bot.message_dispatcher.register(self.log_messages_edit, edit=True)

    async def log_messages(self, message):
        if message.channel_id != self.bot.channel.id:
            return

        texts = components_v2.message.text_display_contents(message)
        if not any("Crafting Bench" in t for t in texts):
            return

        if not self._selected:
            for comp in message.components:
                if comp.component_name != "select_menu":
                    continue
                for opt in comp.options:
                    if self.target_item.lower() in (opt.label or "").lower():
                        await comp.select(
                            [opt.value],
                            self.bot.ws.session_id,
                            self.bot.local_headers,
                            str(self.bot.channel.guild.id),
                        )
                        self.bot.log(f"craft - selected '{opt.label}'", "yellow")
                        self._selected = True
                        return
            self.bot.log(f"craft - '{self.target_item}' not in recipe menu", "red")
            return

        self._try_craft(message)

    async def log_messages_edit(self, message):
        if message.channel_id != self.bot.channel.id:
            return

        if not self._selected:
            return
        if any(
            "Crafting Bench" in t
            for t in components_v2.message.text_display_contents(message)
        ):
            self._try_craft(message)

    def _try_craft(self, message):
        # Click "Craft N" when the recipe is shown and craftable.
        for btn in message.buttons:
            if btn.label and re.match(r"^Craft \d+$", btn.label) and not btn.disabled:
                asyncio.create_task(self._do_craft(btn))
                return

        # Otherwise just log the missing materials (no auto-buy).
        texts = components_v2.message.text_display_contents(message)
        recipe = "\n".join(texts)
        for match in re.finditer(
            r"([A-Za-z ]+?)\s*-\s*(\d+)\s*\n\s*-#?\s*You have\s*(\d+)", recipe
        ):
            name, need, have = (
                match.group(1).strip(),
                int(match.group(2)),
                int(match.group(3)),
            )
            if have < need:
                self.bot.log(
                    f"craft - need {need - have} more {name} (have {have}/{need})",
                    "yellow",
                )

    async def _do_craft(self, btn):
        await self.bot.click_button(btn)
        self.bot.log(f"craft - started: {btn.label}", "green")
        self._selected = False

    async def log_farm(self, message):
        # Plant/harvest on the farm view (components_v2).
        texts = components_v2.message.text_display_contents(message)
        if not any("Farm" in t for t in texts):
            return
        for btn in message.buttons:
            label = btn.label or ""
            if label in ("Plant", "Harvest", "Plant Seed") and not btn.disabled:
                await self.bot.click_button(btn)
                self.bot.log(f"farm - {label}", "green")
                return


async def setup(bot):
    await bot.add_cog(Craft(bot))
