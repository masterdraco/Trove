from __future__ import annotations

import re

# Match a 4-digit year between 1900 and 2099, surrounded by dot, space,
# parens, brackets, or dash. Used to extract movie years from release titles.
YEAR_RE = re.compile(r"(?:^|[ .(\[-])(19\d{2}|20\d{2})(?:[ .)\]-]|$)")

# SxxExx pattern — used to distinguish series from movies
SEASON_EPISODE_RE = re.compile(r"\bS(\d{1,2})E(\d{1,3})\b", re.IGNORECASE)
SEASON_ONLY_RE = re.compile(r"\bS\d{1,2}\b", re.IGNORECASE)

_STRIP = re.compile(r"[^a-z0-9]+")


def extract_year(title: str) -> int | None:
    """Return the first plausible year found in the title, or None.

    Picks the *last* year in the string because "Blade Runner 2049 (2017)" is
    a 2017 movie about the year 2049 — the trailing year is the release year.
    """
    matches = YEAR_RE.findall(title)
    if not matches:
        return None
    try:
        return int(matches[-1])
    except ValueError:
        return None


def extract_episode(title: str) -> tuple[int, int] | None:
    """Return ``(season, episode)`` parsed from the title, or ``None``."""
    m = SEASON_EPISODE_RE.search(title)
    if not m:
        return None
    try:
        return int(m.group(1)), int(m.group(2))
    except ValueError:
        return None


def normalized_show_prefix(title: str) -> str:
    """Return the title up to the SxxExx marker, lowercased and alnum-only.

    A 4-digit year embedded in the prefix is stripped, so
    "The.Boys.2019.S01E01" and "The.Boys.S01E01" produce the same
    normalized show name. This keeps the dedup key stable across
    release groups that disambiguate by year and those that don't.
    """
    m = SEASON_EPISODE_RE.search(title)
    prefix = title[: m.start()] if m else title
    # Drop any 4-digit years sitting between separators.
    prefix = YEAR_RE.sub(" ", prefix)
    return _STRIP.sub("", prefix.lower())[:40]


def normalized_movie_name(title: str) -> str:
    """Return the title up to the *last* year in the string, lowercased
    and alnum-only. Matches :func:`extract_year`'s "last year wins" rule
    so "Blade Runner 2049 (2017)" normalises to ``bladerunner2049``.
    """
    matches = list(YEAR_RE.finditer(title))
    prefix = title[: matches[-1].start()] if matches else title
    return _STRIP.sub("", prefix.lower())[:40]


def looks_like_series(title: str) -> bool:
    return bool(SEASON_EPISODE_RE.search(title) or SEASON_ONLY_RE.search(title))


def looks_like_movie(title: str) -> bool:
    return extract_year(title) is not None and not looks_like_series(title)
