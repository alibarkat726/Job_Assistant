import tiktoken

encoding = tiktoken.get_encoding('cl100k_base')


def count_tokens(text: str) -> int:
    # User text resembling special tokens is still ordinary data.
    return len(encoding.encode(text, disallowed_special=()))


def truncate_tokens(text: str, budget: int) -> str:
    return encoding.decode(encoding.encode(text, disallowed_special=())[:budget])
