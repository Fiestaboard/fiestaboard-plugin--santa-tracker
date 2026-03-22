"""Tests for the santa_tracker plugin."""

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest
import pytz

from plugins.santa_tracker import SANTA_LOCATIONS, SantaTrackerPlugin, _get_santa_status


class TestSantaTrackerPlugin:
    """Test suite for SantaTrackerPlugin."""

    def test_plugin_id(self, sample_manifest):
        """Test plugin ID matches directory name and manifest."""
        plugin = SantaTrackerPlugin(sample_manifest)
        assert plugin.plugin_id == "santa_tracker"

    def test_validate_config_valid(self, sample_manifest):
        """Test config validation with valid config."""
        plugin = SantaTrackerPlugin(sample_manifest)
        errors = plugin.validate_config({"enabled": True})
        assert len(errors) == 0

    def test_validate_config_valid_year(self, sample_manifest):
        """Test config validation with a valid year."""
        plugin = SantaTrackerPlugin(sample_manifest)
        errors = plugin.validate_config({"enabled": True, "year": 2026})
        assert len(errors) == 0

    def test_validate_config_invalid_year_low(self, sample_manifest):
        """Test config validation rejects year before 2024."""
        plugin = SantaTrackerPlugin(sample_manifest)
        errors = plugin.validate_config({"enabled": True, "year": 2020})
        assert len(errors) > 0
        assert any("year" in e.lower() for e in errors)

    def test_validate_config_invalid_year_high(self, sample_manifest):
        """Test config validation rejects year after 2100."""
        plugin = SantaTrackerPlugin(sample_manifest)
        errors = plugin.validate_config({"enabled": True, "year": 2200})
        assert len(errors) > 0

    def test_validate_config_invalid_year_type(self, sample_manifest):
        """Test config validation rejects non-integer year."""
        plugin = SantaTrackerPlugin(sample_manifest)
        errors = plugin.validate_config({"enabled": True, "year": "2026"})
        assert len(errors) > 0

    def test_validate_config_no_year(self, sample_manifest):
        """Test config validation succeeds when year is omitted."""
        plugin = SantaTrackerPlugin(sample_manifest)
        errors = plugin.validate_config({"enabled": True})
        assert len(errors) == 0

    @patch("plugins.santa_tracker.datetime")
    def test_fetch_data_before_christmas(self, mock_datetime, sample_manifest, sample_config):
        """Test fetch_data before Christmas in all timezones."""
        # Dec 1 at noon UTC — well before Christmas anywhere
        mock_now = datetime(2026, 12, 1, 12, 0, 0, tzinfo=pytz.utc)
        mock_datetime.now.return_value = mock_now
        mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)

        plugin = SantaTrackerPlugin(sample_manifest)
        plugin.config = sample_config
        result = plugin.fetch_data()

        assert result.available is True
        assert result.data is not None
        assert "getting ready" in result.data["status"].lower()
        assert result.data["santa_location"] == "North Pole"
        assert result.data["visited_count"] == "0"
        assert result.data["progress_percent"] == "0"

    @patch("plugins.santa_tracker.datetime")
    def test_fetch_data_during_christmas(self, mock_datetime, sample_manifest, sample_config):
        """Test fetch_data when Christmas is happening in some timezones."""
        # Dec 25 at 00:30 UTC — midnight has hit UTC+0 and earlier timezones
        mock_now = datetime(2026, 12, 25, 0, 30, 0, tzinfo=pytz.utc)
        mock_datetime.now.return_value = mock_now
        mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)

        plugin = SantaTrackerPlugin(sample_manifest)
        plugin.config = sample_config
        result = plugin.fetch_data()

        assert result.available is True
        assert result.data is not None
        assert "delivering" in result.data["status"].lower()
        assert int(result.data["visited_count"]) > 0
        assert int(result.data["visited_count"]) < int(result.data["total_locations"])

    @patch("plugins.santa_tracker.datetime")
    def test_fetch_data_after_christmas(self, mock_datetime, sample_manifest, sample_config):
        """Test fetch_data when Christmas is over everywhere."""
        # Dec 26 at 12:00 UTC — well after Christmas even in UTC-10
        mock_now = datetime(2026, 12, 26, 12, 0, 0, tzinfo=pytz.utc)
        mock_datetime.now.return_value = mock_now
        mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)

        plugin = SantaTrackerPlugin(sample_manifest)
        plugin.config = sample_config
        result = plugin.fetch_data()

        assert result.available is True
        assert result.data is not None
        assert "done" in result.data["status"].lower()
        assert result.data["santa_location"] == "North Pole"
        assert result.data["visited_count"] == result.data["total_locations"]
        assert result.data["progress_percent"] == "100"

    @patch("plugins.santa_tracker.datetime")
    def test_fetch_data_uses_current_year_default(self, mock_datetime, sample_manifest):
        """Test that fetch_data defaults to the current year."""
        mock_now = datetime(2026, 6, 15, 12, 0, 0, tzinfo=pytz.utc)
        mock_datetime.now.return_value = mock_now
        mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)

        plugin = SantaTrackerPlugin(sample_manifest)
        plugin.config = {"enabled": True}
        result = plugin.fetch_data()

        assert result.available is True
        assert result.data["year"] == "2026"

    @patch("plugins.santa_tracker.datetime")
    def test_fetch_data_custom_year(self, mock_datetime, sample_manifest):
        """Test fetch_data with a custom year setting."""
        mock_now = datetime(2026, 12, 25, 0, 30, 0, tzinfo=pytz.utc)
        mock_datetime.now.return_value = mock_now
        mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)

        plugin = SantaTrackerPlugin(sample_manifest)
        plugin.config = {"enabled": True, "year": 2026}
        result = plugin.fetch_data()

        assert result.available is True
        assert result.data["year"] == "2026"

    @patch("plugins.santa_tracker.datetime")
    def test_fetch_data_has_all_variables(self, mock_datetime, sample_manifest, sample_config):
        """Test that fetch_data returns all variables declared in manifest."""
        mock_now = datetime(2026, 12, 25, 0, 30, 0, tzinfo=pytz.utc)
        mock_datetime.now.return_value = mock_now
        mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)

        plugin = SantaTrackerPlugin(sample_manifest)
        plugin.config = sample_config
        result = plugin.fetch_data()

        assert result.available is True
        manifest_path = Path(__file__).parent.parent / "manifest.json"
        with open(manifest_path) as f:
            manifest = json.load(f)
        simple_vars = manifest["variables"]["simple"]
        for var_name in simple_vars.keys():
            assert var_name in result.data, f"Variable '{var_name}' declared in manifest but not in data"

    @patch("plugins.santa_tracker.datetime")
    def test_fetch_data_locations_array(self, mock_datetime, sample_manifest, sample_config):
        """Test that locations array is populated correctly."""
        mock_now = datetime(2026, 12, 25, 0, 30, 0, tzinfo=pytz.utc)
        mock_datetime.now.return_value = mock_now
        mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)

        plugin = SantaTrackerPlugin(sample_manifest)
        plugin.config = sample_config
        result = plugin.fetch_data()

        assert "locations" in result.data
        locations = result.data["locations"]
        assert len(locations) == len(SANTA_LOCATIONS)
        for loc in locations:
            assert "name" in loc
            assert "state" in loc
            assert loc["state"] in ("visited", "current", "upcoming")


