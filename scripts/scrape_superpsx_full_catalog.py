#!/usr/bin/env python3
"""Build a complete mirror index from publicly exposed SuperPSX links.

Follows ordinary HTTP redirects and publicly exposed HTML links/buttons for a
small number of hops. It never submits forms, executes page JavaScript, solves
CAPTCHAs, logs in, defeats anti-bot controls, or downloads package payloads.
"""
import argparse
import json
import re
import time
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urljoin, urlparse, unquote

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "catalog/ps4-games/superpsx-full-catalog-links.json"
MIRROR_INDEX = ROOT / "catalog/ps4-games/superpsx-mirror-index.json"
APP_REPO = ROOT / "catalog/ps4-games/superpsx-repo/repo.yml"
LIST_URL = "https://raw.githubusercontent.com/tutw/SuperPSX-PS4-GameList/main/ps4_games_list.json"
USER_AGENT = "Mozilla/5.0 (compatible; PS4CatalogResearch/2.0)"
TIMEOUT = (8, 18)
MAX_PAGE_BYTES = 1024 * 1024
MAX_HOPS = 4
MAX_BRANCHES = 8

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
NEXT_WORDS = (
    "download", "descargar", "continue", "continuar", "mirror",
    "get link", "get file", "download file", "go to", "proceed",
    "descarga", "enlace", "link", "click here", "here", "ir",
)
INTERSTITIAL_HOSTS = (
    "filecrypt.cc", "bit.ly", "tinyurl.com", "t.co", "cutt.ly",
    "linkvertise.com", "ouo.io", "adf.ly", "anotepad.com",
)
FILE_EXTENSIONS = (".pkg", ".zip", ".rar", ".7z", ".iso")


def session():
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT})
    s.max_redirects = 10
    return s


def host_info(host):
    host = (host or "").lower().removeprefix("www.")
    for marker, priority, family in HOST_PRIORITY:
        if marker in host:
            return priority, family
    return 50, host or "unknown"


def kind(label):
    x = label.casefold()
    if re.search(r"\b(update|patch|actualizaci[oó]n|actualizacion|parche)\b", x):
        return "update"
    if re.search(r"\b(dlc|add[\s-]?on|addon|expansion|expansión)\b", x):
        return "dlc"
    return "game"


def page_metadata(soup):
    data = {"region": None, "size": None, "version": None, "firmware": None, "cusa": None}
    for table in soup.find_all("table"):
        for tr in table.find_all("tr"):
            cells = tr.find_all(["td", "th"])
            if len(cells) < 2:
                continue
            key = cells[0].get_text(" ", strip=True).casefold()
            value = cells[1].get_text(" ", strip=True)
            if "region" in key: data["region"] = value
            elif "size" in key or "tamaño" in key: data["size"] = value
            elif "version" in key or "versión" in key: data["version"] = value
            elif "firmware" in key: data["firmware"] = value
            match = re.search(r"CUSA\d{5}", value, re.I)
            if match: data["cusa"] = match.group(0).upper()
    return data


def dll_url(game_url, soup):
    for anchor in soup.find_all("a", href=True):
        href = urljoin(game_url, anchor["href"].strip())
        label = anchor.get_text(" ", strip=True).casefold()
        img = anchor.find("img")
        imgsrc = (img.get("src") or "").casefold() if img else ""
        if "dll-" in urlparse(href).path.casefold() or "download-button" in imgsrc or "download" in label:
            if (urlparse(href).hostname or "").casefold().endswith("superpsx.com"):
                return href
    return None


def visible_targets(root, base_url):
    attrs = ("href", "data-href", "data-url", "data-link", "data-download", "data-redirect")
    for node in root.find_all(["a", "button", "div", "span"], recursive=True):
        for attr in attrs:
            raw = (node.get(attr) or "").strip()
            if not raw or raw.lower().startswith(("javascript:", "mailto:", "tel:", "#")):
                continue
            yield node, urljoin(base_url, raw), attr


def is_ignored(url):
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    return (
        parsed.scheme not in ("http", "https")
        or not host
        or host in IGNORED_HOSTS
        or host == "superpsx.com"
        or host.endswith(".superpsx.com")
        or any(token in host for token in ("doubleclick.", "googlesyndication.", "google-analytics."))
    )


def page_next_links(html, page_url):
    soup = BeautifulSoup(html, "html.parser")
    candidates, seen = [], set()
    page_host = (urlparse(page_url).hostname or "").lower()
    is_container = any(marker in page_host for marker in INTERSTITIAL_HOSTS)
    for node, href, attr in visible_targets(soup, page_url):
        if is_ignored(href) or href in seen:
            continue
        label = node.get_text(" ", strip=True).casefold()
        aria = (node.get("aria-label") or "").casefold()
        title = (node.get("title") or "").casefold()
        hint = " ".join((label, aria, title))
        # Link-container pages such as Filecrypt commonly expose the mirror
        # as an unlabeled anchor. Follow those public anchors, but never forms.
        same_host = urlparse(href).hostname == urlparse(page_url).hostname
        if not same_host and not is_container and not any(word in hint for word in NEXT_WORDS):
            continue
        seen.add(href)
        candidates.append({"url": href, "label": label[:180], "attribute": attr})
    # Prioritize the known mirror hosts while preserving every candidate.
    candidates.sort(key=lambda x: host_info(urlparse(x["url"]).hostname)[0])
    return candidates[:MAX_BRANCHES]


