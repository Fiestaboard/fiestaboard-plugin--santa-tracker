"""Board-geometry conformance for the santa_tracker plugin.

Runs the shared conformance suite (src/plugins/geometry_conformance.py) so
this plugin is held to the same "renders on every board" contract as core's
own plugins: a Flagship (22x6), a Note (15x3), and every note_array/panel
shape from 15x3 up to 120x24.
"""

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytz

from src.plugins.geometry_conformance import assert_board_conformance

from plugins.santa_tracker import SantaTrackerPlugin

_MANIFEST_PATH = Path(__file__).resolve().parent.parent / "manifest.json"


def _load_manifest() -> dict:
    with open(_MANIFEST_PATH) as f:
        return json.load(f)


def make_plugin() -> SantaTrackerPlugin:
    """Fresh, ready-to-render plugin.

    santa_tracker touches no network -- fetch_data is a pure computation over
    datetime.now() -- so there is nothing to stub beyond a fixed clock, which
    the caller patches around each call into the suite.
    """
    plugin = SantaTrackerPlugin(_load_manifest())
    plugin.config = {"enabled": True, "year": 2026}
    return plugin


@patch("plugins.santa_tracker.datetime")
def test_renders_on_every_board_shape(mock_datetime):
    """The plugin must render within bounds on every supported board shape.

    Frozen mid-Christmas-Day so both ``next_stop`` and ``status`` are
    populated -- the fullest content case, and the one most likely to
    overflow a narrow board.
    """
    mock_now = datetime(2026, 12, 25, 6, 0, 0, tzinfo=pytz.utc)
    mock_datetime.now.return_value = mock_now
    mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)

    assert_board_conformance(
        make_plugin,
        manifest=_load_manifest(),
        strict_growth=True,
        require_note_array_preview=True,
    )
