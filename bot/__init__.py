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
from .deutsche_bahn import generate_planner_link
from .imported_stations import STATIONS
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


def get_station(_station: Station, _stations: list[Station] = None) -> Station | None:
    if not _stations:
        _stations = _state["stations"]

    try:
        return [s for s in _stations if s == _station][0]
    except IndexError:
        return None


def update_stations():
    log = create_logger(inspect.currentframe().f_code.co_name)
    log.debug("updating stations")

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
    log.debug("finished updating stations")


# noinspection PyBroadException
try:
    update_stations()
except Exception as e:
    create_logger("update_stations").error("failed to update stations, continuing", exc_info=True)


def send_telegram_error_message(message: str, *, _: Update = None):
    log = create_logger(inspect.currentframe().f_code.co_name)

    log.error(message)


async def station(update: Update, _: ContextTypes.DEFAULT_TYPE):
    log = create_logger(inspect.currentframe().f_code.co_name)

    log.debug(f"{len(_state['stations'])} are registered")
    open_stations = [_station for _station in _state["stations"] if not _station.done]
    log.debug(f"{len(open_stations)} are available to choose from")
    # noinspection PyShadowingNames
    station: Station = random.choice(open_stations)
    log.debug(f"{station.name}")

    # noinspection PyBroadException
    try:
        planner_link = generate_planner_link("Husum", station.name)
        station.planner_link = planner_link
    except Exception:
        log.error("couldn't generate db planner link", exc_info=True)

    message = TextMessage(str(station))
    return await message.send(update)


def find_station_in_caption(name: str, stations: list[Station] = None) -> Station:
    if stations is None:
        stations = _state["stations"]

    match_length = 0
    matched_station = None

    for _station in stations:
        if name == _station.name:
            return _station

        found = re.findall(fr"({_station.name})", name, re.UNICODE | re.MULTILINE | re.IGNORECASE)
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
                s.done_timestamp = datetime.now(tz=ZoneInfo("Europe/Berlin")).timestamp()
            else:
                s.done_timestamp = None
            marked = True

    if marked:
        return update_station(_station)

    return marked


async def done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log = create_logger(inspect.currentframe().f_code.co_name)
    # context.args is None when the message is not of type text (`PHOTO` in this case)
    context_args = context.args if context.args else []

    text = update.effective_message.caption if update.effective_message.caption else " ".join(context_args)
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

    done_stations = sorted(done_stations, key=lambda s: s.name)
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


async def stations(update: Update, context: ContextTypes.DEFAULT_TYPE):
    format_station = lambda s: escape_markdown(f"{s.name} {'(done)' if s.done else ''}")

    message = "\n".join([format_station(s) for s in _state["stations"]])
    await TextMessage(message).send(update)
