"""Bookmark JSON and Netscape HTML import/export."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from html import escape
from html.parser import HTMLParser
from urllib.parse import urlparse

EXPORT_VERSION = 1


def normalize_url(url: str) -> str:
    url = url.strip()
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    scheme = (parsed.scheme or "https").lower()
    path = parsed.path.rstrip("/") or ""
    return f"{scheme}://{host}{path}"


def export_json(folders: list[dict], links: list[dict]) -> dict:
    folder_ref: dict[int, str] = {}
    for i, folder in enumerate(folders, start=1):
        folder_ref[folder["id"]] = f"f{i}"

    export_folders = []
    for folder in folders:
        parent_ref = folder_ref.get(folder["parent_id"]) if folder.get("parent_id") else None
        export_folders.append(
            {
                "ref": folder_ref[folder["id"]],
                "name": folder["name"],
                "parent_ref": parent_ref,
                "sort_order": folder.get("sort_order", 0),
            }
        )

    export_links = []
    for i, link in enumerate(links, start=1):
        folder_ref_id = None
        if link.get("folder_id"):
            folder_ref_id = folder_ref.get(link["folder_id"])
        export_links.append(
            {
                "ref": f"l{i}",
                "title": link["title"],
                "url": link["url"],
                "description": link.get("description") or "",
                "folder_ref": folder_ref_id,
                "sort_order": link.get("sort_order", 0),
                "click_count": link.get("click_count", 0),
            }
        )

    return {
        "version": EXPORT_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "folders": export_folders,
        "links": export_links,
    }


def _folder_tree(folders: list[dict], parent_id: int | None) -> list[dict]:
    nodes = [f for f in folders if f.get("parent_id") == parent_id]
    nodes.sort(key=lambda f: (f.get("sort_order", 0), f["name"].lower()))
    return nodes


def _links_for_folder(links: list[dict], folder_id: int | None) -> list[dict]:
    items = [l for l in links if l.get("folder_id") == folder_id]
    items.sort(key=lambda l: (l.get("sort_order", 0), l["title"].lower()))
    return items


def _render_html_folder(folder: dict, all_folders: list[dict], all_links: list[dict]) -> str:
    lines = [
        f'    <DT><H3>{escape(folder["name"])}</H3>',
        "    <DL><p>",
    ]
    for child in _folder_tree(all_folders, folder["id"]):
        lines.append(_render_html_folder(child, all_folders, all_links))
    for link in _links_for_folder(all_links, folder["id"]):
        title = escape(link["title"])
        href = escape(link["url"], quote=True)
        lines.append(f'        <DT><A HREF="{href}">{title}</A>')
    lines.append("    </DL><p>")
    return "\n".join(lines)


def export_html(folders: list[dict], links: list[dict]) -> str:
    header = """<!DOCTYPE NETSCAPE-Bookmark-file-1>
<!-- This is an automatically generated file.
     It will be read and overwritten.
     DO NOT EDIT! -->
