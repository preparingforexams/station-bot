import asyncio
import logging
import os
import signal
import sys

import telegram.ext
import uvloop
from telegram.ext import ApplicationBuilder, filters

import bot

_logger = logging.getLogger(__name__)


def _setup_logging():
    logging.basicConfig()
    _logger.level = logging.DEBUG


def get_bot_token_or_die(env_variable: str = "TELEGRAM_TOKEN"):
    if token := os.getenv(env_variable):
        return token

    _logger.error("failed to retrieve token from environment (%s)", env_variable)
    sys.exit(1)


def main():
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    _setup_logging()

    bot_token = get_bot_token_or_die()
    application = ApplicationBuilder().token(bot_token).build()

    station_handler = telegram.ext.CommandHandler("station", bot.station)
    application.add_handler(station_handler)

    done_handler = telegram.ext.MessageHandler(filters.PHOTO, bot.done)
    application.add_handler(done_handler)
    done_handler = telegram.ext.CommandHandler("done", bot.done)
    application.add_handler(done_handler)
    progress_handler = telegram.ext.CommandHandler("progress", bot.progress)
    application.add_handler(progress_handler)
    set_timestamp_handler = telegram.ext.CommandHandler(
        "set_timestamp", bot.set_timestamp
    )
    application.add_handler(set_timestamp_handler)
    stations_handler = telegram.ext.CommandHandler("stations", bot.stations)
    application.add_handler(stations_handler)

    application.run_polling(
        stop_signals=[
            signal.SIGINT,
            signal.SIGTERM,
        ]
    )


if __name__ == "__main__":
    main()
