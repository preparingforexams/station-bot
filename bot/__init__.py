import inspect
import random
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from kubernetes import config, client
from telegram import Update
from telegram.ext import ContextTypes

from . import actions
from .actions import MessageType, get_stations, TextMessage, escape_markdown
from .actions.stations import Station
from .logger import create_logger
from .state import ConfigmapState

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


def send_telegram_error_message(message: str, *, _: Update = None):
    log = create_logger(inspect.currentframe().f_code.co_name)

    log.error(message)


async def station(update: Update, _: ContextTypes.DEFAULT_TYPE):
    log = create_logger(inspect.currentframe().f_code.co_name)

    log.debug(f"{len(_state['stations'])} are registered")
    open_stations = [_station for _station in _state["stations"] if not _station.done]
    log.debug(f"{len(open_stations)} are available to choose from")
    # noinspection PyShadowingNames
    station = random.choice(open_stations)
    log.debug(f"{station.name}")

    message = TextMessage(str(station))
    return await message.send(update)


def find_station_in_caption(caption: str) -> Station:
    match_length = 0
    matched_station = None

    stations = _state["stations"]
    for _station in stations:
        if caption == _station.name:
            return _station

        found = re.findall(fr"({_station.name})", caption, re.UNICODE | re.MULTILINE | re.IGNORECASE)
        non_empty = [s for s in found if s]
        if not non_empty:
            continue
        best_match = max(non_empty)
        if len(best_match) > match_length:
            matched_station = _station
            match_length = len(best_match)

    return matched_station


def update_station(_station: Station) -> bool:
    stations = []
    marked = False

    for s in _state["stations"]:
        if s == _station:
            stations.append(_station)
            marked = True
        else:
            stations.append(s)

    if marked:
        _state["stations"] = stations
        _state.write()

    return marked


def mark_station_as(_station: Station, _done: bool) -> bool:
    stations = []
    marked = False

    for s in _state["stations"]:
        if s == _station:
            s.done = _done
            if _done:
                s.done_timestamp = datetime.now(tz=ZoneInfo("Europe/Berlin")).timestamp()
            else:
                s.done_timestamp = None
            marked = True

    if marked:
        return update_station(_station)

    return marked


async def done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log = create_logger(inspect.currentframe().f_code.co_name)

    text = update.effective_message.caption if update.effective_message.caption else " ".join(context.args)
    _station = find_station_in_caption(text)

    if _station:
        log.debug(f"found {_station.name}")
        if _station.done:
            message = f"{_station.name} was already marked as 'done'"
        elif mark_station_as(_station, True):
            message = fr"Marked {_station.name} as done"
        else:
            message = f"Failed to mark {_station.name} as done, not found"
    else:
        message = "No station found"

    return await TextMessage(escape_markdown(message)).send(update)


async def progress(update: Update, _: ContextTypes.DEFAULT_TYPE):
    open_stations = [_station for _station in _state["stations"] if not _station.done]
    done_stations = set(_state["stations"]) - set(open_stations)

    stations_total = len(_state['stations'])
    stations_done = len(done_stations)
    message_header = escape_markdown(f"{stations_done} / {stations_total}")
    message_body = []
    for _station in done_stations:
        message_body.append(_station.done_overview_string())

    msg = message_header + "\n\n" + "\n".join(message_body)
    message = TextMessage(msg)
    return await message.send(update)


async def set_timestamp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = " ".join(context.args[:-1])
    date_format = "%d.%m.%Y"

    _station = find_station_in_caption(name)

    if _station:
        if _station.done:
            try:
                time = datetime.strptime(context.args[-1], date_format)
                _station.done_timestamp = time.timestamp()
                if update_station(_station):
                    message = f"Set `timestamp` for {_station.name} at {time}"
                else:
                    message = f"Couldn't set timestamp for {_station.name} (probably not found)"
            except ValueError as e:
                message = f"Couldn't parse timestamp as {date_format} ({str(e)})"
        else:
            message = fr"Station hasn't been marked as done yet, not settings timestamp"
    else:
        message = "No station found"

    return await TextMessage(escape_markdown(message)).send(update)
