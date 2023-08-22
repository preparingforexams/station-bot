import inspect
import random
import re

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


def mark_station_as_done(_station: Station) -> bool:
    stations = []
    marked = False

    for s in _state["stations"]:
        if s == _station:
            s.done = True
            marked = True
        stations.append(s)

    if marked:
        _state["stations"] = stations
        _state.write()

    return marked


async def done(update: Update, _: ContextTypes.DEFAULT_TYPE):
    log = create_logger(inspect.currentframe().f_code.co_name)

    text = update.effective_message.caption if update.effective_message.caption else update.effective_message.text
    _station = find_station_in_caption(text)
    log.debug(f"found {_station}")

    if _station:
        if _station.done:
            message = f"{_station.name} was already marked as 'done'"
        elif mark_station_as_done(_station):
            message = fr"Marked {_station.name} as done \({_station.done}\)"
        else:
            message = f"Failed to mark {_station.name} as done, not found"
    else:
        message = "No station found"

    return await TextMessage(escape_markdown(message)).send(update)
