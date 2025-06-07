from bot.model import Route, Station, StationType, StopType

IMPORTED_STATIONS = [
    Station(
        name="Lübeck-Moisling",
        name_link="https://de.wikipedia.org/wiki/L%C3%BCbeck-Moisling",  # type: ignore[arg-type]
        type=StationType.HALTEPUNKT,
        tracks=2,
        town="Lübeck",
        town_link="https://de.wikipedia.org/wiki/L%C3%BCbeck",  # type: ignore[arg-type]
        district="HL",
        opening="22. Dez. 2023",
        transport_association="HVV",
        category=None,
        stop_types=frozenset({StopType.R}),
        routes=frozenset(
            {
                Route(
                    name="Lübeck-Hamburg",
                    link="https://de.wikipedia.org/wiki/Bahnstrecke_L%C3%BCbeck%E2%80%93Hamburg",  # type: ignore[arg-type]
                ),
            }
        ),
        notes="",
    ),
]