<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">
<TITLE>Bookmarks</TITLE>
<H1>Bookmarks</H1>
<DL><p>
"""
    body_lines = []
    for folder in _folder_tree(folders, None):
        body_lines.append(_render_html_folder(folder, folders, links))
    for link in _links_for_folder(links, None):
        title = escape(link["title"])
        href = escape(link["url"], quote=True)
        body_lines.append(f'    <DT><A HREF="{href}">{title}</A>')
    footer = "</DL><p>\n"
    return header + "\n".join(body_lines) + footer


class _NetscapeParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.folder_stack: list[int | None] = [None]
        self.folders: list[dict] = []
        self.links: list[dict] = []
        self._in_h3 = False
        self._h3_parts: list[str] = []
        self._in_a = False
        self._a_href = ""
        self._a_parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        attrs_d = {k.lower(): (v or "") for k, v in attrs}
        t = tag.lower()
        if t == "h3":
            self._in_h3 = True
            self._h3_parts = []
        elif t == "a":
            href = attrs_d.get("href", "").strip()
            if href:
                self._in_a = True
                self._a_href = href
                self._a_parts = []

    def handle_endtag(self, tag):
        t = tag.lower()
        if t == "h3" and self._in_h3:
            name = "".join(self._h3_parts).strip()
            if name:
                idx = len(self.folders)
                self.folders.append(
                    {"name": name, "parent_index": self.folder_stack[-1]}
                )
                self.folder_stack.append(idx)
            self._in_h3 = False
        elif t == "dl":
            if len(self.folder_stack) > 1:
                self.folder_stack.pop()
        elif t == "a" and self._in_a:
            title = "".join(self._a_parts).strip() or self._a_href
            href = self._a_href.strip()
            if href and not href.lower().startswith(("javascript:", "place:", "about:", "chrome:")):
                self.links.append(
                    {
                        "title": title.strip(),
                        "url": href,
                        "folder_index": self.folder_stack[-1],
                    }
                )
            self._in_a = False

    def handle_data(self, data):
        if self._in_h3:
            self._h3_parts.append(data)
        if self._in_a:
            self._a_parts.append(data)


def parse_html(content: str) -> tuple[list[dict], list[dict]]:
    parser = _NetscapeParser()
    parser.feed(content)
    return parser.folders, parser.links


def parse_json(content: str) -> tuple[list[dict], list[dict]]:
    data = json.loads(content)
    folders_raw = data.get("folders") or []
    links_raw = data.get("links") or []

    ref_to_index: dict[str, int] = {}
    folders: list[dict] = []
    for item in folders_raw:
        idx = len(folders)
        ref_to_index[item["ref"]] = idx
        folders.append(
            {
                "name": item.get("name", "Folder"),
                "parent_index": None,
                "parent_ref": item.get("parent_ref"),
                "sort_order": item.get("sort_order", 0),
            }
        )

    for i, item in enumerate(folders_raw):
        parent_ref = item.get("parent_ref")
        if parent_ref and parent_ref in ref_to_index:
            folders[i]["parent_index"] = ref_to_index[parent_ref]

    links = []
    for item in links_raw:
        folder_index = None
        folder_ref = item.get("folder_ref")
        if folder_ref and folder_ref in ref_to_index:
            folder_index = ref_to_index[folder_ref]
        links.append(
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "description": item.get("description") or "",
                "folder_index": folder_index,
                "sort_order": item.get("sort_order", 0),
            }
        )
    return folders, links


def import_payload(
    folders: list[dict],
    links: list[dict],
    *,
    insert_folder,
    insert_link,
    existing_urls: set[str],
) -> dict:
    """Insert folders and links; skip duplicate URLs. Callbacks return new row id."""
    folder_id_map: dict[int | None, int | None] = {None: None}
    folders_created = 0
    imported = 0
    skipped = 0

    pending = list(enumerate(folders))
    while pending:
        progress = False
        next_pending = []
        for idx, folder in pending:
            parent_index = folder.get("parent_index")
            if parent_index not in folder_id_map:
                next_pending.append((idx, folder))
                continue
            parent_id = folder_id_map[parent_index]
            new_id = insert_folder(
                folder["name"],
                parent_id,
                folder.get("sort_order", 0),
            )
            folder_id_map[idx] = new_id
            folders_created += 1
            progress = True
        if not progress and next_pending:
            for idx, folder in next_pending:
                new_id = insert_folder(folder["name"], None, folder.get("sort_order", 0))
                folder_id_map[idx] = new_id
                folders_created += 1
            break
        pending = next_pending

    for link in links:
        url = normalize_url(link.get("url", ""))
        if not url or url in existing_urls:
            skipped += 1
            continue
        if not url.startswith(("http://", "https://")):
            skipped += 1
            continue
        folder_idx = link.get("folder_index")
        folder_id = folder_id_map.get(folder_idx)
        insert_link(
            link.get("title") or url,
            url,
            link.get("description") or "",
            folder_id,
            link.get("sort_order", 0),
        )
        existing_urls.add(url)
        imported += 1

    return {
        "imported": imported,
        "skipped": skipped,
        "folders_created": folders_created,
    }