def read_limited(response):
    chunks, total = [], 0
    for chunk in response.iter_content(chunk_size=65536):
        if not chunk:
            continue
        chunks.append(chunk)
        total += len(chunk)
        if total >= MAX_PAGE_BYTES:
            break
    return b"".join(chunks)[:MAX_PAGE_BYTES]


def looks_like_file(url, headers):
    path = unquote(urlparse(url).path).lower()
    disposition = (headers.get("Content-Disposition") or "").lower()
    content_type = (headers.get("Content-Type") or "").lower()
    return (
        path.endswith(FILE_EXTENSIONS)
        or any(ext in disposition for ext in FILE_EXTENSIONS)
        or ("application/octet-stream" in content_type and "text/html" not in content_type)
    )


def resolve_public_link(start_url):
    """Follow redirects and public HTML continuation links; never submit forms."""
    queue = [(start_url, 0, [])]
    seen = set()
    results = []
    while queue and len(results) < MAX_BRANCHES:
        current, depth, chain = queue.pop(0)
        if current in seen or depth > MAX_HOPS or is_ignored(current):
            continue
        seen.add(current)
        try:
            with session().get(current, timeout=TIMEOUT, allow_redirects=True, stream=True) as response:
                response.raise_for_status()
                redirect_chain = [h.url for h in response.history] + [response.url]
                full_chain = chain + redirect_chain
                final_url = response.url
                headers = response.headers
                direct_file = looks_like_file(final_url, headers)
                content_type = (headers.get("Content-Type") or "").lower()
                result = {
                    "source_url": start_url,
                    "resolved_url": final_url,
                    "redirect_chain": full_chain,
                    "http_status": response.status_code,
                    "content_type": content_type,
                    "content_disposition": headers.get("Content-Disposition", ""),
                    "is_direct_file": direct_file,
                    "resolution_hops": depth + len(response.history),
                    "resolution_status": "direct_file" if direct_file else "landing_page",
                }
                if direct_file:
                    results.append(result)
                    continue
                if "text/html" not in content_type and content_type:
                    result["resolution_status"] = "non_html_response"
                    results.append(result)
                    continue
                body = read_limited(response)
                html = body.decode(response.encoding or "utf-8", errors="replace")
                next_links = page_next_links(html, final_url)
                if next_links and depth < MAX_HOPS:
                    for item in next_links:
                        queue.append((item["url"], depth + 1, full_chain + [item["url"]]))
                    result["resolution_status"] = "intermediate_page"
                    result["next_candidates"] = next_links
                else:
                    # CAPTCHA/login/JS-only pages are reported as unresolved,
                    # never bypassed or represented as a successful direct link.
                    result["resolution_status"] = "landing_page"
                results.append(result)
        except requests.RequestException as exc:
            results.append({
                "source_url": start_url, "resolved_url": current,
                "redirect_chain": chain + [current],
                "resolution_status": "request_failed",
                "resolution_error": str(exc)[:240],
                "is_direct_file": False,
            })
    # Deduplicate final URLs while keeping the most informative record.
    unique, output = set(), []
    for item in results:
        key = (item.get("resolved_url"), item.get("resolution_status"))
        if key not in unique:
            unique.add(key)
            output.append(item)
    return output


def extract_game_page(game):
    response = session().get(game["url"], timeout=TIMEOUT, allow_redirects=True)
    response.raise_for_status()
    soup = BeautifulSoup(read_limited(response).decode(response.encoding or "utf-8", errors="replace"), "html.parser")
    target = game["url"] if "/dll-" in urlparse(game["url"]).path else dll_url(game["url"], soup)
    if not target:
        raise ValueError("download_page_not_found")
    dll_response = session().get(target, timeout=TIMEOUT, allow_redirects=True)
    dll_response.raise_for_status()
    dll_soup = BeautifulSoup(read_limited(dll_response).decode(dll_response.encoding or "utf-8", errors="replace"), "html.parser")
    meta = page_metadata(dll_soup)
    roots = dll_soup.select("article, main, .entry-content, .post-content, .td-post-content")
    root = max(roots, key=lambda node: len(node.find_all(["a", "button"], href=True))) if roots else dll_soup.body or dll_soup
    found, seen = [], set()
    for node, href, source_attr in visible_targets(root, dll_response.url):
        if is_ignored(href) or href in seen:
            continue
        seen.add(href)
        label = node.get_text(" ", strip=True)
        parent = node.find_parent(["tr", "li", "p", "div", "section"])
        description = (parent.get_text(" ", strip=True) if parent else label)[:500]
        priority, family = host_info(urlparse(href).hostname)
        found.append({
            "title": game["name"], "game_page": game["url"],
            "download_page": dll_response.url, "type": kind(description or label),
            "description": description or label or "Visible external link",
            "link_label": label, "host": urlparse(href).hostname or "",
            "host_family": family, "mirror_priority": priority,
            "source_attribute": source_attr, "url": href, **meta,
            "status": "visible_page_link",
        })
    return found


