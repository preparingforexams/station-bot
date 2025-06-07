import unicodedata
from datetime import datetime
from enum import Enum
from typing import Self
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup, Tag
from pydantic import BaseModel, Field, computed_field

from bot.actions.utils import escape_markdown


class StationType(str, Enum):
    BAHNHOF = "Bahnhof"
    HALTEPUNKT = "Haltepunkt"

    @classmethod
    def from_str(cls, s: str) -> Self:
        if s.lower() == "hp" or s.lower() == cls.HALTEPUNKT.value.lower():
            return cls.HALTEPUNKT
        return cls.BAHNHOF


class StopType(str, Enum):
    F = "Fernverkehrshalt"
    R = "Regionalverkehrshalt"
    S = "S-Bahn"

    @classmethod
    def from_columns(cls, c1: str, c2: str, _c3: str) -> Self:
        if len(c1) != 0:
            return cls.F
        elif len(c2) != 0:
            return cls.R
        return cls.S


class Station(BaseModel):
    name: str
    name_link: str
    type: StationType
    tracks: int | None = None
    town: str
    town_link: str
    district: str
    opening: str
    transport_association: str
    category: str
    stop_type: StopType
    routes: str
    notes: str
    done_timestamp: float | None = None
    planner_link: str | None = None

    @computed_field
    @property
    def done(self) -> bool:
        return self.done_timestamp is not None

    def __eq__(self, other):
        if isinstance(other, Station):
            return other.name == self.name
        return False

    def __hash__(self):
        return hash(self.name + self.town)

    def done_overview_string(self) -> str:
        if self.done_timestamp:
            s = datetime.fromtimestamp(
                self.done_timestamp, tz=ZoneInfo("Europe/Berlin")
            ).strftime("%d.%m.%Y")
            return escape_markdown(f"{self.name} ({s})")
        else:
            return escape_markdown(self.name)

    def __str__(self):
        done_string = ""
        planner_link_string = ""
        if self.done_timestamp:
            s = datetime.fromtimestamp(
                self.done_timestamp, tz=ZoneInfo("Europe/Berlin")
            ).strftime("%d.%m.%Y")
            done_string = escape_markdown(f"Done: {s}")
        if self.planner_link:
            planner_link_string = f"[DB Plan]({self.planner_link})"

        return rf"""
Name: [{escape_markdown(self.name)}]({self.name_link})
Betriebsstelle: {escape_markdown(str(self.type))}
Gleise: {self.tracks}
Stadt: [{escape_markdown(self.town)}]({self.town_link})
Kreis: {escape_markdown(self.district)}
Eröffnung: {escape_markdown(self.opening)}
Verkehrsverbund: {escape_markdown(self.transport_association)}
Kategorie: {escape_markdown(self.category)}
Halt\-Typ: {escape_markdown(str(self.stop_type))}
Strecke: {self.routes}
Anmerkungen: {escape_markdown(self.notes)}
{done_string}
{planner_link_string}"""

    def update_upstream_parameters(self, station: Self) -> None:
        """Update all fields except done_timestamp and planner_link from another station."""
        for field_name in self.model_fields:
            if field_name not in ("done_timestamp", "planner_link"):
                setattr(self, field_name, getattr(station, field_name))

    model_config = {"frozen": False}


def format_routes(route_tag: Tag) -> str:
    routes = []
    for a in route_tag.find_all("a"):
        link = a.get("href", "")
        cls = a.attrs.get("class", [])
        # a 'new' class marks the link as red indicating that the site does not yet exist
        if not link or "new" in cls:
            link = " "
        elif not link.startswith("https://"):
            link = f"https://de.wikipedia.org{link}"
        routes.append(f"[{escape_markdown(a.text)}]({escape_markdown(link)})")

    return "\n".join(routes)


def get_link(t: Tag) -> str:
    a = t.find("a")
    if not a:
        return " "

    link = a.get("href", "")
    cls = a.attrs.get("class", [])
    # a 'new' class marks the link as red indicating that the site does not yet exist
    if "new" in cls:
        return " "

    if not link.startswith("https://"):
        link = f"https://de.wikipedia.org/{link}"

    return escape_markdown(link)


def normalize_column_strings(
    columns: list[Tag],
    unicode_form: str = "NFC",
) -> list[str]:
    return [
        unicodedata.normalize(unicode_form, " ".join(column.strings)).strip()
        for column in columns
    ]


def get_station_name(t: Tag) -> str:
    link_tags = t.find_all("a")
    if not link_tags:
        strings = list(t.strings)
    else:
        strings = [a.text for a in link_tags]

    return "".join(strings)


async def get_stations() -> list[Station] | None:
    """
    Asynchronously fetch and parse stations from Wikipedia.

    Returns:
        List of Station objects or None if the request failed.
    """
    url = "https://de.wikipedia.org/wiki/Liste_der_Personenbahnh%C3%B6fe_in_Schleswig-Holstein"

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url)
            response.raise_for_status()
        except httpx.HTTPError:
            return None

    soup = BeautifulSoup(response.text, "html.parser")
    tables = soup.find_all("table")
    if not tables:
        return None

    table = tables[0]
    body = table.find("tbody")
    if not body:
        return None

    rows = body.find_all("tr")

    stations = []
    for row in rows[1:]:  # Skip header row
        columns: list[Tag] = row.find_all("td")
        if len(columns) < 13:  # Ensure we have enough columns
            continue

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
            stop_type=StopType.from_columns(
                column_strings[8], column_strings[9], column_strings[10]
            ),
            routes=format_routes(columns[11]),
            notes=column_strings[12],
        )

        stations.append(station)

    return stations
