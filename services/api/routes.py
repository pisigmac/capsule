"""FastAPI routes for the Capsule API."""
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..shared.models import get_db, Capsule, Tag, CapsuleRelationship, init_db
from ..parser.parser import CapsuleParser, ParsedCapsule
from ..search.engine import SearchEngine
from ..sync.watcher import CapsuleSyncService

router = APIRouter()


# Pydantic schemas
class CapsuleCreate(BaseModel):
    topic: str = Field(..., min_length=3, max_length=500)
    content: str = Field(..., min_length=10)
    tags: List[str] = Field(default_factory=list)
    freshness: Optional[str] = None
    source: Optional[str] = None
    confidence: str = Field(default="medium", pattern="^(high|medium|low|hearsay)$")
    file_path: Optional[str] = None


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

    class Config:
        from_attributes = True


class RelationshipCreate(BaseModel):
    from_capsule_id: str
    to_capsule_id: str
    relationship_type: str = "relates_to"


class RelationshipResponse(BaseModel):
    id: str
    from_capsule_id: str
    to_capsule_id: str
    relationship_type: str
    created_at: Optional[str]


class SearchQuery(BaseModel):
    query: str
    tags: Optional[List[str]] = None
    confidence: Optional[str] = None
    archived: Optional[bool] = False
    limit: int = 50
    offset: int = 0


class ComposeRequest(BaseModel):
    tags: Optional[List[str]] = None
    query: Optional[str] = None
    confidence_min: Optional[str] = None
    max_tokens: int = 4000


# CRUD Routes
@router.post("/capsules", response_model=CapsuleResponse, status_code=201)
def create_capsule(data: CapsuleCreate, db: Session = Depends(get_db)):
    """Create a new capsule."""
    from datetime import datetime, timezone

    freshness = datetime.now(timezone.utc)
    if data.freshness:
        try:
            freshness = datetime.fromisoformat(data.freshness.replace("Z", "+00:00"))
        except ValueError:
            pass

    capsule = Capsule(
        topic=data.topic,
        content=data.content,
        freshness=freshness,
        source=data.source,
        confidence=data.confidence,
        file_path=data.file_path,
    )
    db.add(capsule)
    db.flush()

    for tag_name in data.tags:
        tag = db.query(Tag).filter(Tag.name == tag_name.lower().strip()).first()
        if not tag:
            tag = Tag(name=tag_name.lower().strip())
            db.add(tag)
            db.flush()
        capsule.tags.append(tag)

    db.commit()
    db.refresh(capsule)
    return CapsuleResponse(**capsule.to_dict())