class TestGetSantaStatus:
    """Test the _get_santa_status helper function directly."""

    def test_before_christmas(self):
        """Test status before Christmas."""
        now_utc = datetime(2026, 12, 1, 0, 0, 0, tzinfo=pytz.utc)
        data = _get_santa_status(now_utc, 2026)
        assert "getting ready" in data["status"].lower()
        assert data["santa_location"] == "North Pole"
        assert data["next_stop"] == "Auckland, New Zealand"
        assert data["visited_count"] == "0"

    def test_after_christmas(self):
        """Test status after Christmas everywhere."""
        now_utc = datetime(2026, 12, 27, 0, 0, 0, tzinfo=pytz.utc)
        data = _get_santa_status(now_utc, 2026)
        assert "done" in data["status"].lower()
        assert data["santa_location"] == "North Pole"
        assert data["next_stop"] == ""
        assert data["visited_count"] == str(len(SANTA_LOCATIONS))

    def test_during_christmas_first_timezone(self):
        """Test when Christmas just started in Auckland (UTC+13)."""
        # Auckland is UTC+13, so Dec 25 00:00 NZDT = Dec 24 11:00 UTC
        now_utc = datetime(2026, 12, 24, 11, 30, 0, tzinfo=pytz.utc)
        data = _get_santa_status(now_utc, 2026)
        assert "delivering" in data["status"].lower()
        assert int(data["visited_count"]) >= 1

    def test_locations_list_length(self):
        """Test that locations list has correct length."""
        now_utc = datetime(2026, 12, 25, 12, 0, 0, tzinfo=pytz.utc)
        data = _get_santa_status(now_utc, 2026)
        assert len(data["locations"]) == len(SANTA_LOCATIONS)

    def test_location_states_valid(self):
        """Test that all location states are valid values."""
        now_utc = datetime(2026, 12, 25, 12, 0, 0, tzinfo=pytz.utc)
        data = _get_santa_status(now_utc, 2026)
        for loc in data["locations"]:
            assert loc["state"] in ("visited", "current", "upcoming")

    def test_progress_percent_range(self):
        """Test that progress percent is between 0 and 100."""
        for day in range(20, 28):
            now_utc = datetime(2026, 12, day, 12, 0, 0, tzinfo=pytz.utc)
            data = _get_santa_status(now_utc, 2026)
            pct = int(data["progress_percent"])
            assert 0 <= pct <= 100

    def test_total_locations_constant(self):
        """Test that total_locations matches SANTA_LOCATIONS."""
        now_utc = datetime(2026, 12, 25, 12, 0, 0, tzinfo=pytz.utc)
        data = _get_santa_status(now_utc, 2026)
        assert data["total_locations"] == str(len(SANTA_LOCATIONS))


