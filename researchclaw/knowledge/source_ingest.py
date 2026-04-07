"""Structured ingest for Zotero and Obsidian research sources."""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from researchclaw.pipeline._helpers import _safe_filename, _utcnow_iso


def _normalize_text(text: str, limit: int) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())[:limit]


def _extract_year(text: str) -> int:
    match = re.search(r"\b(19|20)\d{2}\b", text or "")
    return int(match.group(0)) if match else 0


def _resolve_attachment_path(raw_path: str, attachment_root: Path) -> str:
    if not raw_path:
        return ""
    if raw_path.startswith("storage:"):
        relative = raw_path.split("storage:", 1)[1].lstrip("/\\")
        return str(attachment_root / relative)
    return raw_path.replace("attachments:", "").strip()


def load_obsidian_notes(
    vault_path: str,
    *,
    max_notes: int = 16,
) -> list[dict[str, Any]]:
    path = Path(vault_path).expanduser()
    if not path.exists() or not path.is_dir():
        return []

    rows: list[dict[str, Any]] = []
    for note_path in sorted(path.rglob("*.md"))[:max_notes]:
        try:
            text = note_path.read_text(encoding="utf-8")
        except OSError:
            continue
        text = text.strip()
        if len(text) < 40:
            continue
        title = note_path.stem
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                title = stripped.lstrip("#").strip() or note_path.stem
                break
        rows.append(
            {
                "id": f"obsidian-{_safe_filename(note_path.stem)}",
                "title": title,
                "source": "obsidian_note",
                "url": str(note_path),
                "year": _extract_year(text),
                "abstract": _normalize_text(text, 900),
                "full_text_excerpt": _normalize_text(text, 5000),
                "collected_at": _utcnow_iso(),
                "source_path": str(note_path),
            }
        )
    return rows


