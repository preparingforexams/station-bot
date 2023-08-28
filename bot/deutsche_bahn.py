import os
import re
from datetime import datetime
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import requests


def send(params: dict | None = None) -> requests.Response:
    CLIENT_ID = os.getenv("DB_CLIENT_ID")
    CLIENT_SECRET = os.getenv("DB_CLIENT_SECRET")

    base_url = "https://apis.deutschebahn.com/db-api-marketplace/apis/station-data/v2/stations"
    headers = {
        "Accept": "application/json",
        "DB-Client-Id": CLIENT_ID,
        "DB-Api-Key": CLIENT_SECRET,
    }

    return requests.get(base_url, headers=headers, params=params)


def get_stations_for_state(state: str) -> list[dict]:
    response = send(params={
        "federalstate": state,
    })
    response.raise_for_status()

    return response.json()['result']


def find_station_by_name(name: str, *, state: str = "Schleswig-Holstein") -> dict:
    stations = get_stations_for_state(state)
    match_length = 0
    matched_station = None

    for _station in stations:
        if name == _station['name']:
            return _station

        found = re.findall(fr"({_station['name']})", name, re.UNICODE | re.MULTILINE | re.IGNORECASE)
        non_empty = [s for s in found if s]
        if not non_empty:
            continue
        best_match = max(non_empty)
        if len(best_match) > match_length:
            matched_station = _station
            match_length = len(best_match)

    return matched_station


def generate_oid(station: dict) -> str:
    station_name = station['name']
    main_eva = [eva for eva in station['evaNumbers'] if eva['isMain']][0]
    eva_number = main_eva['number']
    x, y = main_eva['geographicCoordinates']['coordinates']

    return f"A=1@O={station_name}@X={x}@Y={y}@U=80@L={eva_number}@B=1@p=1692821240@"


def generate_planner_link(origin: str, destination: str) -> str:
    now = datetime.now(tz=ZoneInfo("Europe/Berlin"))
    now_r = now.strftime("%H:%M")

    params = {
        "soid": generate_oid(find_station_by_name(origin)),
        "zoid": generate_oid(find_station_by_name(destination)),
    }

    params.update({
        "sts": "true",
        "so": origin,
        "zo": destination,
        "kl": 2,
        "r": f"13:16:KLASSENLOS:1",
        "hd": now.strftime("%Y-%m-%dT%H:%M:%S"),
        "hza": "D",
        "ar": "false",
        # fastest connection
        "s": "true",
        # direct connections only
        "d": "false",
        "hz": "%5B%5D",
        "fm": "false",
        "bp": "false",
    })

    return f"https://next.bahn.de/buchung/fahrplan/suche?{urlencode(params)}"
