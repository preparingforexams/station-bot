import asyncio
import logging
import unicodedata
from typing import TYPE_CHECKING, overload
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup, Tag
from httpx import URL
from pydantic import (
    HttpUrl,
)

from bot.model import Route, Station, StationType, StopType

if TYPE_CHECKING:
    from collections.abc import Iterable

    from bot.config import UserAgentConfig

_logger = logging.getLogger(__name__)


# noinspection PyMethodMayBeStatic
class _StationParser:
    def __init__(self, url: URL) -> None:
        self.requested_url = url

    def parse_stations(self, raw_wiki_page: str) -> list[Station] | None:
        soup = BeautifulSoup(raw_wiki_page, "html.parser")
        tables = soup.find_all("table")
        if not tables:
            _logger.error("No tables found on page")
            return None

        table = tables[0]
        body = table.find("tbody")
        if not body:
            _logger.error("No body found in table")
            return None

        rows = body.find_all("tr")

        stations = []
        # Skip header row
        for row in rows[1:]:
            station = self._parse_station(row)
            if station is None:
                _logger.warning("Skipping station that couldn't be parsed")
                continue
            stations.append(station)

        return stations

    def _parse_station(self, row: Tag) -> Station | None:
        columns: list[Tag] = row.find_all("td")
        if len(columns) < 13:  # Ensure we have enough columns
            _logger.error("Encountered row with too few columns: %s", row)
            return None

        tracks_str = self._normalize_blank_string(columns[2].string)

        return Station(
            name=self._get_station_name(columns[0]),
            name_link=self._get_link(columns[0]),
            type=self._parse_type(columns[1]),
            tracks=int(tracks_str) if tracks_str else None,
            town=self._normalize_unicode_string(
                " ".join(self._filter_blank_strings(columns[3].strings)) or None
            ),
            town_link=self._get_link(columns[3]),
            district=self._normalize_blank_string(columns[4].string),  # type: ignore
            opening=self._parse_opening_date(columns[5]),
            transport_association=self._normalize_blank_string(columns[6].string),
            category=self._normalize_blank_string(columns[7].string),
            stop_types=frozenset(
                StopType.from_columns(
                    self._normalize_blank_string(columns[8].string),
                    self._normalize_blank_string(columns[9].string),
                    self._normalize_blank_string(columns[10].string),
                )
            ),
            routes=self._parse_routes(columns[11]),
            notes=self._normalize_unicode_string(
                " ".join(self._filter_blank_strings(columns[12].strings))
            ),
        )

    def _filter_blank_strings(self, strings: Iterable[str | None]) -> Iterable[str]:
        for string in strings:
            if string is None:
                continue

            if stripped := string.strip():
                yield stripped

    @overload
    def _normalize_blank_string(self, s: str | None, default: str) -> str:
        pass

    @overload
    def _normalize_blank_string(
        self, s: str | None, default: str | None = None
    ) -> str | None:
        pass

    def _normalize_blank_string(
        self, s: str | None, default: str | None = None
    ) -> str | None:
        if s is None:
            return default

        if stripped := s.strip():
            return stripped

        return default

    def _parse_type(self, tag: Tag) -> StationType:
        text = tag.string
        if not text:
            return StationType.BAHNHOF

        return StationType.from_str(text)

    def _normalize_unicode_string[T: str | None](
        self,
        unicode_string: T,
    ) -> T:
        if unicode_string is None:
            return None  # type: ignore
        return unicodedata.normalize("NFKD", unicode_string).strip()  # type: ignore

    def _parse_opening_date(self, tag: Tag) -> str | None:
        text = self._normalize_unicode_string(tag.string)
        if not text:
            return None

        return text

    def _parse_route(self, a_tag: Tag) -> Route:
        link = a_tag.attrs.get("href", "")
        cls = a_tag.attrs.get("class", "")

        # a 'new' class marks the link as red indicating that the site does not yet exist
        if not link or "new" in cls:
            url = None
        else:
            url = HttpUrl(str(self.requested_url.join(link)))

        return Route(name=a_tag.text, link=url)

    def _parse_routes(self, route_tag: Tag) -> frozenset[Route]:
        routes = set()
        for a in route_tag.find_all("a"):
            routes.add(self._parse_route(a))

        return frozenset(routes)

    def _get_link(self, t: Tag) -> HttpUrl | None:
        a = t.find("a")
        if not isinstance(a, Tag):
            return None

        link = a.attrs.get("href", "")
        cls = a.attrs.get("class", "")
        # a 'new' class marks the link as red indicating that the site does not yet exist
        if "new" in cls:
            return None

        return HttpUrl(str(self.requested_url.join(link)))

    def _get_station_name(self, t: Tag) -> str:
        link_tags = t.find_all("a")
        if not link_tags:
            strings = list(t.strings)
        else:
            strings = [a.text for a in link_tags]

        return "".join(strings)


class _RobotInfo:
    def __init__(
        self,
        *,
        base_url: str,
        parser: RobotFileParser,
        user_agent: str,
    ) -> None:
        self._base_url = base_url
        self._parser = parser
        self._user_agent = user_agent

    def can_request(self, url_path: str) -> bool:
        return self._parser.can_fetch(
            self._user_agent,
            f"{self._base_url}{url_path}",
        )


class WikipediaClient:
    def __init__(self, config: UserAgentConfig) -> None:
        self._base_url = "https://de.wikipedia.org"
        self._user_agent = config.build_header_value()
        self._robots_lock = asyncio.Lock()
        self._robots_loaded = asyncio.Event()
        self._robots: _RobotInfo | None = None

    def _create_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base_url,
            headers={
                "User-Agent": self._user_agent,
            },
        )

    async def _get_robots(self) -> _RobotInfo | None:
        if self._robots_loaded.is_set():
            return self._robots

        async with self._robots_lock:
            try:
                robots = await self._load_robots()
                self._robots = robots
                return robots
            finally:
                self._robots_loaded.set()

    async def get_wiki_stations(self) -> list[Station] | None:
        """
        Asynchronously fetch and parse stations from Wikipedia.

        Returns:
            List of Station objects or None if the request failed.
        """
        robots = await self._get_robots()

        if robots is None:
            _logger.warning("No robots info, so not requesting page")
            return None

        url_path = "/wiki/Liste_der_Personenbahnh%C3%B6fe_in_Schleswig-Holstein"
        if not robots.can_request(url_path):
            _logger.error("Not allowed to request page")
            return None

        async with self._create_client() as client:
            try:
                response = await client.get(
                    url_path,
                    headers={
                        "Accept": "text/html",
                    },
                )
            except httpx.RequestError:
                _logger.exception("Could not fetch stations")
                return None

            if not response.is_success:
                _logger.error(
                    "Received unsuccessful response from Wikipedia: %d",
                    response.status_code,
                )
                _logger.error(response.text)
                return None

            parser = _StationParser(response.url)
            return parser.parse_stations(response.text)

    async def _load_robots(self) -> _RobotInfo | None:
        async with self._create_client() as client:
            try:
                response = await client.get("/robots.txt")
            except httpx.RequestError as e:
                _logger.error("Could not fetch robots.txt", exc_info=e)
                return None

            if not response.is_success:
                _logger.error(
                    "Unsuccessful robots.txt repsonse %d", response.status_code
                )
                return None

            parser = RobotFileParser()
            try:
                parser.parse(response.iter_lines())
            except ValueError as e:
                _logger.error("Could not parse robots.txt", exc_info=e)
                return None

            return _RobotInfo(
                base_url=self._base_url,
                parser=parser,
                user_agent=self._user_agent,
            )
