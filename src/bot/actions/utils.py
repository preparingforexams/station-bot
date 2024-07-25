def escape_markdown(text: str) -> str:
    reserved_characters = [
        "_",
        "*",
        "[",
        "]",
        "(",
        ")",
        "~",
        "`",
        ">",
        "#",
        "+",
        "-",
        "=",
        "|",
        "{",
        "}",
        ".",
        "!",
    ]
    for reserved in reserved_characters:
        text = text.replace(reserved, rf"\{reserved}")

    return text
