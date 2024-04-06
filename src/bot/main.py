import inspect
import os
import sys

import telegram.ext
from telegram.ext import ApplicationBuilder, filters

import bot
from bot.logger import create_logger


def get_bot_token_or_die(env_variable: str = "BOT_TOKEN"):
    logger = create_logger(inspect.currentframe().f_code.co_name)
    if token := os.getenv(env_variable):
        return token

    logger.error(f"failed to retrieve token from environment (`{env_variable}`)")
    sys.exit(1)


def main():
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
    set_timestamp_handler = telegram.ext.CommandHandler("set_timestamp", bot.set_timestamp)
    application.add_handler(set_timestamp_handler)
    stations_handler = telegram.ext.CommandHandler("stations", bot.stations)
    application.add_handler(stations_handler)

    application.run_polling()


if __name__ == "__main__":
    main()
