import pytest

from bot.model import Route, Station, StationType, StopType


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


class TestStopType:
    @pytest.mark.parametrize(
        "f,s,r,expected",
        [
            ("F", "S", "R", {StopType.F, StopType.R, StopType.S}),
            (None, "S", "R", {StopType.R, StopType.S}),
            ("", "S", None, {StopType.S}),
        ],
    )
    def test_from_columns_valid_values(self, f, s, r, expected):
        types = StopType.from_columns(f_column=f, s_column=s, r_column=r)
        assert types == expected

    @pytest.mark.parametrize(
        "value",
        [" ", "invalid", "F"],
    )
    def test_from_columns_invalid_value(self, value):
        with pytest.raises(ValueError):
            StopType.from_columns("F", "R", value)


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
            stop_types={StopType.F},
            routes=[
                Route(
                    name="Test Route",
                    link=None,
                ),
                Route(
                    name="Test Route 2",
                    link="https://example.com/test_route2",
                ),
            ],
            notes="Test Notes",
        )

    def test_serialize(self, sample_station):
        result = sample_station.model_dump(mode="json")

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
            "stop_types": ["Fernverkehr"],
            "routes": [
                {
                    "name": "Test Route",
                    "link": None,
                },
                {
                    "name": "Test Route 2",
                    "link": "https://example.com/test_route2",
                },
            ],
            "notes": "Test Notes",
        }

        result_routes = result.pop("routes")
        result_routes.sort(key=lambda r: r["name"])
        expected_routes = expected.pop("routes")
        expected_routes.sort(key=lambda r: r["name"])
        assert result_routes == expected_routes

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
            "stop_types": ["Fernverkehr"],
            "routes": [],
            "notes": "Test Notes",
        }

        result = Station.model_validate(data)

        assert result.name == "Test Station"
        assert result.type == StationType.BAHNHOF
        assert result.tracks == 4
        assert result.stop_types == {StopType.F}

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
            "stop_types": ["Fernverkehr"],
            "notes": "Test Notes",
            "routes": [],
        }

        result = Station.model_validate(data)
        assert result.tracks is None
