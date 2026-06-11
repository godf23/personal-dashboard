from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.database import get_db, _utcnow
from app.services.bookmarks import (
    export_html,
    export_json,
    import_payload,
    normalize_url,
    parse_html,
    parse_json,
)
from app.services.favicon import favicon_url_for

router = APIRouter(prefix="/api/links", tags=["links"])

SORT_MODES = {"most_used", "recent", "az", "za"}


class LinkCreate(BaseModel):
    title: str
    url: str
    description: str | None = None
    folder_id: int | None = None


class LinkPatch(BaseModel):
    title: str | None = None
    url: str | None = None
    description: str | None = None
    folder_id: int | None = None
    sort_order: int | None = None


class FolderCreate(BaseModel):
    name: str
    parent_id: int | None = None


class FolderPatch(BaseModel):
    name: str | None = None
    parent_id: int | None = None
    sort_order: int | None = None


class FolderFromLinks(BaseModel):
    link_ids: list[int] = Field(..., min_length=2, max_length=2)
    name: str | None = None
    parent_id: int | None = None


def _row_to_link(row) -> dict:
    icon = row["icon_url"]
    if not icon:
        icon = favicon_url_for(row["url"])
    return {
        "id": row["id"],
        "title": row["title"],
        "url": row["url"],
        "description": row["description"] or "",
        "folder_id": row["folder_id"],
        "sort_order": row["sort_order"] or 0,
        "icon_url": icon,
        "click_count": row["click_count"],
        "last_clicked_at": row["last_clicked_at"],
        "created_at": row["created_at"],
    }


def _row_to_folder(row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "parent_id": row["parent_id"],
        "sort_order": row["sort_order"] or 0,
        "created_at": row["created_at"],
    }


def _order_key(sort: str):
    if sort == "most_used":
        return lambda l: (-(l.get("click_count") or 0), l["title"].lower())
    if sort == "recent":
        return lambda l: (
            l.get("last_clicked_at") is None,
            l.get("last_clicked_at") or "",
            l["title"].lower(),
        )
    if sort == "za":
        return lambda l: l["title"].lower()
    return lambda l: l["title"].lower()


def _sort_links(links: list[dict], sort: str) -> list[dict]:
    reverse = sort == "za"
    return sorted(links, key=_order_key(sort), reverse=reverse)


def _link_matches_query(link: dict, q: str) -> bool:
    blob = f"{link.get('title', '')} {link.get('url', '')} {link.get('description', '')}".lower()
    return q.lower() in blob


def _folder_descendant_ids(folder_id: int, folders: list[dict]) -> set[int]:
    children = {f["id"] for f in folders if f.get("parent_id") == folder_id}
    out = set(children)
    for cid in list(children):
        out |= _folder_descendant_ids(cid, folders)
    return out


def _is_valid_reparent(folder_id: int, new_parent_id: int | None, folders: list[dict]) -> bool:
    if new_parent_id is None:
        return True
    if new_parent_id == folder_id:
        return False
    return new_parent_id not in _folder_descendant_ids(folder_id, folders)


def _build_tree(
    folders: list[dict],
    links: list[dict],
    sort: str,
    q: str | None = None,
) -> dict:
    folder_by_id = {f["id"]: dict(f) for f in folders}
    links_by_folder: dict[int | None, list[dict]] = {}
    for link in links:
        links_by_folder.setdefault(link.get("folder_id"), []).append(link)

    if q:
        matching_link_ids = {l["id"] for l in links if _link_matches_query(l, q)}
        needed_folder_ids: set[int] = set()
        for link in links:
            if link["id"] in matching_link_ids and link.get("folder_id"):
                fid = link["folder_id"]
                while fid:
                    needed_folder_ids.add(fid)
                    fid = folder_by_id.get(fid, {}).get("parent_id")
        filtered_links = [l for l in links if l["id"] in matching_link_ids]
        filtered_folders = [f for f in folders if f["id"] in needed_folder_ids]
    else:
        filtered_links = links
        filtered_folders = folders

    def build_folder_node(folder_id: int) -> dict:
        folder = folder_by_id[folder_id]
        child_folders = [
            f for f in filtered_folders if f.get("parent_id") == folder_id
        ]
        child_folders.sort(key=lambda f: (f.get("sort_order", 0), f["name"].lower()))
        folder_links = _sort_links(
            [l for l in filtered_links if l.get("folder_id") == folder_id],
            sort,
        )
        return {
            **_row_to_folder(folder),
            "children": [build_folder_node(f["id"]) for f in child_folders],
            "links": folder_links,
        }

    root_folders = [f for f in filtered_folders if not f.get("parent_id")]
    root_folders.sort(key=lambda f: (f.get("sort_order", 0), f["name"].lower()))
    root_links = _sort_links(
        [l for l in filtered_links if not l.get("folder_id")],
        sort,
    )

    return {
        "folders": [build_folder_node(f["id"]) for f in root_folders],
        "links": root_links,
    }


