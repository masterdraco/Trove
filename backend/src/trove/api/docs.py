from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from trove.api.deps import current_user
from trove.models.user import User

router = APIRouter()

DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"

# Match leading YAML frontmatter
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


class DocMeta(BaseModel):
    slug: str
    title: str
    order: int
    description: str


class DocContent(BaseModel):
    slug: str
    title: str
    order: int
    description: str
    markdown: str


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    fm_text = match.group(1)
    body = text[match.end() :]
    fm: dict[str, str] = {}
    for line in fm_text.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        fm[key.strip()] = value.strip().strip('"').strip("'")
    return fm, body


def _slug_from_filename(name: str) -> str:
    # "01-getting-started.md" -> "getting-started"
    stem = name.rsplit(".", 1)[0]
    parts = stem.split("-", 1)
    if len(parts) == 2 and parts[0].isdigit():
        return parts[1]
    return stem


def _load_all() -> list[DocContent]:
    if not DOCS_DIR.is_dir():
        return []
    out: list[DocContent] = []
    for path in sorted(DOCS_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        fm, body = _parse_frontmatter(text)
        slug = _slug_from_filename(path.name)
        try:
            order = int(fm.get("order", "999"))
        except ValueError:
            order = 999
        out.append(
            DocContent(
                slug=slug,
                title=fm.get("title", slug),
                order=order,
                description=fm.get("description", ""),
                markdown=body.lstrip(),
            )
        )
    out.sort(key=lambda d: (d.order, d.slug))
    return out


@router.get("", response_model=list[DocMeta])
async def list_docs(
    _user: User = Depends(current_user),
) -> list[DocMeta]:
    docs = _load_all()
    return [
        DocMeta(slug=d.slug, title=d.title, order=d.order, description=d.description)
        for d in docs
    ]


@router.get("/{slug}", response_model=DocContent)
async def get_doc(
    slug: str,
    _user: User = Depends(current_user),
) -> DocContent:
    for doc in _load_all():
        if doc.slug == slug:
            return doc
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="doc_not_found")
