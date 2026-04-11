from __future__ import annotations

from email.utils import format_datetime
from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlmodel import Session

from trove.api.deps import db_session
from trove.clients.base import Protocol
from trove.config import get_settings
from trove.indexers.base import Category
from trove.services import search_service

router = APIRouter()

CATEGORY_ID_MAP = {
    Category.MOVIES: 2000,
    Category.TV: 5000,
    Category.MUSIC: 3000,
    Category.BOOKS: 7000,
    Category.ANIME: 5070,
    Category.OTHER: 8000,
}


def _check_api_key(apikey: str | None) -> None:
    settings = get_settings()
    if settings.session_secret is None:
        raise HTTPException(status_code=500, detail="server not initialised")
    if not apikey or apikey != settings.session_secret[:32]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid apikey",
        )


def _caps_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<caps>\n"
        '  <server version="0.1" title="Trove" email="" url="" image=""/>\n'
        '  <limits max="100" default="50"/>\n'
        "  <searching>\n"
        '    <search available="yes" supportedParams="q,cat,limit"/>\n'
        '    <tv-search available="yes" supportedParams="q,cat,season,ep,limit"/>\n'
        '    <movie-search available="yes" supportedParams="q,cat,imdbid,limit"/>\n'
        "  </searching>\n"
        "  <categories>\n"
        '    <category id="2000" name="Movies"/>\n'
        '    <category id="3000" name="Audio"/>\n'
        '    <category id="5000" name="TV"/>\n'
        '    <category id="7000" name="Books"/>\n'
        "  </categories>\n"
        "</caps>\n"
    )


def _rss_item(hit: search_service.SearchHit) -> str:
    title = escape(hit.title)
    guid = escape(hit.infohash or hit.download_url or hit.title)
    link = escape(hit.download_url or "")
    size = hit.size or 0
    pub = hit.published_at or ""
    if pub:
        pub = escape(pub)
    cat_id = 8000
    if hit.category:
        try:
            cat_id = CATEGORY_ID_MAP[Category(hit.category.lower())]
        except (KeyError, ValueError):
            cat_id = 8000
    return (
        "<item>\n"
        f"  <title>{title}</title>\n"
        f'  <guid isPermaLink="false">{guid}</guid>\n'
        f"  <link>{link}</link>\n"
        f"  <pubDate>{pub}</pubDate>\n"
        f"  <size>{size}</size>\n"
        f'  <enclosure url="{link}" length="{size}" type="application/x-bittorrent"/>\n'
        f'  <torznab:attr name="category" value="{cat_id}"/>\n'
        f'  <torznab:attr name="size" value="{size}"/>\n'
        + (
            f'  <torznab:attr name="seeders" value="{hit.seeders}"/>\n'
            if hit.seeders is not None
            else ""
        )
        + "</item>\n"
    )


def _rss_xml(hits: list[search_service.SearchHit]) -> str:
    items = "".join(_rss_item(h) for h in hits)
    now = format_datetime(__import__("datetime").datetime.now(__import__("datetime").UTC))
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom" '
        'xmlns:torznab="http://torznab.com/schemas/2015/feed">\n'
        "<channel>\n"
        "  <title>Trove</title>\n"
        "  <description>Aggregated indexer search results</description>\n"
        f"  <pubDate>{now}</pubDate>\n"
        f"{items}"
        "</channel>\n"
        "</rss>\n"
    )


@router.get("/api")
async def torznab_api(
    t: str = Query("search"),
    apikey: str | None = Query(None),
    q: str = Query(""),
    cat: str = Query(""),
    limit: int = Query(50),
    session: Session = Depends(db_session),
) -> Response:
    _check_api_key(apikey)

    if t == "caps":
        return Response(content=_caps_xml(), media_type="application/xml")

    if not q:
        return Response(content=_rss_xml([]), media_type="application/xml")

    categories: list[Category] = []
    if cat:
        for cid in cat.split(","):
            cid = cid.strip()
            if not cid.isdigit():
                continue
            cat_int = int(cid)
            if 2000 <= cat_int < 3000:
                categories.append(Category.MOVIES)
            elif 3000 <= cat_int < 4000:
                categories.append(Category.MUSIC)
            elif 5000 <= cat_int < 6000:
                categories.append(Category.TV)
            elif 7000 <= cat_int < 8000:
                categories.append(Category.BOOKS)

    result = await search_service.run_search(
        session,
        q,
        categories=categories,
        protocol=Protocol.TORRENT,
        limit=limit,
    )
    return Response(content=_rss_xml(result.hits), media_type="application/xml")