@router.get("/capsules", response_model=List[CapsuleResponse])
def list_capsules(
    archived: Optional[bool] = Query(None),
    tag: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """List capsules with optional filters."""
    query = db.query(Capsule)

    if archived is not None:
        query = query.filter(Capsule.archived == archived)

    if tag:
        query = query.join(Capsule.tags).filter(Tag.name == tag.lower().strip())

    capsules = query.order_by(Capsule.updated_at.desc()).offset(offset).limit(limit).all()
    return [CapsuleResponse(**c.to_dict()) for c in capsules]


@router.get("/capsules/{capsule_id}", response_model=CapsuleResponse)
def get_capsule(capsule_id: str, db: Session = Depends(get_db)):
    """Get a single capsule by ID."""
    try:
        uuid_obj = UUID(capsule_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid capsule ID format")

    capsule = db.query(Capsule).filter(Capsule.id == uuid_obj).first()
    if not capsule:
        raise HTTPException(status_code=404, detail="Capsule not found")
    return CapsuleResponse(**capsule.to_dict())


@router.patch("/capsules/{capsule_id}", response_model=CapsuleResponse)
def update_capsule(capsule_id: str, data: CapsuleUpdate, db: Session = Depends(get_db)):
    """Update an existing capsule."""
    try:
        uuid_obj = UUID(capsule_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid capsule ID format")

    capsule = db.query(Capsule).filter(Capsule.id == uuid_obj).first()
    if not capsule:
        raise HTTPException(status_code=404, detail="Capsule not found")

    if data.topic is not None:
        capsule.topic = data.topic
    if data.content is not None:
        capsule.content = data.content
    if data.freshness is not None:
        from datetime import datetime, timezone
        try:
            capsule.freshness = datetime.fromisoformat(data.freshness.replace("Z", "+00:00"))
        except ValueError:
            pass
    if data.source is not None:
        capsule.source = data.source
    if data.confidence is not None:
        capsule.confidence = data.confidence
    if data.tags is not None:
        capsule.tags.clear()
        for tag_name in data.tags:
            tag = db.query(Tag).filter(Tag.name == tag_name.lower().strip()).first()
            if not tag:
                tag = Tag(name=tag_name.lower().strip())
                db.add(tag)
                db.flush()
            capsule.tags.append(tag)

    db.commit()
    db.refresh(capsule)
    return CapsuleResponse(**capsule.to_dict())


@router.delete("/capsules/{capsule_id}", status_code=204)
def delete_capsule(capsule_id: str, db: Session = Depends(get_db)):
    """Delete a capsule."""
    try:
        uuid_obj = UUID(capsule_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid capsule ID format")

    capsule = db.query(Capsule).filter(Capsule.id == uuid_obj).first()
    if not capsule:
        raise HTTPException(status_code=404, detail="Capsule not found")

    db.delete(capsule)
    db.commit()
    return None


@router.post("/capsules/{capsule_id}/archive", response_model=CapsuleResponse)
def archive_capsule(capsule_id: str, db: Session = Depends(get_db)):
    """Archive a capsule."""
    try:
        uuid_obj = UUID(capsule_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid capsule ID format")

    capsule = db.query(Capsule).filter(Capsule.id == uuid_obj).first()
    if not capsule:
        raise HTTPException(status_code=404, detail="Capsule not found")

    capsule.archived = True
    db.commit()
    db.refresh(capsule)
    return CapsuleResponse(**capsule.to_dict())


# Search Routes
@router.post("/search", response_model=List[CapsuleResponse])
def search_capsules(data: SearchQuery, db: Session = Depends(get_db)):
    """Search capsules by text query."""
    engine = SearchEngine(db)
    results = engine.search(
        query=data.query,
        tags=data.tags,
        confidence=data.confidence,
        archived=data.archived,
        limit=data.limit,
        offset=data.offset,
    )
    return [CapsuleResponse(**r) for r in results]


@router.post("/compose")
def compose_context(data: ComposeRequest, db: Session = Depends(get_db)):
    """Compose a context window from matching capsules."""
    engine = SearchEngine(db)
    context = engine.compose(
        tags=data.tags,
        query=data.query,
        confidence_min=data.confidence_min,
        max_tokens=data.max_tokens,
    )
    return {"context": context, "token_estimate": len(context.split())}


@router.get("/stale")
def get_stale_capsules(days: int = Query(90, ge=1), db: Session = Depends(get_db)):
    """Get capsules that haven't been updated in N days."""
    engine = SearchEngine(db)
    capsules = engine.stale_capsules(days=days)
    return {
        "count": len(capsules),
        "capsules": [CapsuleResponse(**c) for c in capsules],
    }


# Relationship Routes
@router.post("/relationships", response_model=RelationshipResponse, status_code=201)
def create_relationship(data: RelationshipCreate, db: Session = Depends(get_db)):
    """Create a relationship between two capsules."""
    try:
        from_uuid = UUID(data.from_capsule_id)
        to_uuid = UUID(data.to_capsule_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid capsule ID format")

    from_capsule = db.query(Capsule).filter(Capsule.id == from_uuid).first()
    to_capsule = db.query(Capsule).filter(Capsule.id == to_uuid).first()

    if not from_capsule or not to_capsule:
        raise HTTPException(status_code=404, detail="One or both capsules not found")

    rel = CapsuleRelationship(
        from_capsule_id=from_uuid,
        to_capsule_id=to_uuid,
        relationship_type=data.relationship_type,
    )
    db.add(rel)
    db.commit()
    db.refresh(rel)
    return RelationshipResponse(**rel.to_dict())


@router.get("/capsules/{capsule_id}/relationships")
def get_capsule_relationships(capsule_id: str, db: Session = Depends(get_db)):
    """Get all relationships for a capsule."""
    try:
        uuid_obj = UUID(capsule_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid capsule ID format")

    capsule = db.query(Capsule).filter(Capsule.id == uuid_obj).first()
    if not capsule:
        raise HTTPException(status_code=404, detail="Capsule not found")

    outgoing = [r.to_dict() for r in capsule.outgoing_relationships]
    incoming = [r.to_dict() for r in capsule.incoming_relationships]

    return {
        "outgoing": [RelationshipResponse(**r) for r in outgoing],
        "incoming": [RelationshipResponse(**r) for r in incoming],
    }


# Sync Routes
@router.post("/sync")
def sync_directory(path: Optional[str] = None, db: Session = Depends(get_db)):
    """Manually trigger a sync of a directory."""
    from ..shared.config import config
    from pathlib import Path

    watch_dirs = [path] if path else [str(config.capsules_dir)]
    service = CapsuleSyncService(watch_dirs=watch_dirs)
    count = service.initial_sync()
    return {"synced": count, "directories": watch_dirs}


# Tags
@router.get("/tags", response_model=List[dict])
def list_tags(db: Session = Depends(get_db)):
    """List all tags with capsule counts."""
    tags = db.query(Tag).all()
    return [{"name": t.name, "count": len(t.capsules)} for t in tags]
