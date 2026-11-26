#!/usr/bin/env python3
"""Collect publicly visible outbound download-page links from mapped SuperPSX entries.

Records page links only. It does not solve CAPTCHAs, log in, bypass host protections,
or resolve temporary/final file URLs.
"""
import argparse, json, time
from pathlib import Path
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "catalog/ps4-games/superpsx-source-pages-200.json"
OUTPUT = ROOT / "catalog/ps4-games/superpsx-visible-download-links.json"
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Mozilla/5.0 (compatible; PS4CatalogResearch/1.0)"})

def classify(label):
    s = label.lower()
    if any(x in s for x in ("update", "patch", "actualiz", "parche")): return "update"
    if any(x in s for x in ("dlc", "add-on", "addon", "expansion")): return "dlc"
    return "game"

def page_info(soup):
    info = {"region": None, "size": None, "version": None, "min_fw": None}
    table = soup.find("table")
    if table:
        for row in table.find_all("tr"):
            cells = row.find_all(["td", "th"])
            if len(cells) < 2: continue
            key, value = cells[0].get_text(" ", strip=True).lower(), cells[1].get_text(" ", strip=True)
            if "region" in key: info["region"] = value
            elif "size" in key or "tamaño" in key: info["size"] = value
            elif "version" in key or "versión" in key: info["version"] = value
            elif "firmware" in key: info["min_fw"] = value
    return info

def find_download_page(page_url, soup):
    for a in soup.find_all("a", href=True):
        img = a.find("img")
        src = (img.get("src", "") if img else "").lower()
        label = a.get_text(" ", strip=True).lower()
        if "download-button" in src or "download" in label:
            href = urljoin(page_url, a["href"])
            if (urlparse(href).hostname or "").endswith("superpsx.com"): return href
    return None

def extract_links(download_url, game, info):
    response = SESSION.get(download_url, timeout=35)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    links, seen = [], set()
    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all(["td", "th"])
            if len(cells) < 2: continue
            description = cells[0].get_text(" ", strip=True)
            for a in cells[1].find_all("a", href=True):
                url = urljoin(download_url, a["href"].strip())
                parsed = urlparse(url)
                if parsed.scheme not in ("http", "https") or url in seen: continue
                seen.add(url)
                links.append({
                    "game": game["title"], "source_page": game["source_url"],
                    "download_page": download_url, "type": classify(description),
                    "description": description, "label": a.get_text(" ", strip=True),
                    "host": (parsed.hostname or "").lower(), "url": url,
                    **info, "link_status": "page_link_only"
                })
    return links

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="0 = all mapped entries")
    parser.add_argument("--delay", type=float, default=1.2)
    args = parser.parse_args()
    source = json.loads(INPUT.read_text(encoding="utf-8"))
    entries = [x for x in source["entries"] if x.get("source_url")]
    if args.limit: entries = entries[:args.limit]
    output = {"source": "SuperPSX", "scope": len(entries),
              "note": "Visible outbound page links only; not resolved direct file URLs.",
              "processed": 0, "errors": [], "downloads": []}
    for i, game in enumerate(entries, 1):
        try:
            response = SESSION.get(game["source_url"], timeout=35)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            info = page_info(soup)
            target = find_download_page(game["source_url"], soup)
            if target: output["downloads"].extend(extract_links(target, game, info))
            else: output["errors"].append({"game": game["title"], "error": "download_page_not_found"})
        except Exception as exc:
            output["errors"].append({"game": game["title"], "error": str(exc)[:300]})
        output["processed"] = i
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"[{i}/{len(entries)}] {game['title']} | links={len(output['downloads'])} | errors={len(output['errors'])}", flush=True)
        time.sleep(max(0, args.delay))
    print(f"Finished: {output['processed']} pages, {len(output['downloads'])} visible links, {len(output['errors'])} errors")

if __name__ == "__main__":
    main()
