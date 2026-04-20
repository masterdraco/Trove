from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from trove.api.deps import current_user, db_session
from trove.api.indexers import IndexerOut, _to_out
from trove.clients.base import Protocol
from trove.indexers.base import Category
from trove.indexers.cardigann import load_definition_yaml
from trove.models.indexer import IndexerRow
from trove.models.user import User
from trove.services import catalog, indexer_registry

router = APIRouter()


class CatalogEntryOut(BaseModel):
    slug: str
    display_name: str
    description: str
    categories: list[Category]
    mirrors: list[str]
    default_mirror: str
    protocol: Protocol
    logo: str | None = None
    already_installed: bool


class CatalogInstallRequest(BaseModel):
    base_url: str = Field(min_length=1, max_length=512)
    name: str | None = Field(default=None, max_length=64)


@router.get("", response_model=list[CatalogEntryOut])
async def list_catalog(
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> list[CatalogEntryOut]:
    installed_slugs = set(
        session.exec(
            select(IndexerRow.catalog_slug).where(
                IndexerRow.catalog_slug.is_not(None)  # type: ignore[attr-defined]
            )
        ).all()
    )
    out: list[CatalogEntryOut] = []
    for entry in catalog.list_entries():
        out.append(
            CatalogEntryOut(
                slug=entry.slug,
                display_name=entry.display_name,
                description=entry.description,
                categories=entry.categories,
                mirrors=entry.mirrors,
                default_mirror=entry.default_mirror,
                protocol=entry.protocol,
                logo=entry.logo,
                already_installed=entry.slug in installed_slugs,
            )
        )
    return out
