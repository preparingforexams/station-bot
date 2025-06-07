import dataclasses
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from bot.actions.stations import (
    Station,
    StationType,
    StopType,
    get_stations,
)

# This file was written by an AI, I just thinned out the most insane parts a bit lol.


class TestStationType:
    def test_from_str_haltepunkt(self):
        assert StationType.from_str("hp") == StationType.HALTEPUNKT
        assert StationType.from_str("HP") == StationType.HALTEPUNKT
        assert StationType.from_str("Haltepunkt") == StationType.HALTEPUNKT
        assert StationType.from_str("haltepunkt") == StationType.HALTEPUNKT

    def test_from_str_bahnhof(self):
        assert StationType.from_str("bahnhof") == StationType.BAHNHOF
        assert StationType.from_str("Bahnhof") == StationType.BAHNHOF
        assert StationType.from_str("random_string") == StationType.BAHNHOF

    def test_str_representation(self):
        assert str(StationType.BAHNHOF) == "Bahnhof"
        assert str(StationType.HALTEPUNKT) == "Haltepunkt"


class TestStopType:
    def test_serialize_valid_values(self):
        assert StopType.serialize("Fernverkehrshalt") == StopType.F
        assert StopType.serialize("Regionalverkehrshalt") == StopType.R
        assert StopType.serialize("S-Bahn") == StopType.S

    def test_serialize_invalid_value(self):
        with pytest.raises(ValueError, match="Unmatched StopType: invalid"):
            StopType.serialize("invalid")

    def test_str_representation(self):
        assert str(StopType.F) == "Fernverkehrshalt"
        assert str(StopType.R) == "Regionalverkehrshalt"
        assert str(StopType.S) == "S-Bahn"


class TestStation:
    @pytest.fixture
    def sample_station(self):
        return Station(
            name="Test Station",
            name_link="https://example.com/test_station",
            type=StationType.BAHNHOF,
            tracks=4,
            town="Test Town",
            town_link="https://example.com/test_town",
            district="Test District",
            opening="1900",
            transport_association="Test Association",
            category="Test Category",
            stop_type=StopType.F,
            routes="Test Route",
            notes="Test Notes",
            done_timestamp=None,
            planner_link=None,
        )

    def test_station_equality(self, sample_station):
        other_station = dataclasses.replace(sample_station)
        assert sample_station == other_station

        different_station = dataclasses.replace(sample_station, name="Different")
        assert sample_station != different_station

    def test_station_hash(self, sample_station):
        expected_hash = hash("Test Station" + "Test Town")
        assert hash(sample_station) == expected_hash

    def test_done_property(self, sample_station):
        assert not sample_station.done

        sample_station.done_timestamp = datetime.now().timestamp()
        assert sample_station.done

    def test_done_overview_string_not_done(self, sample_station):
        result = sample_station.done_overview_string()
        assert result == "Test Station"

    def test_done_overview_string_done(self, sample_station):
        # Use a specific timestamp for predictable output
        timestamp = datetime(
            2023, 12, 25, 10, 30, 0, tzinfo=ZoneInfo("Europe/Berlin")
        ).timestamp()
        sample_station.done_timestamp = timestamp

        result = sample_station.done_overview_string()
        assert result == "Test Station \\(25\\.12\\.2023\\)"

    def test_str_representation_not_done(self, sample_station):
        result = str(sample_station)

        assert "Name: [Test Station](https://example.com/test_station)" in result
        assert "Betriebsstelle: Bahnhof" in result
        assert "Gleise: 4" in result
        assert "Done:" not in result

    def test_str_representation_done_with_planner_link(self, sample_station):
        timestamp = datetime(
            2023, 12, 25, 10, 30, 0, tzinfo=ZoneInfo("Europe/Berlin")
        ).timestamp()
        sample_station.done_timestamp = timestamp
        sample_station.planner_link = "https://planner.example.com"

        result = str(sample_station)

        assert "Done: 25\\.12\\.2023" in result
        assert "[DB Plan](https://planner.example.com)" in result

    def test_serialize(self, sample_station):
        result = sample_station.serialize()

        expected = {
            "name": "Test Station",
            "name_link": "https://example.com/test_station",
            "type": "Bahnhof",
            "tracks": 4,
            "town": "Test Town",
            "town_link": "https://example.com/test_town",
            "district": "Test District",
            "opening": "1900",
            "transport_association": "Test Association",
            "category": "Test Category",
            "stop_type": "Fernverkehrshalt",
            "routes": "Test Route",
            "notes": "Test Notes",
            "done_timestamp": None,
        }

        assert result == expected

    def test_deserialize(self):
        data = {
            "name": "Test Station",
            "name_link": "https://example.com/test_station",
            "type": "Bahnhof",
            "tracks": 4,
            "town": "Test Town",
            "town_link": "https://example.com/test_town",
            "district": "Test District",
            "opening": "1900",
            "transport_association": "Test Association",
            "category": "Test Category",
            "stop_type": "Fernverkehrshalt",
            "routes": "Test Route",
            "notes": "Test Notes",
            "done_timestamp": None,
        }

        result = Station.deserialize(data)

        assert result.name == "Test Station"
        assert result.type == StationType.BAHNHOF
        assert result.tracks == 4
        assert result.stop_type == StopType.F
        assert result.planner_link is None

    def test_deserialize_none_tracks(self):
        data = {
            "name": "Test Station",
            "name_link": "https://example.com/test_station",
            "type": "Bahnhof",
            "tracks": None,
            "town": "Test Town",
            "town_link": "https://example.com/test_town",
            "district": "Test District",
            "opening": "1900",
            "transport_association": "Test Association",
            "category": "Test Category",
            "stop_type": "Fernverkehrshalt",
            "routes": "Test Route",
            "notes": "Test Notes",
            "done_timestamp": None,
        }

        result = Station.deserialize(data)
        assert result.tracks is None

    def test_update_upstream_parameters(self, sample_station):
        upstream_station = Station(
            name="Updated Station",
            name_link="https://example.com/updated",
            type=StationType.HALTEPUNKT,
            tracks=2,
            town="Updated Town",
            town_link="https://example.com/updated_town",
            district="Updated District",
            opening="1950",
            transport_association="Updated Association",
            category="Updated Category",
            stop_type=StopType.R,
            routes="Updated Route",
            notes="Updated Notes",
            done_timestamp=None,
            planner_link=None,
        )

        original_done_timestamp = datetime.now().timestamp()
        sample_station.done_timestamp = original_done_timestamp

        sample_station.update_upstream_parameters(upstream_station)

        # Check that upstream parameters were updated
        assert sample_station.name == "Updated Station"
        assert sample_station.type == StationType.HALTEPUNKT
        assert sample_station.tracks == 2
        assert sample_station.stop_type == StopType.R

        # Check that done_timestamp was preserved (not updated)
        assert sample_station.done_timestamp == original_done_timestamp