def _existing_normalized_urls(conn) -> set[str]:
    rows = conn.execute("SELECT url FROM links").fetchall()
    return {normalize_url(r["url"]) for r in rows if r["url"]}


@router.get("/tree")
def get_links_tree(sort: str = "most_used", q: str | None = None):
    if sort not in SORT_MODES:
        sort = "most_used"
    query = q.strip() if q else None
    with get_db() as conn:
        folder_rows = conn.execute(
            "SELECT * FROM link_folders ORDER BY sort_order, name COLLATE NOCASE"
        ).fetchall()
        link_rows = conn.execute("SELECT * FROM links").fetchall()
    folders = [_row_to_folder(r) for r in folder_rows]
    links = [_row_to_link(r) for r in link_rows]
    return _build_tree(folders, links, sort, query)


@router.get("")
def list_links(sort: str = "most_used", q: str | None = None):
    tree = get_links_tree(sort=sort, q=q)

    def flatten(node_folders, acc):
        for folder in node_folders:
            acc.extend(folder.get("links", []))
            flatten(folder.get("children", []), acc)

    items: list[dict] = []
    items.extend(tree.get("links", []))
    flatten(tree.get("folders", []), items)
    return items


@router.post("/folders")
def create_folder(body: FolderCreate):
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Folder name is required")
    with get_db() as conn:
        if body.parent_id is not None:
            parent = conn.execute(
                "SELECT id FROM link_folders WHERE id = ?", (body.parent_id,)
            ).fetchone()
            if not parent:
                raise HTTPException(404, "Parent folder not found")
        max_order = conn.execute(
            "SELECT COALESCE(MAX(sort_order), -1) FROM link_folders WHERE parent_id IS ?",
            (body.parent_id,),
        ).fetchone()[0]
        cur = conn.execute(
            "INSERT INTO link_folders (name, parent_id, sort_order, created_at) VALUES (?, ?, ?, ?)",
            (name, body.parent_id, max_order + 1, _utcnow()),
        )
        row = conn.execute(
            "SELECT * FROM link_folders WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
    return _row_to_folder(row)


@router.post("/folders/from-links")
def create_folder_from_links(body: FolderFromLinks):
    name = (body.name or "New folder").strip() or "New folder"
    link_ids = list(dict.fromkeys(body.link_ids))
    if len(link_ids) != 2:
        raise HTTPException(400, "Exactly two link ids are required")
    with get_db() as conn:
        rows = conn.execute(
            f"SELECT id FROM links WHERE id IN ({','.join('?' * len(link_ids))})",
            link_ids,
        ).fetchall()
        if len(rows) != 2:
            raise HTTPException(404, "One or more links not found")
        max_order = conn.execute(
            "SELECT COALESCE(MAX(sort_order), -1) FROM link_folders WHERE parent_id IS ?",
            (body.parent_id,),
        ).fetchone()[0]
        cur = conn.execute(
            "INSERT INTO link_folders (name, parent_id, sort_order, created_at) VALUES (?, ?, ?, ?)",
            (name, body.parent_id, max_order + 1, _utcnow()),
        )
        folder_id = cur.lastrowid
        for link_id in link_ids:
            conn.execute(
                "UPDATE links SET folder_id = ? WHERE id = ?",
                (folder_id, link_id),
            )
        folder = conn.execute(
            "SELECT * FROM link_folders WHERE id = ?", (folder_id,)
        ).fetchone()
    return _row_to_folder(folder)


@router.patch("/folders/{folder_id}")
def patch_folder(folder_id: int, body: FolderPatch):
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM link_folders WHERE id = ?", (folder_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "Folder not found")
        folders = [
            _row_to_folder(r)
            for r in conn.execute("SELECT * FROM link_folders").fetchall()
        ]
        new_parent = body.parent_id if body.parent_id is not None else row["parent_id"]
        if body.parent_id is not None and not _is_valid_reparent(
            folder_id, body.parent_id, folders
        ):
            raise HTTPException(400, "Cannot move folder into itself or a descendant")
        name = body.name.strip() if body.name is not None else row["name"]
        sort_order = body.sort_order if body.sort_order is not None else row["sort_order"]
        conn.execute(
            "UPDATE link_folders SET name = ?, parent_id = ?, sort_order = ? WHERE id = ?",
            (name, new_parent, sort_order, folder_id),
        )
        updated = conn.execute(
            "SELECT * FROM link_folders WHERE id = ?", (folder_id,)
        ).fetchone()
    return _row_to_folder(updated)


@router.delete("/folders/{folder_id}")
def delete_folder(folder_id: int):
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM link_folders WHERE id = ?", (folder_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "Folder not found")
        parent_id = row["parent_id"]
        conn.execute(
            "UPDATE links SET folder_id = ? WHERE folder_id = ?",
            (parent_id, folder_id),
        )
        conn.execute(
            "UPDATE link_folders SET parent_id = ? WHERE parent_id = ?",
            (parent_id, folder_id),
        )
        conn.execute("DELETE FROM link_folders WHERE id = ?", (folder_id,))
    return {"ok": True}


@router.post("")
def create_link(body: LinkCreate):
    title = body.title.strip()
    url = body.url.strip()
    if not title or not url:
        raise HTTPException(400, "Title and URL are required")
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    icon_url = favicon_url_for(url)
    with get_db() as conn:
        if body.folder_id is not None:
            folder = conn.execute(
                "SELECT id FROM link_folders WHERE id = ?", (body.folder_id,)
            ).fetchone()
            if not folder:
                raise HTTPException(404, "Folder not found")
        max_order = conn.execute(
            "SELECT COALESCE(MAX(sort_order), -1) FROM links WHERE folder_id IS ?",
            (body.folder_id,),
        ).fetchone()[0]
        cur = conn.execute(
            """
            INSERT INTO links (
                title, url, icon_url, description, folder_id, sort_order, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                title,
                url,
                icon_url,
                (body.description or "").strip() or None,
                body.folder_id,
                max_order + 1,
                _utcnow(),
            ),
        )
        row = conn.execute(
            "SELECT * FROM links WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
    return _row_to_link(row)


@router.patch("/{link_id}")
def patch_link(link_id: int, body: LinkPatch):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM links WHERE id = ?", (link_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Link not found")
        title = body.title.strip() if body.title is not None else row["title"]
        url = body.url.strip() if body.url is not None else row["url"]
        if body.url is not None and not url.startswith(("http://", "https://")):
            url = "https://" + url
        description = (
            body.description.strip() if body.description is not None else row["description"]
        )
        folder_id = body.folder_id if body.folder_id is not None else row["folder_id"]
        sort_order = body.sort_order if body.sort_order is not None else row["sort_order"]
        icon_url = favicon_url_for(url) if body.url is not None else row["icon_url"]
        if folder_id is not None:
            folder = conn.execute(
                "SELECT id FROM link_folders WHERE id = ?", (folder_id,)
            ).fetchone()
            if not folder:
                raise HTTPException(404, "Folder not found")
        conn.execute(
            """
            UPDATE links
            SET title = ?, url = ?, description = ?, folder_id = ?, sort_order = ?, icon_url = ?
            WHERE id = ?
            """,
            (title, url, description, folder_id, sort_order, icon_url, link_id),
        )
        updated = conn.execute("SELECT * FROM links WHERE id = ?", (link_id,)).fetchone()
    return _row_to_link(updated)


@router.delete("/{link_id}")
def delete_link(link_id: int):
    with get_db() as conn:
        cur = conn.execute("DELETE FROM links WHERE id = ?", (link_id,))
        if cur.rowcount == 0:
            raise HTTPException(404, "Link not found")
    return {"ok": True}


@router.post("/{link_id}/click")
def click_link(link_id: int):
    now = _utcnow()
    with get_db() as conn:
        cur = conn.execute(
            "UPDATE links SET click_count = click_count + 1, last_clicked_at = ? WHERE id = ?",
            (now, link_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "Link not found")
        row = conn.execute("SELECT url FROM links WHERE id = ?", (link_id,)).fetchone()
    return {"url": row["url"]}


@router.post("/import")
async def import_links(
    file: UploadFile = File(...),
    format: str = Query("json", pattern="^(json|html)$"),
):
    raw = await file.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("latin-1", errors="replace")

    if format == "html":
        folders, links = parse_html(text)
    else:
        folders, links = parse_json(text)

    with get_db() as conn:
        existing = _existing_normalized_urls(conn)

        def insert_folder(name, parent_id, sort_order):
            cur = conn.execute(
                "INSERT INTO link_folders (name, parent_id, sort_order, created_at) VALUES (?, ?, ?, ?)",
                (name, parent_id, sort_order, _utcnow()),
            )
            return cur.lastrowid

        def insert_link(title, url, description, folder_id, sort_order):
            icon = favicon_url_for(url)
            conn.execute(
                """
                INSERT INTO links (
                    title, url, icon_url, description, folder_id, sort_order, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (title, url, icon, description or None, folder_id, sort_order, _utcnow()),
            )

        result = import_payload(
            folders,
            links,
            insert_folder=insert_folder,
            insert_link=insert_link,
            existing_urls=existing,
        )
    return result


@router.get("/export")
def export_links(format: str = Query("json", pattern="^(json|html)$")):
    with get_db() as conn:
        folder_rows = conn.execute("SELECT * FROM link_folders").fetchall()
        link_rows = conn.execute("SELECT * FROM links").fetchall()
    folders = [_row_to_folder(r) for r in folder_rows]
    links = [_row_to_link(r) for r in link_rows]

    if format == "html":
        content = export_html(folders, links)
        return Response(
            content=content,
            media_type="text/html",
            headers={"Content-Disposition": 'attachment; filename="bookmarks.html"'},
        )

    payload = export_json(folders, links)
    body = json_dumps(payload)
    return Response(
        content=body,
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="bookmarks.json"'},
    )


def json_dumps(payload: dict) -> bytes:
    import json

    return json.dumps(payload, indent=2).encode("utf-8")
