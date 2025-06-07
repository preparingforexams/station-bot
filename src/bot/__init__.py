import logging
import random
import re
from datetime import datetime
from typing import cast
from zoneinfo import ZoneInfo

from kubernetes import client, config
from telegram import Message as TelegramMessage
from telegram import Update
from telegram.ext import ContextTypes

from bot.actions import TextMessage
from bot.actions.stations import Station, get_stations
from bot.actions.utils import escape_markdown
from bot.imported_stations import STATIONS
from bot.state import ConfigmapState

_logger = logging.getLogger(__package__)

try:
    config.load_incluster_config()
except config.config_exception.ConfigException:
    config.load_kube_config()

kubernetes_api_client = client.CoreV1Api()

_state = ConfigmapState(kubernetes_api_client, {})
_state.initialize()
if not _state["stations"]:
    _state["stations"] = get_stations()
    _state.write()


def update_station(_station: Station) -> bool:
    _stations = []
    marked = False

    for s in _state["stations"]:
        if s == _station:
            _stations.append(_station)
            marked = True
        else:
            _stations.append(s)

    if marked:
        _state["stations"] = _stations
        _state.write()

    return marked


def remove_station(_station: Station):
    new = []
    for s in _state["stations"]:
        if s == _station:
            continue
        new.append(s)

    _state["stations"] = new


def get_station(
    _station: Station,
    _stations: list[Station] | None = None,
) -> Station | None:
    if not _stations:
        _stations = cast(list[Station], _state["stations"])

    try:
        return [s for s in _stations if s == _station][0]
    except IndexError:
        return None


def update_stations():
    _logger.debug("updating stations")

    upstream_stations = get_stations()
    current_stations: list[Station] = _state["stations"]
    new = []

    for upstream_station in upstream_stations:
        _station = get_station(upstream_station, current_stations)
        if _station is None:
            new.append(upstream_station)
        else:
            _station.update_upstream_parameters(upstream_station)
            new.append(_station)

    updated = []
    for current_station in new:
        if get_station(current_station, upstream_stations) is not None:
            updated.append(current_station)

    for s in STATIONS:
        updated.append(Station.deserialize(s))
    _state["stations"] = updated
    _state.write()
    _logger.debug("finished updating stations")


# noinspection PyBroadException
try:
    update_stations()
except Exception:
    _logger.exception("failed to update stations, continuing")


async def station(update: Update, _: ContextTypes.DEFAULT_TYPE):
    _logger.debug("%d are registered", len(_state["stations"]))
    open_stations = [_station for _station in _state["stations"] if not _station.done]
    _logger.debug("%d are available to choose from", len(open_stations))
    # noinspection PyShadowingNames
    station: Station = random.choice(open_stations)
    _logger.debug(station.name)

    message = TextMessage(str(station))
    return await message.send(update)


def find_station_in_caption(
    name: str, stations: list[Station] | None = None
) -> Station | None:
    if stations is None:
        stations = cast(list[Station], _state["stations"])

    match_length = 0
    matched_station = None

    for _station in stations:
        if name == _station.name:
            return _station

        found = re.findall(
            rf"({_station.name})", name, re.UNICODE | re.MULTILINE | re.IGNORECASE
        )
        non_empty = [s for s in found if s]
        if not non_empty:
            continue
        best_match = max(non_empty)
        if len(best_match) > match_length:
            matched_station = _station
            match_length = len(best_match)

    return matched_station


def mark_station_as(_station: Station, _done: bool) -> bool:
    marked = False

    for s in _state["stations"]:
        if s == _station:
            if _done:
                s.done_timestamp = datetime.now(
                    tz=ZoneInfo("Europe/Berlin")
                ).timestamp()
            else:
                s.done_timestamp = None
            marked = True

    if marked:
        return update_station(_station)

    return marked


async def done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # context.args is None when the message is not of type text (`PHOTO` in this case)
    context_args = context.args if context.args else []

    effective_message = cast(TelegramMessage, update.effective_message)
    text = (
        effective_message.caption
        if effective_message.caption
        else " ".join(context_args)
    )
    _station = find_station_in_caption(text)

    if _station:
        _logger.debug("found %s", _station.name)
        if _station.done:
            message = f"{_station.name} was already marked as 'done'"
        elif mark_station_as(_station, True):
            message = rf"Marked {_station.name} as done"
        else:
            message = f"Failed to mark {_station.name} as done, not found"
    else:
        message = "No station found"

    return await TextMessage(escape_markdown(message)).send(update)


async def progress(update: Update, _: ContextTypes.DEFAULT_TYPE):
    open_stations = [_station for _station in _state["stations"] if not _station.done]
    done_stations = set(_state["stations"]) - set(open_stations)

    stations_total = len(_state["stations"])
    stations_done = len(done_stations)
    message_header = escape_markdown(f"{stations_done} / {stations_total}")
    message_body = []

    for _station in sorted(done_stations, key=lambda s: s.name):
        message_body.append(_station.done_overview_string())

    msg = message_header + "\n\n" + "\n".join(message_body)
    message = TextMessage(msg)
    return await message.send(update)


async def set_timestamp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = " ".join(context.args[:-1])  # type: ignore[index]
    date_format = "%d.%m.%Y"

    _station = find_station_in_caption(name)

    if _station:
        if _station.done:
            try:
                time_string = cast(str, context.args[-1])  # type: ignore[index]
                time = datetime.strptime(time_string, date_format)
                _station.done_timestamp = time.timestamp()
                if update_station(_station):
                    message = f"Set `timestamp` for {_station.name} at {time}"
                else:
                    message = f"Couldn't set timestamp for {_station.name} (probably not found)"
            except ValueError as e:
                message = f"Couldn't parse timestamp as {date_format} ({str(e)})"
        else:
            message = r"Station hasn't been marked as done yet, not settings timestamp"
    else:
        message = "No station found"

    return await TextMessage(escape_markdown(message)).send(update)


async def stations(update: Update, context: ContextTypes.DEFAULT_TYPE):
    format_station = lambda s: escape_markdown(f"{s.name} {'(done)' if s.done else ''}")  # noqa: E731

    message = "\n".join([format_station(s) for s in _state["stations"]])
    await TextMessage(message).send(update)