def _parse_zotero_json_items(
    library_path: Path,
    *,
    attachment_root: Path | None,
    collection_filters: tuple[str, ...],
    max_items: int,
) -> list[dict[str, Any]]:
    try:
        payload = json.loads(library_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(payload, list):
        return []

    filters = {item.lower() for item in collection_filters if item}
    rows: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        if not title:
            continue
        collections = [str(c) for c in item.get("collections", []) if c]
        if filters and not any(c.lower() in filters for c in collections):
            continue
        abstract = str(item.get("abstractNote", "") or item.get("abstract", ""))
        creators = item.get("creators", [])
        authors = []
        if isinstance(creators, list):
            for creator in creators[:6]:
                if not isinstance(creator, dict):
                    continue
                name = " ".join(
                    part for part in (
                        str(creator.get("firstName", "")).strip(),
                        str(creator.get("lastName", "")).strip(),
                    )
                    if part
                ).strip()
                if not name:
                    name = str(creator.get("name", "")).strip()
                if name:
                    authors.append({"name": name})
        attachment_path = ""
        attachments = item.get("attachments", [])
        if isinstance(attachments, list):
            for attachment in attachments:
                if not isinstance(attachment, dict):
                    continue
                raw_path = str(attachment.get("path", "")).strip()
                if raw_path and attachment_root is not None:
                    attachment_path = _resolve_attachment_path(raw_path, attachment_root)
                    break
        rows.append(
            {
                "id": f"zotero-{_safe_filename(str(item.get('key', title)))}",
                "title": title,
                "source": "zotero_json",
                "url": attachment_path or str(item.get("url", "")),
                "year": _extract_year(str(item.get("date", ""))),
                "abstract": _normalize_text(abstract, 900),
                "authors": authors,
                "collections": collections,
                "collected_at": _utcnow_iso(),
                "source_path": str(library_path),
            }
        )
        if len(rows) >= max_items:
            break
    return rows


def _parse_zotero_sqlite_items(
    library_path: Path,
    *,
    attachment_root: Path | None,
    collection_filters: tuple[str, ...],
    max_items: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    filters = {item.lower() for item in collection_filters if item}
    attachment_base = attachment_root or (library_path.parent / "storage")
    query = """
    WITH field_map AS (
        SELECT fieldID, fieldName FROM fields
    ),
    title_data AS (
        SELECT itemData.itemID, itemDataValues.value AS title
        FROM itemData
        JOIN field_map ON field_map.fieldID = itemData.fieldID
        JOIN itemDataValues ON itemDataValues.valueID = itemData.valueID
        WHERE field_map.fieldName = 'title'
    ),
    abstract_data AS (
        SELECT itemData.itemID, itemDataValues.value AS abstract_text
        FROM itemData
        JOIN field_map ON field_map.fieldID = itemData.fieldID
        JOIN itemDataValues ON itemDataValues.valueID = itemData.valueID
        WHERE field_map.fieldName = 'abstractNote'
    ),
    date_data AS (
        SELECT itemData.itemID, itemDataValues.value AS date_text
        FROM itemData
        JOIN field_map ON field_map.fieldID = itemData.fieldID
        JOIN itemDataValues ON itemDataValues.valueID = itemData.valueID
        WHERE field_map.fieldName = 'date'
    )
    SELECT items.itemID, items.key, title_data.title, abstract_data.abstract_text, date_data.date_text
    FROM items
    LEFT JOIN title_data ON title_data.itemID = items.itemID
    LEFT JOIN abstract_data ON abstract_data.itemID = items.itemID
    LEFT JOIN date_data ON date_data.itemID = items.itemID
    WHERE title_data.title IS NOT NULL
    LIMIT ?
    """
    try:
        conn = sqlite3.connect(str(library_path))
        conn.row_factory = sqlite3.Row
    except sqlite3.Error:
        return rows
    try:
        items = conn.execute(query, (max_items * 4,)).fetchall()
        for item in items:
            item_id = int(item["itemID"])
            collections = [
                str(row["collectionName"])
                for row in conn.execute(
                    """
                    SELECT collections.collectionName
                    FROM itemCollections
                    JOIN collections ON collections.collectionID = itemCollections.collectionID
                    WHERE itemCollections.itemID = ?
                    """,
                    (item_id,),
                ).fetchall()
            ]
            if filters and not any(c.lower() in filters for c in collections):
                continue
            authors = []
            for row in conn.execute(
                """
                SELECT creatorData.firstName, creatorData.lastName, creatorData.lastName || ' ' || creatorData.firstName AS name
                FROM itemCreators
                JOIN creators ON creators.creatorID = itemCreators.creatorID
                JOIN creatorData ON creatorData.creatorDataID = creators.creatorDataID
                WHERE itemCreators.itemID = ?
                ORDER BY itemCreators.orderIndex ASC
                """,
                (item_id,),
            ).fetchall()[:6]:
                name = str(row["name"] or "").strip()
                if name:
                    authors.append({"name": name})
            attachment_path = ""
            for row in conn.execute(
                """
                SELECT itemAttachments.path
                FROM itemAttachments
                WHERE itemAttachments.parentItemID = ?
                """,
                (item_id,),
            ).fetchall():
                raw_path = str(row["path"] or "").strip()
                if raw_path:
                    attachment_path = _resolve_attachment_path(raw_path, attachment_base)
                    break
            rows.append(
                {
                    "id": f"zotero-{_safe_filename(str(item['key']))}",
                    "title": str(item["title"]).strip(),
                    "source": "zotero_sqlite",
                    "url": attachment_path,
                    "year": _extract_year(str(item["date_text"] or "")),
                    "abstract": _normalize_text(str(item["abstract_text"] or ""), 900),
                    "authors": authors,
                    "collections": collections,
                    "collected_at": _utcnow_iso(),
                    "source_path": str(library_path),
                }
            )
            if len(rows) >= max_items:
                break
    except sqlite3.Error:
        return rows
    finally:
        conn.close()
    return rows


def load_zotero_items(
    library_path: str,
    *,
    attachment_root: str = "",
    collection_filters: tuple[str, ...] = (),
    max_items: int = 20,
) -> list[dict[str, Any]]:
    path = Path(library_path).expanduser()
    if not path.exists():
        return []
    attachment_base = Path(attachment_root).expanduser() if attachment_root else None
    if path.suffix.lower() == ".json":
        return _parse_zotero_json_items(
            path,
            attachment_root=attachment_base,
            collection_filters=collection_filters,
            max_items=max_items,
        )
    if path.suffix.lower() == ".sqlite":
        return _parse_zotero_sqlite_items(
            path,
            attachment_root=attachment_base,
            collection_filters=collection_filters,
            max_items=max_items,
        )
    return []

