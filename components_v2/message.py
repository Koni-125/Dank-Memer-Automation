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
        self.reference = self._parse_reference(data.get("message_reference"))
        self.referenced_message = (
            SimpleNamespace(
                id=int(data["referenced_message"].get("id", 0) or 0),
                content=data["referenced_message"].get("content", ""),
                author=author(data["referenced_message"].get("author", {})),
            )
            if data.get("referenced_message")
            else None
        )
        self.components, self.buttons = walker(
            components=data.get("components", {}),
            message_details={
                "message_channel": self.channel_id,
                "message_id": self.id,
                "message_flag": self.flags,
                "message_author_id": self.author.id,
            },
        )
        # Some responses (e.g. stream "Run AD") arrive as components_v1
        # embeds, so expose them for dispatcher handlers to read.
        self.embeds = []
        for embed_data in data.get("embeds", []) or []:
            self.embeds.append(
                SimpleNamespace(
                    title=embed_data.get("title") or "",
                    description=embed_data.get("description") or "",
                )
            )

    @staticmethod
    def _parse_reference(data):
        if not data:
            return None
        ref = SimpleNamespace(
            message_id=int(data.get("message_id", 0)),
            channel_id=int(data.get("channel_id", 0)),
            guild_id=data.get("guild_id"),
            resolved=None,
        )
        if not data.get("message_id"):
            return ref
        # `author_id` is often absent from the raw `message_reference`, so the
        # resolved message author comes from `referenced_message` when present.
        ref.resolved = SimpleNamespace(
            id=ref.message_id,
            author=SimpleNamespace(id=int(data.get("author_id", 0) or 0)),
        )
        return ref


def get_message_obj(msg: str):
    return message(msg)


def text_display_contents(message) -> list:
    """All text_display contents recursively (sections nest their own)."""
    results = []

    def walk(component):
        if component.component_name == "text_display":
            results.append(component.content or "")
        if component.component_name == "section":
            for child in component.components:
                walk(child)

    for component in getattr(message, "components", []) or []:
        walk(component)
    return results


def is_message_for_user(message, user_id: int) -> bool:
    # Accept messages that are part of an interaction with the user, sent by the
    # user, or direct replies to one of the user's own messages. Dank Memer's
    # responses to text commands don't always carry interaction metadata.
    if getattr(message, "interaction_user_id", None) == user_id:
        return True

    if getattr(message, "author", None) is not None and message.author.id == user_id:
        return True

    if getattr(message, "reference", None) is not None:
        resolved = getattr(message.reference, "resolved", None)
        if resolved is not None and getattr(resolved, "author", None) is not None:
            if resolved.author.id == user_id:
                return True

    referenced = getattr(message, "referenced_message", None)
    if referenced is not None and getattr(referenced, "author", None) is not None:
        if referenced.author.id == user_id:
            return True

    return False
