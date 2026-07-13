import emoji


def text_stats(text: str | None) -> tuple[int, int, int]:
    if not text:
        return (0, 0, 0)
    return (len(text), len(text.split()), emoji.emoji_count(text))


def list_emojis(text: str | None) -> list[str]:
    if not text:
        return []
    return [m["emoji"] for m in emoji.emoji_list(text)]
