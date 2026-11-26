#!/usr/bin/env python3
"""Full SuperPSX catalog scraper: games, updates, DLC and every visible host link.

Only records links publicly present in SuperPSX HTML. It does not bypass CAPTCHA,
login, anti-bot controls, link shorteners, or resolve temporary file URLs.
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

def kind(label):
    x = label.casefold()
    if re.search(r"\b(update|patch|actualizaci[oó]n|actualizacion|parche)\b", x):
        return "update"
    if re.search(r"\b(dlc|add[\s-]?on|addon|expansion|expansi[oó]n)\b", x):
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
            m = re.search(r"CUSA\d{5}", v, re.I)
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

def scrape_dll(url, game):
    r = S.get(url, timeout=35)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    meta = page_metadata(soup)
    found, seen = [], set()
    for table in soup.find_all("table"):
        for tr in table.find_all("tr"):
            cells = tr.find_all(["td", "th"])
            if len(cells) < 2:
                continue
            label = cells[0].get_text(" ", strip=True)
            for cell in cells[1:]:
                for a in cell.find_all("a", href=True):
                    href = urljoin(url, a["href"].strip())
                    p = urlparse(href)
                    if p.scheme not in ("http", "https") or not p.hostname or href in seen:
                        continue
                    seen.add(href)
                    found.append({
                        "title": game["name"], "game_page": game["url"],
                        "download_page": url, "type": kind(label),
                        "description": label, "link_label": a.get_text(" ", strip=True),
                        "host": p.hostname.lower(), "url": href,
                        **meta, "status": "visible_page_link"
                    })
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

    result = {"source": LIST_URL, "total_in_run": len(games), "processed": 0,
              "links": [], "errors": [], "note": "All publicly visible host links; no CAPTCHA bypass or temporary URL resolution."}
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
        OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"[{i}/{len(games)}] {name or url}: {len(result['links'])} links; {len(result['errors'])} errors", flush=True)
        time.sleep(max(0, args.delay))
    print(f"DONE: {result['processed']} pages; {len(result['links'])} links; {len(result['errors'])} errors")

if __name__ == "__main__":
    main()
