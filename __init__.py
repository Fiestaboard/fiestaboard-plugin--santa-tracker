"""Santa Tracker plugin for FiestaBoard.

Tracks Santa's travel across the world as he delivers presents by monitoring
when midnight of December 25th hits famous/remarkable world locations in each timezone.
"""

import logging
from datetime import datetime
from typing import Any, Dict

import pytz

from src.plugins.base import PluginBase, PluginResult
from src.text_to_board import count_tiles

logger = logging.getLogger(__name__)

# Fallback geometry when no board is bound (self.board is None -- unit tests,
# legacy callers). Matches the Flagship, the platform's historical default.
_DEFAULT_WIDTH = 22
_DEFAULT_HEIGHT = 6

# Most-important-first. A short board (a Note, 15x3) cannot show everything;
# the tracking info -- where Santa is, how far along, where he's headed --
# is what a user actually wants, so it survives before the title or the
# status blurb does.
_PRIORITY = ["at", "progress", "next", "status", "title"]

# Reading order for whichever items survive _PRIORITY's cut.
_NATURAL_ORDER = ["title", "status", "at", "next", "progress"]


def _fit(text: str, width: int) -> str:
    """Tile-safe truncate *text* to *width* tiles, then center it.

    Measured in tiles (``count_tiles``), not characters, so a colour marker
    would count as one tile rather than four -- this plugin emits none today,
    but the measure is the board's own and should not silently drift from it.
    """
    while count_tiles(text) > width:
        text = text[:-1]
    return text.center(width)


# Ordered list of locations by UTC offset (most ahead first, i.e. earliest to hit Dec 25).
# Each entry: (display_name, timezone_name, utc_offset_hours)
SANTA_LOCATIONS = [
    ("Auckland, New Zealand", "Pacific/Auckland", 13),
    ("Sydney, Australia", "Australia/Sydney", 11),
    ("Tokyo, Japan", "Asia/Tokyo", 9),
    ("Beijing, China", "Asia/Shanghai", 8),
    ("Bangkok, Thailand", "Asia/Bangkok", 7),
    ("Dhaka, Bangladesh", "Asia/Dhaka", 6),
    ("Delhi, India", "Asia/Kolkata", 5),
    ("Dubai, UAE", "Asia/Dubai", 4),
    ("Moscow, Russia", "Europe/Moscow", 3),
    ("Athens, Greece", "Europe/Athens", 2),
    ("Paris, France", "Europe/Paris", 1),
    ("London, England", "Europe/London", 0),
    ("Reykjavik, Iceland", "Atlantic/Reykjavik", 0),
    ("São Paulo, Brazil", "America/Sao_Paulo", -3),
    ("Buenos Aires, Argentina", "America/Argentina/Buenos_Aires", -3),
    ("New York, USA", "America/New_York", -5),
    ("Chicago, USA", "America/Chicago", -6),
    ("Denver, USA", "America/Denver", -7),
    ("Los Angeles, USA", "America/Los_Angeles", -8),
    ("Anchorage, USA", "America/Anchorage", -9),
    ("Honolulu, USA", "Pacific/Honolulu", -10),
]


def _get_santa_status(now_utc: datetime, year: int) -> dict[str, Any]:
    """Determine Santa's current status based on UTC time.

    Args:
        now_utc: Current time in UTC (timezone-aware).
        year: The Christmas year to track.

    Returns:
        Dictionary with Santa's status data.
    """
    visited = []
    current_location = None
    upcoming = []

    for display_name, tz_name, _offset in SANTA_LOCATIONS:
        tz = pytz.timezone(tz_name)
        local_now = now_utc.astimezone(tz)
        local_christmas = tz.localize(datetime(year, 12, 25, 0, 0, 0))
        local_christmas_end = tz.localize(datetime(year, 12, 26, 0, 0, 0))

        if local_now >= local_christmas_end:
            visited.append(display_name)
        elif local_now >= local_christmas:
            if current_location is None:
                current_location = display_name
            visited.append(display_name)
        else:
            upcoming.append(display_name)

    # Determine overall status
    total = len(SANTA_LOCATIONS)
    visited_count = len(visited)

    if visited_count == 0:
        status = f"Santa is getting ready for {year}"
        santa_location = "North Pole"
        next_stop = upcoming[0] if upcoming else "Unknown"
    elif visited_count >= total:
        status = f"Santa is done for {year}"
        santa_location = "North Pole"
        next_stop = ""
    else:
        status = "Santa is delivering presents!"
        santa_location = current_location or visited[-1]
        next_stop = upcoming[0] if upcoming else ""

    last_visited = visited[-1] if visited else ""
    progress_percent = round((visited_count / total) * 100)

    return {
        "status": status,
        "santa_location": santa_location,
        "last_visited": last_visited,
        "next_stop": next_stop,
        "visited_count": str(visited_count),
        "total_locations": str(total),
        "progress_percent": str(progress_percent),
        "year": str(year),
        "locations": [
            {
                "name": name,
                "state": (
                    "visited"
                    if name in visited
                    else "current"
                    if name == current_location
                    else "upcoming"
                ),
            }
            for name, _tz, _off in SANTA_LOCATIONS
        ],
    }