class TestFormattedDisplay:
    """Test get_formatted_display output."""

    @patch("plugins.santa_tracker.datetime")
    def test_formatted_display_returns_six_lines(self, mock_datetime, sample_manifest, sample_config):
        """Test formatted display returns exactly 6 lines."""
        mock_now = datetime(2026, 12, 25, 12, 0, 0, tzinfo=pytz.utc)
        mock_datetime.now.return_value = mock_now
        mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)

        plugin = SantaTrackerPlugin(sample_manifest)
        plugin.config = sample_config
        lines = plugin.get_formatted_display()

        assert lines is not None
        assert len(lines) == 6

    @patch("plugins.santa_tracker.datetime")
    def test_formatted_display_line_length(self, mock_datetime, sample_manifest, sample_config):
        """Test that each formatted display line is at most 22 characters."""
        mock_now = datetime(2026, 12, 25, 12, 0, 0, tzinfo=pytz.utc)
        mock_datetime.now.return_value = mock_now
        mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)

        plugin = SantaTrackerPlugin(sample_manifest)
        plugin.config = sample_config
        lines = plugin.get_formatted_display()

        assert lines is not None
        for i, line in enumerate(lines):
            assert len(line) <= 22, f"Line {i} is {len(line)} chars: '{line}'"

    @patch("plugins.santa_tracker.datetime")
    def test_formatted_display_header(self, mock_datetime, sample_manifest, sample_config):
        """Test formatted display header."""
        mock_now = datetime(2026, 12, 25, 12, 0, 0, tzinfo=pytz.utc)
        mock_datetime.now.return_value = mock_now
        mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)

        plugin = SantaTrackerPlugin(sample_manifest)
        plugin.config = sample_config
        lines = plugin.get_formatted_display()

        assert lines is not None
        assert "SANTA TRACKER" in lines[0]

    @patch("plugins.santa_tracker.datetime")
    def test_formatted_display_when_fetch_fails(self, mock_datetime, sample_manifest):
        """Test formatted display returns None when fetch fails."""
        mock_datetime.now.side_effect = Exception("Test error")

        plugin = SantaTrackerPlugin(sample_manifest)
        plugin.config = {"enabled": True}
        lines = plugin.get_formatted_display()

        assert lines is None


