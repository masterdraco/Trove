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
                IndexerRow.catalog_slug.is_not(None)  # type: ignore[union-attr]
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


def _dedup_name(session: Session, base: str) -> str:
    candidate = base
    suffix = 2
    while session.exec(select(IndexerRow).where(IndexerRow.name == candidate)).first() is not None:
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


@router.post("/{slug}", response_model=IndexerOut, status_code=status.HTTP_201_CREATED)
async def install_catalog_entry(
    slug: str,
    payload: CatalogInstallRequest,
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> IndexerOut:
    try:
        entry = catalog.get_entry(slug)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown_slug") from None

    if payload.base_url not in entry.mirrors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="base_url_not_in_catalog_mirrors",
        )

    try:
        yaml_text = catalog.read_yaml(slug)
        load_definition_yaml(yaml_text)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"catalog_yaml_broken: {e}",
        ) from e

    base_name = payload.name or entry.display_name
    name = _dedup_name(session, base_name)

    row = IndexerRow(
        name=name,
        type="cardigann",
        protocol=entry.protocol.value,
        base_url=payload.base_url,
        credentials_cipher=indexer_registry.encrypt_credentials({}),
        definition_yaml=yaml_text,
        enabled=True,
        priority=50,
        catalog_slug=slug,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return _to_out(row)
