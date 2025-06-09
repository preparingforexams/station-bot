import logging
import random
import signal
from collections.abc import Iterable
from datetime import datetime
from io import StringIO
from typing import Any
from zoneinfo import ZoneInfo

from bs_state import StateStorage
from pydantic import HttpUrl
from rapidfuzz import process
from rapidfuzz.utils_py import default_process
from telegram import LinkPreviewOptions, Update
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from bot import legacy_state, wiki
from bot.config import Config
from bot.imported_stations import IMPORTED_STATIONS
from bot.model import Station
from bot.state import StateStorageFactory, StationState

_logger = logging.getLogger(__name__)


DATE_FORMAT = "%d.%m.%Y"


class FuzzyMatchingException(Exception):
    def __init__(self, closest_match: str, match_ratio: float) -> None:
        self.closest_match = closest_match
        self.match_ratio = match_ratio

        super().__init__(
            f"No match found, closest match: {closest_match} ({round(match_ratio * 100)}%)",
        )


class StationBot:
    def __init__(
        self,
        *,
        state_storage_factory: StateStorageFactory,
    ) -> None:
        self._state_storage_factory = state_storage_factory
        self._state_storage: StateStorage[StationState] = None  # type: ignore[assignment]

    async def __post_init(self, _) -> None:
        _logger.info("Initializing...")
        self._state_storage = await self._state_storage_factory(StationState.empty())

        _logger.info("Trying to update stations from Wikipedia")
        stations = await wiki.get_wiki_stations()
        if stations is None:
            _logger.warning("Could not retrieve stations")
            return

        state = await self._state_storage.load()
        new_state = state.update_stations(IMPORTED_STATIONS).update_stations(stations)
        await self._state_storage.store(new_state)

        await self.__restore_legacy_state(new_state)

    async def __restore_legacy_state(self, state: StationState) -> None:
        _logger.info("Trying to restore done timestamps from legacy state")
        restored_state = await legacy_state.read_legacy_state()
        if restored_state:
            _logger.info("Found legacy state: %s", restored_state)
            restored_stations: list[dict[str, Any]] = restored_state.get("stations", [])

            for restored_station in restored_stations:
                name = restored_station["name"]
                done_timestamp = restored_station.get("done_timestamp")
                if not done_timestamp:
                    _logger.info("No done time for station %s", name)
                    continue

                matching_station: Station | None = None
                for station in state.stations:
                    if station.name == name:
                        matching_station = station
                        break

                if matching_station is None:
                    _logger.error("Could not find station for legacy station %s", name)
                    continue

                done_datetime = datetime.fromtimestamp(
                    done_timestamp,
                    tz=ZoneInfo("Europe/Berlin"),
                )
                _logger.info("Found done time for station %s", name)
                state = state.mark_as_done(matching_station, done_datetime.date())

            _logger.info("Saving restored state")
            await self._state_storage.store(state)

    async def __post_shutdown(self, _) -> None:
        _logger.info("Shutting down...")
        await self._state_storage.close()

        _logger.info("Shutdown complete.")

    @classmethod
    def run(cls, config: Config, state_storage_factory: StateStorageFactory) -> None:
        bot = cls(
            state_storage_factory=state_storage_factory,
        )

        app = (
            ApplicationBuilder()
            .token(config.telegram_token)
            .post_init(bot.__post_init)
            .post_shutdown(bot.__post_shutdown)
            .build()
        )

        app.add_handler(
            CommandHandler(
                "done",
                bot._command_done,
                filters=~filters.UpdateType.EDITED_MESSAGE,
            )
        )
        app.add_handler(
            MessageHandler(
                filters.PHOTO,
                bot._command_done,
            )
        )
        app.add_handler(
            CommandHandler(
                "progress",
                bot._command_progress,
                filters=~filters.UpdateType.EDITED_MESSAGE,
            )
        )
        app.add_handler(
            CommandHandler(
                "station",
                bot._command_station,
                filters=~filters.UpdateType.EDITED_MESSAGE,
            )
        )

        app.run_polling(
            stop_signals=[
                signal.SIGTERM,
                signal.SIGINT,
            ]
        )

    async def _command_done(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        # Update might be a command or a photo

        message = update.message
        if not message:
            _logger.error("Done command had no message")
            return

        args = context.args
        caption = message.caption
        if args:
            query = " ".join(args)
        elif caption:
            query = caption
        else:
            if not message.photo:
                await message.reply_text(
                    "Du musst den Namen eines Bahnhofs oder Haltepunkts angeben."
                )
            return

        _logger.info("Extracted query for done command: %s", query)

        state = await self._state_storage.load()
        stations = state.stations
        try:
            station = self._find_best_station_match(stations, query)
        except FuzzyMatchingException as e:
            _logger.warning("Could not find station for query %s: %s", query, e)
            reply = (
                "Sorry, das konnte ich nicht zuordnen. Meintest du "
                f"<code>{e.closest_match}</code>"
                "?"
            )
            await message.reply_text(reply, parse_mode=ParseMode.HTML)
            return

        done = state.done_date_by_station_name.get(station.name)
        if done:
            reply = f"Der {station.type.value} {station.name} wurde schon am {done.strftime(DATE_FORMAT)} besucht."
            await message.reply_text(reply)
            return

        message_time = message.date.astimezone(ZoneInfo("Europe/Berlin"))
        state = state.mark_as_done(
            station,
            message_time.date(),
        )
        await self._state_storage.store(state)

        await message.reply_text(
            f"Der {station.type.value} {station.name} wurde als besucht markiert.",
        )

    async def _command_progress(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        message = update.message
        if not message:
            _logger.error("Progress command had no message")
            return

        state = await self._state_storage.load()

        visited = []
        for station in state.stations:
            done_at = state.done_date_by_station_name.get(station.name)
            if not done_at:
                continue

            link = self._format_link(station.name, station.name_link)
            visited.append(f"{link} ({done_at.strftime(DATE_FORMAT)})")
        visited.sort()

        station_list = "\n".join(visited)
        reply = f"{len(visited)} / {len(state.stations)}\n\n{station_list}"
        await message.reply_text(reply, parse_mode=ParseMode.HTML)

    async def _command_station(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        message = update.message
        if not message:
            _logger.error("Station command had no message")
            return

        state = await self._state_storage.load()
        stations = state.stations

        if not stations:
            await message.reply_text("Keine Stationen geladen.")
            return

        _logger.debug("Found %d stations in total", len(stations))
        open_stations = list(state.get_open_stations())
        _logger.debug("%d stations are not done yet", len(open_stations))

        if not open_stations:
            await message.reply_text("Alle Stationen wurden besucht. Glückwunsch!")
            return

        station = random.choice(open_stations)
        await message.reply_text(
            self._format_station(station),
            parse_mode=ParseMode.HTML,
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )

    @staticmethod
    def _format_link(text: str, link: str | HttpUrl | None) -> str:
        if link is None:
            return text

        return f"<a href='{link}'>{text}</a>"

    def _format_station(self, station: Station) -> str:
        buffer = StringIO()

        buffer.write("Name: ")
        buffer.write(self._format_link(station.name, station.name_link))
        buffer.write("\n")

        buffer.write("Betriebsstellenart: ")
        buffer.write(station.type.value)
        buffer.write("\n")

        if stop_types := station.stop_types:
            buffer.write("Erreichbar mit ")
            buffer.write(", ".join(t.value for t in stop_types))
            buffer.write("\n")

        if routes := station.routes:
            if len(routes) == 1:
                buffer.write("Strecke: ")
            else:
                buffer.write("Strecken: ")

            buffer.write(", ".join(self._format_link(r.name, r.link) for r in routes))
            buffer.write("\n")

        if tracks := station.tracks:
            buffer.write("Gleise: ")
            buffer.write(str(tracks))
            buffer.write("\n")

        if town := station.town:
            buffer.write("Stadt: ")
            buffer.write(self._format_link(town, station.town_link))
            buffer.write("\n")

        buffer.write("Kreis: ")
        buffer.write(station.district)
        buffer.write("\n")

        if opening := station.opening:
            buffer.write("Eröffnung: ")
            buffer.write(opening)
            buffer.write("\n")

        if transport_association := station.transport_association:
            buffer.write("Verkehrsbund: ")
            buffer.write(transport_association)
            buffer.write("\n")

        if category := station.category:
            buffer.write("Kategorie: ")
            buffer.write(category)
            buffer.write("\n")

        if notes := station.notes:
            buffer.write("Anmerkungen: ")
            buffer.write(notes)
            buffer.write("\n")

        return buffer.getvalue()

    @staticmethod
    def _find_best_station_match(stations: Iterable[Station], query: str) -> Station:
        _, ratio, result = process.extractOne(
            query,
            {station: station.name for station in stations},
            processor=default_process,
        )

        if ratio > 0.95:
            return result

        raise FuzzyMatchingException(result.name, ratio)
