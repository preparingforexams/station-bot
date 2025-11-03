import pytest

from bot.model import (
    Station,
    StationType,
    StopType,
)
from bot.wiki import WikipediaClient

# This file was written by an AI, I just thinned out the most insane parts a bit lol.


@pytest.fixture
def client(config) -> WikipediaClient:
    return WikipediaClient(config.user_agent)


class TestGetStations:
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_get_stations_success(self, client):
        """Test the actual HTTP request to Wikipedia."""
        stations = await client.get_wiki_stations()

        # Basic checks to ensure we got valid data
        assert stations is not None
        assert isinstance(stations, list)
        assert len(stations) > 0

        # Check the first station has expected attributes
        first_station = stations[0]
        assert isinstance(first_station, Station)
        assert first_station.name
        assert isinstance(first_station.type, StationType)
        for stop_type in first_station.stop_types:
            assert isinstance(stop_type, StopType)
        assert first_station.town
        assert first_station.district

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_get_stations_integration(self, client):
        """Integration test that verifies the structure of returned data."""
        stations = await client.get_wiki_stations()

        assert stations is not None
        assert len(stations) > 100  # Schleswig-Holstein should have many stations

        # Verify some known properties about the data
        station_names = [s.name for s in stations]
        assert any("Kaltenkirchen" in name for name in station_names)

        # Check that we have different types of stations
        station_types = {s.type for s in stations}
        assert len(station_types) >= 2

        # Check that we have different stop types
        stop_types = {t for s in stations for t in s.stop_types}
        assert len(stop_types) >= 3

        # Verify that tracks can be None or integer
        tracks_values = {s.tracks for s in stations}
        assert None in tracks_values or any(isinstance(t, int) for t in tracks_values)

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_get_stations_data_format(self, client):
        """Test that get_stations returns properly formatted Station objects."""
        stations = await client.get_wiki_stations()

        if stations is None:
            pytest.skip("Network request failed, skipping data format test")

        for station in stations[:5]:  # Test first 5 stations
            # Check required string fields are not empty
            assert station.name.strip()
            assert station.town.strip()
            assert station.district.strip()

            # Check that links are properly formatted
            if station.name_link:
                assert station.name_link.scheme == "https"

            if station.town_link:
                assert station.town_link.scheme == "https"

            # Check that tracks is either None or positive integer
            if station.tracks is not None:
                assert isinstance(station.tracks, int)
                assert station.tracks >= 0
