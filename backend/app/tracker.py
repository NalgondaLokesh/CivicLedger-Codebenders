"""Application tracker: saved schemes, document checklist and reminders.

Tracked items live in the ``tracked_applications`` collection. Scheme details
are snapshotted at creation time so the tracker keeps working if the scheme
document is later edited in MongoDB Atlas.
"""

import re
from datetime import date, datetime, time, timedelta, timezone
from typing import Annotated, Any, Literal

from bson import Binary, ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from pymongo import ReturnDocument

from .auth import require_user
from .db import get_db

TrackerStatus = Literal["documents_pending", "ready_to_apply", "applied", "follow_up"]
ReminderState = Literal["overdue", "due_soon", "scheduled"]

DocName = Annotated[str, Field(max_length=200)]
DocList = Annotated[list[DocName], Field(max_length=100)]
Notes = Annotated[str, Field(max_length=500)]

router = APIRouter(prefix="/api/tracker", tags=["tracker"])

_AADHAAR_RE = re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}\b")
_PAN_RE = re.compile(r"[A-Z]{5}\d{4}[A-Z]")

_indexes_ready = False


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class Attachment(BaseModel):
    """Attachment metadata. `file_id` links to stored bytes in tracker_files;
    legacy entries without file_id are metadata-only."""

    name: str = Field(min_length=1, max_length=255)
    size: int = Field(ge=0)
    type: str = Field(default="", max_length=100)
    file_id: str | None = Field(default=None, max_length=64)


class TrackerItemCreate(BaseModel):
    slug: str = Field(min_length=1, max_length=120)
    checked_documents: DocList = Field(default_factory=list)
    reminder_date: date | None = None
    notes: Notes | None = None
    attachments: list[Attachment] = Field(default_factory=list, max_length=20)


class TrackerItemUpdate(BaseModel):
    status: TrackerStatus | None = None
    checked_documents: DocList | None = None
    reminder_date: date | None = None
    notes: Notes | None = None
    attachments: list[Attachment] | None = Field(default=None, max_length=20)


class TrackerItemOut(BaseModel):
    id: str
    slug: str
    name: str
    status: TrackerStatus
    official_url: str | None = None
    last_verified_date: str | None = None
    required_documents: list[str] = []
    application_steps: list[str] = []
    checked_documents: list[str] = []
    attachments: list[Attachment] = []
    reminder_date: str | None = None
    reminder_state: ReminderState | None = None
    notes: str | None = None
    created_at: str
    updated_at: str


class TrackerListOut(BaseModel):
    items: list[TrackerItemOut]
    total: int


class ChecklistDocument(BaseModel):
    name: str
    key: str
    schemes: list[str]
    checked: bool
    total_items: int


class ChecklistOut(BaseModel):
    documents: list[ChecklistDocument]
    checked_count: int
    total_count: int
    progress_percent: int = Field(ge=0, le=100)


class ChecklistToggle(BaseModel):
    document: str = Field(min_length=1, max_length=200)
    checked: bool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def sanitize_notes(text: str) -> str:
    """Mask Aadhaar-like and PAN-like numbers so no sensitive IDs are stored."""
    cleaned = _AADHAAR_RE.sub("[removed]", text)
    cleaned = _PAN_RE.sub("[removed]", cleaned)
    return cleaned.strip()


def _clean_notes(notes: str | None) -> str | None:
    if notes is None:
        return None
    return sanitize_notes(notes) or None


def normalize_doc(name: str) -> str:
    """Lowercase, trim and collapse internal whitespace."""
    return " ".join(name.split()).lower()


def _clean_doc_keys(names: list[str]) -> list[str]:
    """Normalize document names and drop duplicates, preserving order."""
    return list(dict.fromkeys(k for k in (normalize_doc(n) for n in names) if k))


def reminder_state(reminder_date: date | None, today: date) -> ReminderState | None:
    if reminder_date is None:
        return None
    if reminder_date < today:
        return "overdue"
    if reminder_date <= today + timedelta(days=7):
        return "due_soon"
    return "scheduled"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc_iso(value: datetime) -> str:
    # Mongo returns naive datetimes; they were written as UTC.
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _to_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):  # must precede date: datetime subclasses date
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _iso_date(value: Any) -> str | None:
    parsed = _to_date(value)
    return parsed.isoformat() if parsed else None