class TestSantaLocations:
    """Test the SANTA_LOCATIONS data."""

    def test_locations_not_empty(self):
        """Test that SANTA_LOCATIONS is not empty."""
        assert len(SANTA_LOCATIONS) > 0

    def test_locations_have_three_elements(self):
        """Test each location tuple has 3 elements."""
        for loc in SANTA_LOCATIONS:
            assert len(loc) == 3, f"Location {loc} should have 3 elements"

    def test_locations_valid_timezones(self):
        """Test that all timezone names are valid pytz timezones."""
        for name, tz_name, _offset in SANTA_LOCATIONS:
            try:
                pytz.timezone(tz_name)
            except pytz.exceptions.UnknownTimeZoneError:
                pytest.fail(f"Invalid timezone '{tz_name}' for location '{name}'")

    def test_locations_ordered_by_offset(self):
        """Test that locations are ordered by UTC offset descending."""
        offsets = [offset for _, _, offset in SANTA_LOCATIONS]
        for i in range(len(offsets) - 1):
            assert offsets[i] >= offsets[i + 1], (
                f"Locations not ordered: offset {offsets[i]} at index {i} "
                f"should be >= {offsets[i + 1]} at index {i + 1}"
            )


class TestManifestMetadata:
    """Validate that manifest.json follows the rich variable metadata format."""

    @pytest.fixture(autouse=True)
    def load_manifest(self):
        manifest_path = Path(__file__).parent.parent / "manifest.json"
        with open(manifest_path) as f:
            self.manifest = json.load(f)

    def test_required_top_level_fields(self):
        for field in ("id", "name", "version"):
            assert field in self.manifest, f"Missing required field: {field}"

    def test_simple_variables_are_dict(self):
        simple = self.manifest["variables"]["simple"]
        assert isinstance(simple, dict), "variables.simple must be a dict, not a list"

    def test_each_simple_variable_has_description(self):
        for var_name, meta in self.manifest["variables"]["simple"].items():
            assert "description" in meta, f"Variable '{var_name}' missing 'description'"

    def test_each_simple_variable_has_type(self):
        for var_name, meta in self.manifest["variables"]["simple"].items():
            assert "type" in meta, f"Variable '{var_name}' missing 'type'"
            assert meta["type"] in ("string", "number", "boolean"), (
                f"Variable '{var_name}' has invalid type '{meta['type']}'"
            )

    def test_each_simple_variable_has_max_length(self):
        for var_name, meta in self.manifest["variables"]["simple"].items():
            assert "max_length" in meta, f"Variable '{var_name}' missing 'max_length'"
            assert isinstance(meta["max_length"], int), (
                f"Variable '{var_name}' max_length must be an int"
            )

    def test_each_simple_variable_has_example(self):
        for var_name, meta in self.manifest["variables"]["simple"].items():
            assert "example" in meta, f"Variable '{var_name}' missing 'example'"

    def test_each_simple_variable_has_group(self):
        groups = self.manifest["variables"].get("groups", {})
        for var_name, meta in self.manifest["variables"]["simple"].items():
            assert "group" in meta, f"Variable '{var_name}' missing 'group'"
            assert meta["group"] in groups, (
                f"Variable '{var_name}' references unknown group '{meta['group']}'"
            )

    def test_groups_have_labels(self):
        groups = self.manifest["variables"].get("groups", {})
        assert len(groups) > 0, "Must define at least one variable group"
        for group_id, group_meta in groups.items():
            assert "label" in group_meta, f"Group '{group_id}' missing 'label'"

    def test_array_max_lengths_kept_at_top_level(self):
        max_lengths = self.manifest.get("max_lengths", {})
        arrays = self.manifest["variables"].get("arrays", {})
        for array_name, array_meta in arrays.items():
            for field in array_meta.get("item_fields", []):
                key = f"{array_name}.*.{field}"
                assert key in max_lengths, (
                    f"Array field '{key}' missing from top-level max_lengths"
                )
