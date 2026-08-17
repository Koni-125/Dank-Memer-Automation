import asyncio
import time

import components_v2

from discord.ext import commands


class Pets(commands.Cog):
    """Level-17 onboarding tasks (components_v2 responses).

      - "pets view":  /pets view -> Manage button (rename pet rock).
      - "pets care":  /pets care -> Hug button.
      - "pets rooms": /pets rooms -> view room.
    """

    def __init__(self, bot):
        self.bot = bot
        self.bot.message_dispatcher.register(self.log_messages)
        self.bot.message_dispatcher.register(self.log_messages_edit, edit=True)

    def _onboarding_active(self):
        onboarding = self.bot.get_cog("Onboarding")
        return onboarding is not None and onboarding.enabled()

    def _is_pending(self, key):
        onboarding = self.bot.get_cog("Onboarding")
        if onboarding is None:
            return False
        return key in onboarding.active_onboarding_tasks

    def _mark_done(self, key):
        onboarding = self.bot.get_cog("Onboarding")
        if onboarding is None:
            return
        onboarding.active_onboarding_tasks.discard(key)
        try:
            self.bot.settings_dict["commands"][key]["enabled"] = False
        except (KeyError, TypeError):
            pass
        self.bot.last_ran[key] = time.time()

    async def log_messages(self, message):
        await self._handle(message)

    async def log_messages_edit(self, message):
        await self._handle(message)

    async def _handle(self, message):
        if message.channel_id != self.bot.channel.id:
            return
        if not self._onboarding_active():
            return
        if self.bot.hold_command:
            return

        texts = components_v2.message.text_display_contents(message)
        joined = "\n".join(texts)

        # /pets view: click Manage (opens manage panel), then Rename opens a
        # modal to set the new name.
        if self._is_pending("pets view"):
            rename_btn = next(
                (
                    b
                    for b in message.buttons
                    if b.label == "Rename"
                    and not b.disabled
                    and "pets-view" in b.custom_id
                ),
                None,
            )
            if rename_btn is not None:
                await self.bot.set_command_hold_stat(True)
                try:
                    await self.bot.click_button(rename_btn)
                    self.bot.log("pets - clicked Rename, waiting for modal", "green")
                    modal = await self.bot.wait_for("modal", timeout=15)
                    modal.components[0].children[0].answer("Rocky")
                    await modal.submit()
                    self.bot.log("pets - submitted pet name", "green")
                    self._mark_done("pets view")
                except asyncio.TimeoutError:
                    self.bot.log("pets - rename modal timed out", "yellow")
                except Exception as e:
                    self.bot.log(f"pets - rename modal: {e}", "red")
                finally:
                    if self.bot.hold_command:
                        await self.bot.set_command_hold_stat(False)
                return
            manage_btn = next(
                (
                    b
                    for b in message.buttons
                    if b.label == "Manage"
                    and not b.disabled
                    and "pets-view" in b.custom_id
                ),
                None,
            )
            if manage_btn is not None:
                await self.bot.click_button(manage_btn)
                self.bot.log("pets - clicked Manage (opens panel)", "green")
                return

        # /pets care: click Hug.
        if self._is_pending("pets care"):
            for btn in message.buttons:
                if (
                    btn.label == "Hug"
                    and not btn.disabled
                    and "pets-care" in btn.custom_id
                ):
                    await self.bot.click_button(btn)
                    self.bot.log("pets - hugged pet rock", "green")
                    self._mark_done("pets care")
                    return

        # /pets rooms: viewing is enough.
        if self._is_pending("pets rooms"):
            if any("Room #" in t for t in texts):
                self.bot.log("pets - viewed pet room", "green")
                self._mark_done("pets rooms")


async def setup(bot):
    await bot.add_cog(Pets(bot))