def _date_to_mongo(value: date | None) -> datetime | None:
    # BSON cannot encode datetime.date, so store midnight UTC instead.
    return None if value is None else datetime.combine(value, time.min)


def _str_list(value: Any) -> list[str]:
    return [str(item) for item in (value or [])]


def _sort_created(doc: dict[str, Any]) -> datetime:
    return doc.get("created_at") or datetime.min


def _reminder_sort_key(doc: dict[str, Any]) -> tuple[bool, date]:
    # Nulls last, then soonest first.
    reminder = _to_date(doc.get("reminder_date"))
    return (reminder is None, reminder or date.max)


def _parse_id(item_id: str) -> ObjectId:
    try:
        return ObjectId(item_id)
    except (InvalidId, TypeError):
        raise HTTPException(status_code=404, detail="Tracker item not found")


def _scope(user_id: str) -> dict[str, Any]:
    """Per-user data scope. 'guest' sees legacy docs written before scoping
    existed plus anything tagged guest; named demo accounts see only their own.
    """
    uid = (user_id or "guest").strip() or "guest"
    if uid != "guest":
        return {"user_id": uid[:120]}
    return {"$or": [{"user_id": "guest"}, {"user_id": {"$exists": False}}]}


async def _tracked_collection() -> Any:
    global _indexes_ready
    coll = get_db()["tracked_applications"]
    if not _indexes_ready:
        await coll.create_index("slug")
        await coll.create_index("status")
        _indexes_ready = True
    return coll


def _to_out(doc: dict[str, Any], today: date) -> TrackerItemOut:
    reminder = _to_date(doc.get("reminder_date"))
    return TrackerItemOut(
        id=str(doc["_id"]),
        slug=doc.get("slug", ""),
        name=doc.get("name", ""),
        status=doc.get("status", "documents_pending"),
        official_url=doc.get("official_url"),
        last_verified_date=_iso_date(doc.get("last_verified_date")),
        required_documents=_str_list(doc.get("required_documents")),
        application_steps=_str_list(doc.get("application_steps")),
        checked_documents=_str_list(doc.get("checked_documents")),
        attachments=[Attachment(**a) for a in (doc.get("attachments") or []) if isinstance(a, dict)],
        reminder_date=reminder.isoformat() if reminder else None,
        reminder_state=reminder_state(reminder, today),
        notes=doc.get("notes"),
        created_at=_as_utc_iso(doc["created_at"]),
        updated_at=_as_utc_iso(doc["updated_at"]),
    )


def _build_checklist(items: list[dict[str, Any]]) -> ChecklistOut:
    docs: dict[str, dict[str, Any]] = {}
    for item in items:
        slug = item.get("slug", "")
        checked_keys = set(_clean_doc_keys(_str_list(item.get("checked_documents"))))
        listed: set[str] = set()
        for name in _str_list(item.get("required_documents")):
            key = normalize_doc(name)
            if not key or key in listed:
                continue
            listed.add(key)
            entry = docs.get(key)
            if entry is None:
                entry = {
                    "name": name.strip(),
                    "key": key,
                    "schemes": [],
                    "checked": False,
                    "total_items": 0,
                }
                docs[key] = entry
            if slug not in entry["schemes"]:
                entry["schemes"].append(slug)
            entry["total_items"] += 1
            if key in checked_keys:
                entry["checked"] = True

    documents = [ChecklistDocument(**e) for e in sorted(docs.values(), key=lambda e: e["key"])]
    total = len(documents)
    checked = sum(1 for d in documents if d.checked)
    percent = round(checked * 100 / total) if total else 0
    return ChecklistOut(
        documents=documents,
        checked_count=checked,
        total_count=total,
        progress_percent=min(100, max(0, percent)),
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=TrackerListOut)
async def list_tracked(
    status: TrackerStatus | None = Query(default=None),
    user_id: str = Depends(require_user),
) -> TrackerListOut:
    coll = await _tracked_collection()
    query: dict[str, Any] = _scope(user_id)
    if status:
        query["status"] = status
    docs = await coll.find(query).to_list(length=None)
    # Stable sorts: created_at desc first, then reminder asc with nulls last.
    docs.sort(key=_sort_created, reverse=True)
    docs.sort(key=_reminder_sort_key)
    today = _utcnow().date()
    items = [_to_out(d, today) for d in docs]
    return TrackerListOut(items=items, total=len(items))


