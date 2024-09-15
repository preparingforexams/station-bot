import dataclasses
import time
from abc import abstractmethod
from enum import Enum
from typing import List

import telegram.constants
from telegram import Update


class MessageType(Enum):
    Text = "text"
    Photo = "photo"


class Message:
    type: MessageType
    parse_mode: telegram.constants.ParseMode = telegram.constants.ParseMode.MARKDOWN_V2

    @abstractmethod
    async def send(self, update: Update):
        raise NotImplementedError("subclasses of `Message` must imlpement `send`")


@dataclasses.dataclass
class TextMessage(Message):
    async def send(self, update: Update):
        effective_message = update.effective_message
        if effective_message is None:
            raise ValueError("Unexpected non-message update")

        messages = self.split()
        first = True
        for message in messages:
            await effective_message.reply_text(
                message, parse_mode=self.parse_mode, disable_notification=not first
            )
            first = False
            time.sleep(1)

    type = MessageType.Text
    text: str
    split_by = "\n"
    join_with = "\n"

    def split(self) -> list[str]:
        message_length = 4096
        messages: list[list[str]] = []
        current_message_length = 0
        current_message_index = 0
        join_by_length = len(self.join_with)
        lines = self.text.split(self.split_by)

        line_index = 0
        while line_index < len(lines):
            line = lines[line_index]
            if len(messages) <= current_message_index:
                messages.append([])

            line_length = len(line)
            if (
                current_message_length
                + line_length
                + (len(messages[current_message_index]) * join_by_length)
                < message_length
            ):
                current_message_length += line_length
                messages[current_message_index].append(line)
                line_index += 1
            else:
                current_message_length = 0
                current_message_index += 1

        return [self.join_with.join(entry) for entry in messages]


@dataclasses.dataclass
class PhotoMessage(Message):
    type = MessageType.Photo
    url: str
    caption: str = ""

    async def send(self, update: Update):
        effective_message = update.effective_message
        if effective_message is None:
            raise ValueError("Unexpected non-message update")

        await effective_message.reply_photo(
            self.url,
            caption=self.caption[:1024],
            parse_mode=self.parse_mode,
        )