def write_outputs(result):
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    resolved = []
    for item in result["links"]:
        for hop in item.get("resolution", []):
            resolved.append({**item, **hop})
    resolved.sort(key=lambda x: (x.get("mirror_priority", 50), not x.get("is_direct_file", False)))
    index = {
        "schema_version": 2,
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "processed": result["processed"],
        "total_in_run": result["total_in_run"],
        "source_link_count": len(result["links"]),
        "resolved_candidate_count": len(resolved),
        "direct_file_count": sum(1 for x in resolved if x.get("is_direct_file")),
        "links": resolved,
    }
    MIRROR_INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # App-compatible repository feed: only confirmed direct .pkg links are
    # emitted. Landing pages are never passed to the PKG downloader as files.
    by_game = defaultdict(list)
    for item in resolved:
        url = item.get("resolved_url", "")
        disposition = (item.get("content_disposition") or "").lower()
        is_pkg = urlparse(url).path.lower().endswith(".pkg") or bool(re.search(r'filename\*?=.*?\.pkg(?:[";]|$)', disposition))
        if item.get("is_direct_file") and is_pkg:
            by_game[item["title"]].append(url)
    lines = ['name: "SuperPSX verified direct PKG mirrors"', 'repoURL: "https://raw.githubusercontent.com/ayoubnoob543-lab/PS4-4PT-DownloadHub/feat/download-reliability-throughput/catalog/ps4-games/superpsx-repo/"']
    for title, urls in sorted(by_game.items()):
        unique = list(dict.fromkeys(urls))
        priority_sorted = sorted(unique, key=lambda u: host_info(urlparse(u).hostname)[0])
        if not priority_sorted:
            continue
        lines += [json.dumps(title, ensure_ascii=False) + ':', '  type: GAME', '  pkgPath: ' + json.dumps(priority_sorted[0], ensure_ascii=False)]
        if len(priority_sorted) > 1:
            lines.append('  mirrors:')
            lines.extend('    - ' + json.dumps(url, ensure_ascii=False) for url in priority_sorted[1:])
    APP_REPO.parent.mkdir(parents=True, exist_ok=True)
    APP_REPO.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="0 = entire published game list")
    parser.add_argument("--delay", type=float, default=0.8)
    parser.add_argument("--start", type=int, default=0, help="zero-based resume offset")
    parser.add_argument("--resolve-delay", type=float, default=0.15)
    args = parser.parse_args()
    source = session().get(LIST_URL, timeout=TIMEOUT)
    source.raise_for_status()
    games = source.json().get("games", [])
    if args.start:
        games = games[args.start:]
    if args.limit:
        games = games[:args.limit]

    result = {
        "source": LIST_URL, "total_in_run": len(games), "processed": 0,
        "links": [], "errors": [], "resolution_errors": [],
        "host_priority": {family: priority for _, priority, family in HOST_PRIORITY},
        "note": "All public links are retained. Redirects and public HTML continuation links are followed; no CAPTCHA, login, anti-bot, form, or JavaScript challenge is bypassed.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    resolved_cache = {}
    for i, game in enumerate(games, 1):
        name, url = game.get("name"), game.get("url")
        try:
            if not name or not url:
                raise ValueError("entry_missing_name_or_url")
            links = extract_game_page({"name": name, "url": url})
            for link in links:
                if link["url"] not in resolved_cache:
                    resolved_cache[link["url"]] = resolve_public_link(link["url"])
                    time.sleep(max(0, args.resolve_delay))
                link["resolution"] = resolved_cache[link["url"]]
                if not link["resolution"]:
                    result["resolution_errors"].append({"title": name, "url": link["url"], "error": "no_resolution_result"})
            result["links"].extend(links)
        except Exception as exc:
            result["errors"].append({"title": name, "url": url, "error": str(exc)[:300]})
        result["processed"] = i
        result["links"].sort(key=lambda x: (x["mirror_priority"], x["title"].casefold()))
        write_outputs(result)
        print(
            f"[{i}/{len(games)}] {name or url}: {len(result['links'])} links; "
            f"{sum(len(x.get('resolution', [])) for x in result['links'])} resolved candidates; "
            f"{len(result['errors'])} page errors",
            flush=True,
        )
        time.sleep(max(0, args.delay))
    write_outputs(result)
    counts = Counter(x["host_family"] for x in result["links"])
    print(f"DONE: {result['processed']}/{result['total_in_run']} games; {len(result['links'])} links; hosts={dict(counts)}; errors={len(result['errors'])}")


if __name__ == "__main__":
    main()
