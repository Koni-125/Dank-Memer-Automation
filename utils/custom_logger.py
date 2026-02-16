import aiohttp
import datetime

class CustomLogger:
    def __init__(self, webhook_url=None,file_name=None ,log_to_file=False, log_to_discord=False):
        self.webhook_url = webhook_url
        self.file_enabled = log_to_file
        self.discord_enabled = log_to_discord
        self.filename = file_name

        self.colors = {
            "DEBUG": "\033[95m",    # Purple
            "INFO": "\033[94m",     # Blue
            "SUCCESS": "\033[92m",  # Green
            "WARN": "\033[93m",     # Yellow
            "ERROR": "\033[91m",    # Red
            "CRITICAL": "\033[41m", # Red Background
            "RESET": "\033[0m"
        }

        # Hex colors for Discord embeds
        self.discord_colors = {
            "DEBUG": 9807270,    # Grey
            "INFO": 3447003,     # Blue
            "SUCCESS": 3066993,  # Green
            "WARN": 16776960,    # Yellow
            "ERROR": 15158332,   # Red
            "CRITICAL": 10038562 # Dark Red
        }

    def _get_timestamp(self):
        return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _write_to_file(self, level, message):
        try:
            with open(self.filename, "a", encoding="utf-8") as f:
                f.write(f"[{self._get_timestamp()}] {level.ljust(8)} | {message}\n")
        except Exception as e:
            print(f"File Logging Error: {e}")

    async def _send_discord(self, level, message):
        if not self.webhook_url: return

        payload = {
            "embeds": [{
                "title": f"Priority: {level}",
                "description": message,
                "color": self.discord_colors.get(level, 0),
                "footer": {"text": f"System Time: {self._get_timestamp()}"}
            }]
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.webhook_url, json=payload) as resp:
                    pass 
        except:
            pass 

    async def log(self, level, message):
        level = level.upper()
        ts = self._get_timestamp()
        
        color = self.colors.get(level, self.colors["RESET"])
        reset = self.colors["RESET"]
        print(f"[{ts}] {color}{level.ljust(8)}{reset} | {message}")

        if self.file_enabled:
            self._write_to_file(level, message)

        if self.discord_enabled and level != "DEBUG":
            await self._send_discord(level, message)
