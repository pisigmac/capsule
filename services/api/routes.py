"""FastAPI routes for the Capsule API."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..search.engine import SearchEngine
from ..shared.models import Capsule, CapsuleRelationship, Tag, get_db, utcnow
from ..store.store import CapsuleStore, DuplicateContentError, StoreError

router = APIRouter()


class CapsuleCreate(BaseModel):
    topic: str = Field(..., min_length=3, max_length=500)
    content: str = Field(..., min_length=10)
    tags: List[str] = Field(default_factory=list)
    freshness: Optional[str] = None
    source: Optional[str] = None
    confidence: str = Field(default="medium", pattern="^(high|medium|low|hearsay)$")


class CapsuleUpdate(BaseModel):
    topic: Optional[str] = Field(None, min_length=3, max_length=500)
    content: Optional[str] = Field(None, min_length=10)
    tags: Optional[List[str]] = None
    freshness: Optional[str] = None
    source: Optional[str] = None
    confidence: Optional[str] = Field(None, pattern="^(high|medium|low|hearsay)$")


class CapsuleResponse(BaseModel):
    id: str
    topic: str
    content: str
    tags: List[str]
    freshness: Optional[str]
    source: Optional[str]
    confidence: str
    created_at: Optional[str]
    updated_at: Optional[str]
    archived: bool
    file_path: Optional[str]
    content_hash: Optional[str] = None
    deduped: bool = False


class CapsuleListResponse(BaseModel):
    items: List[CapsuleResponse]
    total: int
    limit: int
    offset: int


class RelationshipCreate(BaseModel):
    from_capsule_id: str
    to_capsule_id: str
    relationship_type: str = Field(default="relates_to", max_length=50)


class RelationshipResponse(BaseModel):
    id: str
    from_capsule_id: str
    to_capsule_id: str
    relationship_type: str
    created_at: Optional[str]


class SearchQuery(BaseModel):
    query: str = ""
    tags: Optional[List[str]] = None
    confidence: Optional[str] = None
    archived: Optional[bool] = False
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)
    mode: str = Field(default="fts", pattern="^(fts|semantic|hybrid)$")


class ComposeRequest(BaseModel):
    tags: Optional[List[str]] = None
    query: Optional[str] = None
    confidence_min: Optional[str] = None
    max_tokens: int = Field(default=4000, ge=50, le=128000)
    mode: str = Field(default="fts", pattern="^(fts|semantic|hybrid)$")


def get_store(db: Session = Depends(get_db)) -> CapsuleStore:
    return CapsuleStore(db)


def parse_freshness(value: Optional[str]):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid freshness timestamp") from exc


def require_uuid(value: str) -> str:
    try:
        return str(UUID(value))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid capsule ID format") from exc


def raise_store_error(exc: StoreError) -> None:
    if isinstance(exc, DuplicateContentError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if "not found" in str(exc).lower():
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/capsules", response_model=CapsuleResponse)
def create_capsule(data: CapsuleCreate, store: CapsuleStore = Depends(get_store)):
    try:
        capsule = store.create(
            topic=data.topic,
            content=data.content,
            tags=data.tags,
            source=data.source,
            confidence=data.confidence,
            freshness=parse_freshness(data.freshness) or utcnow(),
        )
    except StoreError as exc:
        raise_store_error(exc)
    store.db.commit()
    store.db.refresh(capsule)
    payload = CapsuleResponse(**capsule.to_dict())
    status = 200 if payload.deduped else 201
    return JSONResponse(status_code=status, content=payload.model_dump())


@router.get("/capsules", response_model=CapsuleListResponse)
def list_capsules(
    archived: Optional[bool] = Query(False),
    tag: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    query = db.query(Capsule)
    if archived is not None:
        query = query.filter(Capsule.archived == archived)
    if tag:
        query = query.filter(Capsule.tags.any(Tag.name == tag.lower().strip()))
    total = query.count()
    capsules = query.order_by(Capsule.updated_at.desc()).offset(offset).limit(limit).all()
    return CapsuleListResponse(
        items=[CapsuleResponse(**c.to_dict()) for c in capsules],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/capsules/{capsule_id}", response_model=CapsuleResponse)
def get_capsule(capsule_id: str, store: CapsuleStore = Depends(get_store)):
    capsule = store.get(require_uuid(capsule_id))
    if not capsule:
        raise HTTPException(status_code=404, detail="Capsule not found")
    return CapsuleResponse(**capsule.to_dict())


@router.patch("/capsules/{capsule_id}", response_model=CapsuleResponse)
def update_capsule(capsule_id: str, data: CapsuleUpdate, store: CapsuleStore = Depends(get_store)):
    try:
        capsule = store.update(
            require_uuid(capsule_id),
            topic=data.topic,
            content=data.content,
            tags=data.tags,
            source=data.source,
            confidence=data.confidence,
            freshness=parse_freshness(data.freshness),
        )
    except StoreError as exc:
        raise_store_error(exc)
    store.db.commit()
    store.db.refresh(capsule)
    return CapsuleResponse(**capsule.to_dict())


@router.delete("/capsules/{capsule_id}", status_code=204)
def delete_capsule(capsule_id: str, store: CapsuleStore = Depends(get_store)):
    store.delete(require_uuid(capsule_id))
    store.db.commit()
    return None


@router.post("/capsules/{capsule_id}/archive", response_model=CapsuleResponse)
def archive_capsule(capsule_id: str, store: CapsuleStore = Depends(get_store)):
    capsule = store.archive(require_uuid(capsule_id))
    store.db.commit()
    store.db.refresh(capsule)
    return CapsuleResponse(**capsule.to_dict())


@router.post("/search", response_model=List[CapsuleResponse])
def search_capsules(data: SearchQuery, db: Session = Depends(get_db)):
    engine = SearchEngine(db)
    results = engine.search(
        query=data.query,
        tags=data.tags,
        confidence=data.confidence,
        archived=data.archived,
        limit=data.limit,
        offset=data.offset,
        mode=data.mode,
    )
    return [CapsuleResponse(**r) for r in results]


@router.post("/compose")
def compose_context(data: ComposeRequest, db: Session = Depends(get_db)):
    engine = SearchEngine(db)
    return engine.compose(
        tags=data.tags,
        query=data.query,
        confidence_min=data.confidence_min,
        max_tokens=data.max_tokens,
        mode=data.mode,
    )


@router.get("/stale")
def get_stale_capsules(days: int = Query(90, ge=1, le=3650), db: Session = Depends(get_db)):
    engine = SearchEngine(db)
    capsules = engine.stale_capsules(days=days)
    return {
        "count": len(capsules),
        "capsules": [CapsuleResponse(**c) for c in capsules],
    }


@router.post("/relationships", response_model=RelationshipResponse, status_code=201)
def create_relationship(data: RelationshipCreate, store: CapsuleStore = Depends(get_store)):
    rel = store.link(
        require_uuid(data.from_capsule_id),
        require_uuid(data.to_capsule_id),
        data.relationship_type,
    )
    store.db.commit()
    store.db.refresh(rel)
    return RelationshipResponse(**rel.to_dict())


@router.get("/capsules/{capsule_id}/relationships")
def get_capsule_relationships(capsule_id: str, db: Session = Depends(get_db)):
    uid = require_uuid(capsule_id)
    capsule = db.query(Capsule).filter(Capsule.id == uid).first()
    if not capsule:
        raise HTTPException(status_code=404, detail="Capsule not found")
    return {
        "outgoing": [RelationshipResponse(**r.to_dict()) for r in capsule.outgoing_relationships],
        "incoming": [RelationshipResponse(**r.to_dict()) for r in capsule.incoming_relationships],
    }


@router.post("/sync")
def sync_directory(store: CapsuleStore = Depends(get_store)):
    count = store.reconcile()
    store.db.commit()
    return {"synced": count, "directory": str(store.capsules_dir)}


@router.get("/tags")
def list_tags(db: Session = Depends(get_db)):
    tags = db.query(Tag).order_by(Tag.name.asc()).all()
    return [{"name": t.name, "count": len(t.capsules)} for t in tags]


@router.get("/status")
def status(db: Session = Depends(get_db)):
    from ..shared.config import config
    from ..shared.models import CapsuleRelationship

    engine = SearchEngine(db)
    counts = engine.counts()
    rel_count = db.query(CapsuleRelationship).count()
    return {
        **counts,
        "relationships": rel_count,
        "database": config.database_url,
        "dialect": db.get_bind().dialect.name,
        "capsules_dir": str(config.capsules_dir.resolve()),
    }