@router.post("", response_model=TrackerItemOut, status_code=201)
async def add_tracked(
    body: TrackerItemCreate,
    user_id: str = Depends(require_user),
) -> TrackerItemOut:
    scheme = await get_db()["schemes"].find_one({"slug": body.slug})
    if scheme is None:
        raise HTTPException(status_code=404, detail="Scheme not found")

    coll = await _tracked_collection()
    uid = user_id
    dup_query: dict[str, Any] = {"slug": body.slug, "user_id": uid[:120]}
    if await coll.find_one(dup_query, {"_id": 1}) is not None:
        raise HTTPException(status_code=409, detail="Scheme is already in your tracker")

    now = _utcnow()
    doc: dict[str, Any] = {
        "slug": body.slug,
        "name": scheme.get("name", body.slug),
        "status": "documents_pending",
        "official_url": scheme.get("official_url"),
        "last_verified_date": _iso_date(scheme.get("last_verified_date")),
        "required_documents": _str_list(scheme.get("required_documents")),
        "application_steps": _str_list(scheme.get("application_steps")),
        "checked_documents": _clean_doc_keys(body.checked_documents),
        "attachments": [a.model_dump() for a in body.attachments],
        "reminder_date": _date_to_mongo(body.reminder_date),
        "notes": _clean_notes(body.notes),
        "user_id": uid[:120],
        "created_at": now,
        "updated_at": now,
    }
    result = await coll.insert_one(doc)
    doc["_id"] = result.inserted_id
    return _to_out(doc, now.date())


@router.get("/checklist", response_model=ChecklistOut)
async def get_checklist(user_id: str = Depends(require_user)) -> ChecklistOut:
    coll = await _tracked_collection()
    items = await coll.find(_scope(user_id)).to_list(length=None)
    return _build_checklist(items)


@router.post("/checklist/toggle", response_model=ChecklistOut)
async def toggle_checklist_document(
    body: ChecklistToggle,
    user_id: str = Depends(require_user),
) -> ChecklistOut:
    key = normalize_doc(body.document)
    coll = await _tracked_collection()
    items = await coll.find(_scope(user_id)).to_list(length=None)
    matches = [
        it
        for it in items
        if key in {normalize_doc(n) for n in _str_list(it.get("required_documents"))}
    ]
    if not matches:
        raise HTTPException(status_code=404, detail="Document not in your tracker")

    now = _utcnow()
    for item in matches:
        current = [k for k in _clean_doc_keys(_str_list(item.get("checked_documents"))) if k != key]
        if body.checked:
            current.append(key)
        await coll.update_one(
            {"_id": item["_id"]},
            {"$set": {"checked_documents": current, "updated_at": now}},
        )

    items = await coll.find(_scope(user_id)).to_list(length=None)
    return _build_checklist(items)


@router.patch("/{item_id}", response_model=TrackerItemOut)
async def update_tracked(
    item_id: str,
    body: TrackerItemUpdate,
    user_id: str = Depends(require_user),
) -> TrackerItemOut:
    oid = _parse_id(item_id)
    fields = body.model_fields_set
    updates: dict[str, Any] = {}

    if "status" in fields:
        if body.status is None:
            raise HTTPException(status_code=422, detail="status cannot be null")
        updates["status"] = body.status
    if "checked_documents" in fields:
        updates["checked_documents"] = _clean_doc_keys(body.checked_documents or [])
    if "reminder_date" in fields:
        updates["reminder_date"] = _date_to_mongo(body.reminder_date)
    if "notes" in fields:
        updates["notes"] = _clean_notes(body.notes)
    if "attachments" in fields:
        updates["attachments"] = [a.model_dump() for a in (body.attachments or [])]

    now = _utcnow()
    updates["updated_at"] = now

    coll = await _tracked_collection()
    doc = await coll.find_one_and_update(
        {"_id": oid, **_scope(user_id)},
        {"$set": updates},
        return_document=ReturnDocument.AFTER,
    )
    if doc is None:
        raise HTTPException(status_code=404, detail="Tracker item not found")
    return _to_out(doc, now.date())


# ---------------------------------------------------------------------------
# File attachments (stored per-user in `tracker_files`, owner-only access)
# ---------------------------------------------------------------------------

MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB
ALLOWED_UPLOAD_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/webp",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def _clean_filename(name: str) -> str:
    # Strip any path components; keep it short and single-line.
    base = name.replace("\\", "/").rsplit("/", 1)[-1].strip()
    return base[:255] or "document"


