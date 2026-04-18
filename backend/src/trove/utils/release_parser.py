"""Release-title parsing helpers.

Currently exposes :func:`parse_release_group`, which extracts the
release group tag (e.g. ``FitGirl``, ``RARBG``, ``SubsPlease``) from
the end of a release title. Used by the search/browse response
layer to annotate hits with their group so the UI can colour
trusted/blocked groups differently.
"""

from __future__ import annotations

import re

# Common release groups — not used for filtering (that's a user choice
# via app_settings), just for documentation/reference.
KNOWN_GROUPS: frozenset[str] = frozenset(
    {
        # Game releases
        "fitgirl",
        "dodi",
        "razor1911",
        "codex",
        "flt",
        "plaza",
        "gog",
        "skidrow",
        "reloaded",
        "ali213",
        "tinyiso",
        "darksiders",
        "elamigos",
        "empress",
        "rune",
        "tenoke",
        "razordox",
        # Movie/TV scene/P2P groups
        "rarbg",
        "yts",
        "yify",
        "eztv",
        "ntb",
        "syncopy",
        "flux",
        "cakes",
        "nosivid",
        "ethel",
        "ion10",
        "successfulcrab",
        "rovers",
        # Anime
        "subsplease",
        "erai-raws",
        "judas",
        "chotab",
    }
)

# Match "-GROUP" or "-GROUP.ext" at the end of a title. The group tag
# must start with a letter so we don't mis-identify release years
# ("Movie.Name-2024") as groups.
_TAIL_RE = re.compile(r"-([A-Za-z][A-Za-z0-9_-]{1,29})(?:\.[A-Za-z0-9]{1,5})?\s*$")


def parse_release_group(title: str) -> str | None:
    """Extract the release group tag from a release title.

    Returns the tag as originally cased (for display) when found, or
    ``None`` if no trailing group pattern is detected. The match is
    intentionally anchored to the tail of the title to avoid grabbing
    intermediate dash-separated words.
    """
    if not title:
        return None
    match = _TAIL_RE.search(title)
    if not match:
        return None
    return match.group(1)
