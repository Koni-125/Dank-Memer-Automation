from components_v2.components import walker
from types import SimpleNamespace


class author:
    # The user who send the message.
    def __init__(self, data: dict):
        self.name = data.get("username")
        self.id = int(data.get("id", 0))


class emoji:
    # Emoji, likely to be inside `button`
    def __init__(self, data: dict):
        self.id = int(data.get("id", 0))
        self.name = data.get("name")


class message:
    # Message object
    def __init__(self, data: dict):
        self.author = author(data.get("author", {}))
        self.id = int(data.get("id", 0))
        self.flags = int(data.get("flags", 0))
        self.content = data.get("content", "")
        self.channel_id = int(data.get("channel_id", 0))
        self.channel = SimpleNamespace(id=self.channel_id)
        try:
            self.interaction_user_id = int(data["interaction_metadata"]["user"]["id"])
        except (KeyError, TypeError, ValueError):
            self.interaction_user_id = None
        self.components, self.buttons = walker(
            components=data.get("components", {}),
            message_details={
                "message_channel": self.channel_id,
                "message_id": self.id,
                "message_flag": self.flags,
                "message_author_id": self.author.id,
            },
        )


def get_message_obj(msg: str):
    return message(msg)


def is_message_for_user(message, user_id: int) -> bool:
    # True if the message has interaction_metadata and its user id matches user_id.
    if getattr(message, "interaction_user_id", None) is None:
        return False
    return message.interaction_user_id == user_id
