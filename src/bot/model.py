from enum import Enum
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, HttpUrl, StringConstraints


class StationType(str, Enum):
    BAHNHOF = "Bahnhof"
    HALTEPUNKT = "Haltepunkt"

    @classmethod
    def from_str(cls, s: str) -> Self:
        if s.lower() == "hp" or s.lower() == cls.HALTEPUNKT.value.lower():
            return cls.HALTEPUNKT  # type: ignore[return-value]
        return cls.BAHNHOF  # type: ignore[return-value]


class StopType(str, Enum):
    F = "Fernverkehr"
    R = "Regionalverkehr"
    S = "S-Bahn"

    @classmethod
    def from_columns(
        cls,
        f_column: str | None,
        r_column: str | None,
        s_column: str | None,
    ) -> set[Self]:
        result = set()
        if f_column:
            if f_column != "F":
                raise ValueError(f"Invalid value for F column: {f_column}")
            result.add(cls.F)

        if r_column:
            if r_column != "R":
                raise ValueError(f"Invalid value for R column: {r_column}")
            result.add(cls.R)

        if s_column:
            if s_column != "S":
                raise ValueError(f"Invalid value for S column: {s_column}")
            result.add(cls.S)

        return result  # type: ignore[return-value]


type NonBlankString = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1)
]


class Route(BaseModel):
    model_config = ConfigDict(
        frozen=True,
    )

    name: str
    link: HttpUrl | None


class Station(BaseModel):
    model_config = ConfigDict(
        frozen=True,
    )

    name: NonBlankString
    name_link: HttpUrl | None
    type: StationType
    tracks: int | None
    town: NonBlankString | None
    town_link: HttpUrl | None
    district: NonBlankString
    # This is either just a year or a date like '9. Jun. 1907'
    opening: str | None
    transport_association: NonBlankString | None
    category: NonBlankString | None
    stop_types: frozenset[StopType]
    routes: frozenset[Route]
    notes: str

    def is_same_station(self, other: Self) -> bool:
        link = self.name_link
        other_link = other.name_link

        if link is not None and link == other_link:
            return True

        return self.name == other.name