class SantaTrackerPlugin(PluginBase):
    """Track Santa's journey around the world on Christmas Eve/Day.

    Monitors when midnight of December 25th arrives at famous world locations
    across every timezone. Shows current location, next stop, and progress.
    """

    @property
    def plugin_id(self) -> str:
        return "santa_tracker"

    def validate_config(self, config: dict[str, Any]) -> list[str]:
        errors = []
        year = config.get("year")
        if year is not None:
            if not isinstance(year, int) or year < 2024 or year > 2100:
                errors.append("Year must be an integer between 2024 and 2100")
        return errors

    def fetch_data(self) -> PluginResult:
        try:
            now_utc = datetime.now(pytz.utc)
            year = self.config.get("year", now_utc.year)

            data = _get_santa_status(now_utc, year)
            return PluginResult(available=True, data=data, formatted_lines=self._format_display(data))
        except Exception as e:
            logger.exception("Error fetching Santa tracker data")
            return PluginResult(available=False, error=str(e))

    def get_formatted_display(self) -> list[str] | None:
        result = self.fetch_data()
        if not result.available or not result.data:
            return None
        return result.formatted_lines

    def _format_display(self, data: dict[str, Any]) -> list[str]:
        """Format Santa's status for the board, adapted to its size.

        ``self.board`` is None outside a board-scoped render (unit tests,
        legacy callers) -- fall back to the Flagship 22x6 layout. Width and
        height are always derived from the board, never hardcoded: a Note
        (15x3) keeps only the highest-priority lines (see ``_PRIORITY``),
        while a taller board (a note_array/panel) uses its extra rows to
        show more of the journey itself rather than sitting blank.
        """
        board = self.board
        width = board.cols if board else _DEFAULT_WIDTH
        height = board.rows if board else _DEFAULT_HEIGHT

        status = data.get("status", "")
        location = data.get("santa_location", "")
        next_stop = data.get("next_stop", "")
        progress = data.get("progress_percent", "0")
        locations = data.get("locations") or []

        items: dict[str, str] = {}
        if location:
            items["at"] = f"At: {location}"
        items["progress"] = f"Progress: {progress}%"
        if next_stop:
            items["next"] = f"Next: {next_stop}"
        if status:
            items["status"] = status
        items["title"] = "SANTA TRACKER"

        kept = set(name for name in _PRIORITY if name in items)
        # Trim lowest-priority items first until what remains fits height.
        for name in reversed(_PRIORITY):
            if len(kept) <= height:
                break
            kept.discard(name)

        lines = [_fit(items[name], width) for name in _NATURAL_ORDER if name in kept]

        # Reflow into any rows still left: one stop per row, in route order,
        # so a taller board (note_array/panel) shows more of the journey
        # instead of leaving the extra rows blank.
        remaining = height - len(lines)
        if remaining > 0 and locations:
            markers = {"visited": "x", "current": ">", "upcoming": " "}
            for entry in locations:
                if remaining <= 0:
                    break
                name = str(entry.get("name", ""))
                marker = markers.get(entry.get("state"), " ")
                lines.append(_fit(f"{marker} {name}", width))
                remaining -= 1

        return lines


Plugin = SantaTrackerPlugin
