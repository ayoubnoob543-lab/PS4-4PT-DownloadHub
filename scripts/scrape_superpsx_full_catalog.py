#!/usr/bin/env python3
"""Extract publicly visible download/mirror links from the SuperPSX catalog.

The scraper records links exposed in page markup. It does not bypass CAPTCHA,
authentication, anti-bot controls, paywalls, or resolve temporary download URLs.
All mirrors are retained; preferred hosts are only sorted to the top.
"""
import argparse
import json
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "catalog/ps4-games/superpsx-full-catalog-links.json"
LIST_URL = "https://raw.githubusercontent.com/tutw/SuperPSX-PS4-GameList/main/ps4_games_list.json"
S = requests.Session()
S.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"})

# Lower number = shown earlier in the app/catalog. No host is discarded because
# of its rank: the complete mirror list remains available as fallback.
HOST_PRIORITY = (
    ("mocha.my", 0, "mocha"),
    ("filecrypt.cc", 1, "filecrypt"),
    ("vikingfile.com", 2, "vikingfile"),
    ("1fichier.com", 3, "1fichier"),
    ("onefile", 4, "onefile"),
    ("filekeeper", 5, "filekeeper"),
    ("buzzheavier", 6, "buzzheavier"),
    ("akirabox", 7, "akirabox"),
)

IGNORED_HOSTS = {
    "facebook.com", "twitter.com", "x.com", "instagram.com",
    "youtube.com", "t.me", "telegram.me", "pinterest.com", "wa.me",
}


def host_info(host):
    host = (host or "").lower().removeprefix("www.")
    for marker, priority, family in HOST_PRIORITY:
        if marker in host:
            return priority, family
    return 50, host or "unknown"


def kind(label):
    x = label.casefold()
    if re.search(r"\\b(update|patch|actualizaci[oó]n|actualizacion|parche)\\b", x):
        return "update"
    if re.search(r"\\b(dlc|add[\\s-]?on|addon|expansion|expansión)\\b", x):
        return "dlc"
    return "game"


def page_metadata(soup):
    data = {"region": None, "size": None, "version": None, "firmware": None, "cusa": None}
    for table in soup.find_all("table"):
        for tr in table.find_all("tr"):
            cells = tr.find_all(["td", "th"])
            if len(cells) < 2:
                continue
            k, v = cells[0].get_text(" ", strip=True).casefold(), cells[1].get_text(" ", strip=True)
            if "region" in k: data["region"] = v
            elif "size" in k or "tamaño" in k: data["size"] = v
            elif "version" in k or "versión" in k: data["version"] = v
            elif "firmware" in k: data["firmware"] = v
            m = re.search(r"CUSA\\d{5}", v, re.I)
            if m: data["cusa"] = m.group(0).upper()
    return data


def dll_url(game_url, soup):
    for a in soup.find_all("a", href=True):
        href = urljoin(game_url, a["href"].strip())
        label = a.get_text(" ", strip=True).casefold()
        img = a.find("img")
        imgsrc = (img.get("src") or "").casefold() if img else ""
        if "dll-" in urlparse(href).path.casefold() or "download-button" in imgsrc or "download" in label:
            if (urlparse(href).hostname or "").casefold().endswith("superpsx.com"):
                return href
    return None


def visible_targets(root):
    """Yield markup URLs from anchors and common button/data attributes."""
    attributes = ("href", "data-href", "data-url", "data-link", "data-download")
    for node in root.find_all(["a", "button", "div", "span"], recursive=True):
        for attr in attributes:
            value = (node.get(attr) or "").strip()
            if value and not value.lower().startswith(("javascript:", "mailto:", "tel:", "#")):
                yield node, value, attr


def scrape_dll(url, game):
    r = S.get(url, timeout=35)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    meta = page_metadata(soup)
    found, seen = [], set()

    roots = soup.select("article, main, .entry-content, .post-content, .td-post-content")
    root = max(roots, key=lambda node: len(node.find_all(["a", "button"], href=True))) if roots else soup.body or soup

    for node, raw, source_attr in visible_targets(root):
        href = urljoin(url, raw)
        parsed = urlparse(href)
        host = (parsed.hostname or "").lower().removeprefix("www.")
        if parsed.scheme not in ("http", "https") or not host:
            continue
        if host == "superpsx.com" or host.endswith(".superpsx.com") or host in IGNORED_HOSTS:
            continue
        if any(token in host for token in ("doubleclick.", "googlesyndication.", "google-analytics.")):
            continue
        if href in seen:
            continue
        seen.add(href)

        label = node.get_text(" ", strip=True)
        parent = node.find_parent(["tr", "li", "p", "div", "section"])
        context = parent.get_text(" ", strip=True)[:500] if parent else label
        description = context or label or "Visible external link"
        priority, family = host_info(host)
        found.append({
            "title": game["name"], "game_page": game["url"],
            "download_page": url, "type": kind(description),
            "description": description, "link_label": label,
            "host": host, "host_family": family, "mirror_priority": priority,
            "source_attribute": source_attr, "url": href,
            **meta, "status": "visible_page_link"
        })

    # Stable sort: all links remain; preferred mirror hosts are first.
    found.sort(key=lambda item: item["mirror_priority"])
    if not found:
        title = soup.title.get_text(" ", strip=True) if soup.title else "untitled"
        body_text = (root.get_text(" ", strip=True) if root else "")[:180]
        raise ValueError(
            "no_visible_external_links; "
            f"http_status={r.status_code}; page_title={title!r}; "
            f"page_text={body_text!r}"
        )
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="0 = entire published game list")
    ap.add_argument("--delay", type=float, default=1.2)
    ap.add_argument("--start", type=int, default=0, help="zero-based resume offset")
    args = ap.parse_args()

    data = S.get(LIST_URL, timeout=40)
    data.raise_for_status()
    games = data.json().get("games", [])
    if args.start:
        games = games[args.start:]
    if args.limit:
        games = games[:args.limit]

    result = {
        "source": LIST_URL, "total_in_run": len(games), "processed": 0,
        "links": [], "errors": [],
        "host_priority": {family: priority for _, priority, family in HOST_PRIORITY},
        "note": "All publicly visible external links retained and ordered by preferred host; URLs are not claimed to be verified direct downloads."
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    for i, game in enumerate(games, 1):
        name, url = game.get("name"), game.get("url")
        try:
            if not name or not url:
                raise ValueError("entry_missing_name_or_url")
            r = S.get(url, timeout=35)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            target = url if "/dll-" in urlparse(url).path else dll_url(url, soup)
            if not target:
                raise ValueError("download_page_not_found")
            result["links"].extend(scrape_dll(target, {"name": name, "url": url}))
        except Exception as e:
            result["errors"].append({"title": name, "url": url, "error": str(e)[:250]})
        result["processed"] = i
        OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\\n", encoding="utf-8")
        print(f"[{i}/{len(games)}] {name or url}: {len(result['links'])} links; {len(result['errors'])} errors", flush=True)
        time.sleep(max(0, args.delay))
    print(f"DONE: {result['processed']} pages; {len(result['links'])} links; {len(result['errors'])} errors")


if __name__ == "__main__":
    main()
