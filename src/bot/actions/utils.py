import inspect
import socket

import requests as requests
import urllib3 as urllib3

from bot.logger import create_logger_with_frame


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


class RequestError(Exception):
    pass


def get_json_from_url(url: str, *, headers: dict | None = None) -> dict | None:
    log = create_logger_with_frame(inspect.currentframe(), __name__)

    try:
        response = requests.get(url, headers=headers)
        content = response.json()
    except (
        requests.exceptions.ConnectionError,
        socket.gaierror,
        urllib3.exceptions.MaxRetryError,
    ) as e:
        log.exception("failed to communicate with jokes api")
        raise RequestError(e)

    if not response.ok:
        raise RequestError(f"[{response.status_code}]{response.text}")

    return content