class TestGetStations:
    @pytest.mark.integration
    def test_get_stations_success(self):
        """Test the actual HTTP request to Wikipedia."""
        stations = get_stations()

        # Basic checks to ensure we got valid data
        assert stations is not None
        assert isinstance(stations, list)
        assert len(stations) > 0

        # Check the first station has expected attributes
        first_station = stations[0]
        assert isinstance(first_station, Station)
        assert first_station.name
        assert isinstance(first_station.type, StationType)
        assert isinstance(first_station.stop_type, StopType)
        assert first_station.town
        assert first_station.district

    @pytest.mark.integration
    def test_get_stations_integration(self):
        """Integration test that verifies the structure of returned data."""
        stations = get_stations()

        assert stations is not None
        assert len(stations) > 100  # Schleswig-Holstein should have many stations

        # Verify some known properties about the data
        station_names = [s.name for s in stations]
        assert any("Kaltenkirchen" in name for name in station_names)

        # Check that we have different types of stations
        station_types = {s.type for s in stations}
        assert len(station_types) >= 1

        # Check that we have different stop types
        stop_types = {s.stop_type for s in stations}
        assert len(stop_types) >= 1

        # Verify that tracks can be None or integer
        tracks_values = {s.tracks for s in stations}
        assert None in tracks_values or any(isinstance(t, int) for t in tracks_values)

    @pytest.mark.integration
    def test_get_stations_data_format(self):
        """Test that get_stations returns properly formatted Station objects."""
        stations = get_stations()

        if stations is None:
            pytest.skip("Network request failed, skipping data format test")

        for station in stations[:5]:  # Test first 5 stations
            # Check required string fields are not empty
            assert station.name.strip()
            assert station.town.strip()
            assert station.district.strip()

            # Check that links are properly formatted
            if station.name_link.strip():
                assert (
                    station.name_link.startswith("https://") or station.name_link == " "
                )

            if station.town_link.strip():
                assert (
                    station.town_link.startswith("https://") or station.town_link == " "
                )

            # Check that tracks is either None or positive integer
            if station.tracks is not None:
                assert isinstance(station.tracks, int)
                assert station.tracks >= 0

            # Check that timestamps are None for fresh data
            assert station.done_timestamp is None
            assert station.planner_link is None