async def _files_collection() -> Any:
    coll = get_db()["tracker_files"]
    await coll.create_index("item_id")
    await coll.create_index("user_id")
    return coll


async def _owned_item(item_id: str, user_id: str) -> tuple[ObjectId, dict[str, Any]]:
    oid = _parse_id(item_id)
    doc = await (await _tracked_collection()).find_one({"_id": oid, **_scope(user_id)})
    if doc is None:
        raise HTTPException(status_code=404, detail="Tracker item not found")
    return oid, doc


@router.post("/{item_id}/attachments", response_model=TrackerItemOut, status_code=201)
async def upload_attachment(
    item_id: str,
    file: UploadFile = File(...),
    user_id: str = Depends(require_user),
) -> TrackerItemOut:
    oid, item = await _owned_item(item_id, user_id)

    content_type = (file.content_type or "").split(";")[0].strip().lower()
    if content_type not in ALLOWED_UPLOAD_TYPES:
        raise HTTPException(status_code=415, detail="File type not allowed (pdf, png, jpg, webp, doc, docx)")

    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 5 MB)")
    if not data:
        raise HTTPException(status_code=422, detail="Empty file")

    filename = _clean_filename(file.filename or "document")
    files = await _files_collection()
    now = _utcnow()
    result = await files.insert_one(
        {
            "item_id": str(oid),
            "user_id": user_id[:120],
            "filename": filename,
            "content_type": content_type,
            "size": len(data),
            "data": Binary(data),
            "created_at": now,
        }
    )
    file_id = str(result.inserted_id)

    meta = Attachment(name=filename, size=len(data), type=content_type, file_id=file_id)
    coll = await _tracked_collection()
    attachments = [a for a in (item.get("attachments") or []) if isinstance(a, dict)]
    if len(attachments) >= 20:
        await files.delete_one({"_id": result.inserted_id})
        raise HTTPException(status_code=422, detail="Too many attachments (max 20)")
    attachments.append(meta.model_dump())
    doc = await coll.find_one_and_update(
        {"_id": oid},
        {"$set": {"attachments": attachments, "updated_at": now}},
        return_document=ReturnDocument.AFTER,
    )
    return _to_out(doc, now.date())


@router.get("/files/{file_id}")
async def download_attachment(
    file_id: str,
    user_id: str = Depends(require_user),
) -> Response:
    try:
        oid = ObjectId(file_id)
    except (InvalidId, TypeError):
        raise HTTPException(status_code=404, detail="File not found")
    doc = await (await _files_collection()).find_one({"_id": oid, "user_id": user_id[:120]})
    if doc is None:
        raise HTTPException(status_code=404, detail="File not found")
    return Response(
        content=bytes(doc["data"]),
        media_type=doc.get("content_type") or "application/octet-stream",
        headers={"Content-Disposition": f'inline; filename="{doc.get("filename", "document")}"'},
    )


@router.delete("/files/{file_id}")
async def delete_attachment(
    file_id: str,
    user_id: str = Depends(require_user),
) -> dict[str, bool]:
    try:
        oid = ObjectId(file_id)
    except (InvalidId, TypeError):
        raise HTTPException(status_code=404, detail="File not found")
    files = await _files_collection()
    doc = await files.find_one({"_id": oid, "user_id": user_id[:120]})
    if doc is None:
        raise HTTPException(status_code=404, detail="File not found")
    await files.delete_one({"_id": oid})
    # Drop the metadata entry from the parent tracker item too.
    try:
        item_oid = ObjectId(doc.get("item_id"))
    except (InvalidId, TypeError):
        item_oid = None
    if item_oid is not None:
        await (await _tracked_collection()).update_one(
            {"_id": item_oid, **_scope(user_id)},
            {"$pull": {"attachments": {"file_id": file_id}}},
        )
    return {"deleted": True}


@router.delete("/{item_id}")
async def delete_tracked(
    item_id: str,
    user_id: str = Depends(require_user),
) -> dict[str, bool]:
    oid = _parse_id(item_id)
    coll = await _tracked_collection()
    result = await coll.delete_one({"_id": oid, **_scope(user_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Tracker item not found")
    # Remove any stored attachment bytes for this item.
    await (await _files_collection()).delete_many({"item_id": str(oid), "user_id": user_id[:120]})
    return {"deleted": True}
