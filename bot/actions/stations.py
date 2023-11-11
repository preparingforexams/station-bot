import dataclasses
import unicodedata
from datetime import datetime
from enum import Enum
from typing import Optional, Self
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup, Tag

from bot import actions


class StationType(Enum):
    BAHNHOF = "Bahnhof"
    HALTEPUNKT = "Haltepunkt"

    @classmethod
    def from_str(cls, s: str) -> Self:
        if s.lower() == "hp":
            return cls.HALTEPUNKT

        return cls.BAHNHOF

    def __str__(self):
        return self.value


class StopType(Enum):
    F = "Fernverkehrshalt"
    R = "Regionalverkehrshalt"
    S = "S-Bahn"

    @classmethod
    def from_columns(cls, c1: str, c2: str, c3: str):
        if len(c1) != 0:
            return cls.F
        elif len(c2) != 0:
            return cls.R

        return cls.S

    @classmethod
    def serialize(cls, s: str) -> Self:
        if s == StopType.F.value:
            return StopType.F
        elif s == StopType.R.value:
            return StopType.R
        elif s == StopType.S.value:
            return StopType.S

    def __str__(self):
        return self.value


def format_routes(route_tag: Tag) -> str:
    routes = []
    for a in route_tag.find_all("a"):
        link = a["href"]
        if not link.startswith("https://"):
            link = f"https://de.wikipedia.org{link}"
        if not link:
            link = " "
        routes.append(f"[{actions.escape_markdown(a.text)}]({actions.escape_markdown(link)})")

    return "\n".join(routes)


@dataclasses.dataclass
class Station:
    name: str
    name_link: str
    type: StationType
    tracks: Optional[int]
    town: str
    town_link: str
    district: str
    opening: str
    transport_association: str
    category: str
    stop_type: StopType
    routes: str
    notes: str
    done_timestamp: Optional[int]
    planner_link: Optional[str]

    def __eq__(self, other):
        return other.name == self.name

    def done_overview_string(self) -> str:
        if self.done_timestamp:
            s = datetime.fromtimestamp(self.done_timestamp, tz=ZoneInfo("Europe/Berlin")).strftime("%d.%m.%Y")
            return actions.escape_markdown(f"{self.name} ({s})")
        else:
            return actions.escape_markdown(self.name)

    def __str__(self):
        done_string = ""
        planner_link_string = ""
        if self.done_timestamp:
            s = datetime.fromtimestamp(self.done_timestamp, tz=ZoneInfo("Europe/Berlin")).strftime("%d.%m.%Y")
            done_string = actions.escape_markdown(f"Done: {s}")
        if getattr(self, "planner_link"):
            planner_link_string = f"[DB Plan]({self.planner_link})"

        return rf"""
Name: [{actions.escape_markdown(self.name)}]({self.name_link})
Betriebsstelle: {actions.escape_markdown(str(self.type))}
Gleise: {self.tracks}
Stadt: [{actions.escape_markdown(self.town)}]({self.town_link})
Kreis: {actions.escape_markdown(self.district)}
Eröffnung: {actions.escape_markdown(self.opening)}
Verkehrsverbund: {actions.escape_markdown(self.transport_association)}
Kategorie: {actions.escape_markdown(self.category)}
Halt\-Typ: {actions.escape_markdown(str(self.stop_type))}
Strecke: {self.routes}
Anmerkungen: {actions.escape_markdown(self.notes)}
{done_string}
{planner_link_string}"""

    def serialize(self):
        return {
            "name": self.name.strip(),
            "name_link": self.name_link.strip(),
            "type": str(self.type),
            "tracks": self.tracks,
            "town": self.town.strip(),
            "town_link": self.town_link.strip(),
            "district": self.district.strip(),
            "opening": self.opening.strip(),
            "transport_association": self.transport_association.strip(),
            "category": self.category.strip(),
            "stop_type": str(self.stop_type),
            "routes": self.routes.strip(),
            "notes": self.notes.strip(),
            "done_timestamp": self.done_timestamp,
        }

    @classmethod
    def deserialize(cls, obj: dict) -> Self:
        return Station(
            obj["name"],
            obj["name_link"],
            StationType.from_str(obj["type"]),
            int(obj["tracks"]) if obj["tracks"] else None,
            obj["town"],
            obj["town_link"],
            obj["district"],
            obj["opening"],
            obj["transport_association"],
            obj["category"],
            StopType.serialize(obj["stop_type"]),
            obj["routes"],
            obj["notes"],
            obj.get("done_timestamp"),
            None,
        )

    @property
    def done(self):
        return self.done_timestamp is not None

    def __hash__(self):
        return hash(self.name + self.town)


def get_link(t: Tag) -> str:
    a = t.find("a")
    if not a:
        return " "

    link = a["href"]
    if not link.startswith("https://"):
        link = f"https://de.wikipedia.org/{link}"

    return actions.escape_markdown(link)


def normalize_column_strings(columns: list[Tag], unicode_form: str = "NFC") -> list[str]:
    return [unicodedata.normalize(unicode_form, " ".join(column.strings)).strip() for column in columns]


def get_station_name(t: Tag) -> str:
    link_tags = t.find_all("a")
    if not link_tags:
        strings = list(t.strings)
    else:
        strings = [a.text for a in link_tags]

    return "".join(strings)


def get_stations() -> Optional[list[Station]]:
    response = requests.get(
        "https://de.wikipedia.org/wiki/Liste_der_Personenbahnh%C3%B6fe_in_Schleswig-Holstein"
    )
    if not response.ok:
        return None

    soup = BeautifulSoup(response.text, "html.parser")
    out = soup.find_all("table")
    table = out[1]
    body = table.find("tbody")
    rows = body.find_all("tr")

    stations = []
    for row in rows[1:]:
        columns: list[Tag] = row.find_all("td")
        column_strings = normalize_column_strings(columns)
        tracks = int(column_strings[2]) if column_strings[2] else None

        station = Station(
            name=get_station_name(columns[0]),
            name_link=get_link(columns[0]),
            type=StationType.from_str(column_strings[1]),
            tracks=tracks,
            town=column_strings[3],
            town_link=get_link(columns[3]),
            district=column_strings[4],
            opening=column_strings[5],
            transport_association=column_strings[6],
            category=column_strings[7],
            stop_type=StopType.from_columns(column_strings[8], column_strings[9], column_strings[10]),
            routes=format_routes(columns[11]),
            notes=column_strings[12],
            done_timestamp=None,
            planner_link=None,
        )

        stations.append(station)

    return stations
