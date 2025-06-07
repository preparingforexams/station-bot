from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from datetime import date
from typing import Self

from bs_state import StateStorage
from pydantic import BaseModel, ConfigDict

from bot.model import Station

type StateStorageFactory[T: BaseModel] = Callable[[T], Awaitable[StateStorage[T]]]


class StationState(BaseModel):
    model_config = ConfigDict(
        frozen=True,
    )

    stations: Sequence[Station]
    done_date_by_station_name: Mapping[str, date]

    def get_open_stations(self) -> Iterable[Station]:
        for station in self.stations:
            if not self.done_date_by_station_name.get(station.name):
                yield station

    @classmethod
    def empty(cls):
        return cls(
            stations=[],
            done_date_by_station_name={},
        )

    def update_stations(self, fresh_stations: list[Station]) -> Self:
        stations = list(self.stations)
        for fresh_station in fresh_stations:
            old_index = -1
            for index, station in enumerate(stations):
                if station.is_same_station(fresh_station):
                    old_index = index
                    break

            if old_index > -1:
                stations[old_index] = fresh_station
            else:
                stations.append(fresh_station)

        return StationState(  # type: ignore[return-value]
            stations=stations,
            done_date_by_station_name=self.done_date_by_station_name,
        )

    def mark_as_done(
        self,
        station: Station,
        at_date: date,
    ) -> Self:
        done_date_by_station_name = dict(self.done_date_by_station_name)
        if station.name in done_date_by_station_name:
            raise ValueError("Station already done")

        done_date_by_station_name[station.name] = at_date
        return StationState(  # type: ignore[return-value]
            stations=self.stations,
            done_date_by_station_name=done_date_by_station_name,
        )
