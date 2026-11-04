#!/usr/bin/env python3
"""Fetch the public Limitless metagame ranking into a change-only JSON snapshot."""
import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

URL = 'https://limitlesstcg.com/decks'
OUTPUT = Path(__file__).resolve().parents[1] / 'metagame' / 'rankings.json'


def parse_page(html):
    soup = BeautifulSoup(html, 'html.parser')
    table = next((t for t in soup.select('table') if {'deck', 'points', 'share'}.issubset(
        {th.get_text(' ', strip=True).lower() for th in t.select('th')})), None)
    if table is None:
        raise ValueError('Could not find Limitless Deck / Points / Share table')
    result = []
    for tr in table.select('tr'):
        cells = tr.find_all('td', recursive=False)
        if len(cells) < 5:
            continue
        # Rank | images | Deck | Points | Share
        link = cells[2].find('a', href=re.compile(r'/decks/'))
        if not link:
            continue
        name = link.get_text(' ', strip=True)
        pts = cells[3].get_text(' ', strip=True).replace(',', '').replace(' ', '')
        share = cells[4].get_text(' ', strip=True).replace(' ', '')
        if not name or not pts.isdigit() or not re.fullmatch(r'\d+(?:\.\d+)?%', share):
            raise ValueError(f'Invalid metagame row: {tr.get_text(" ", strip=True)}')
        result.append({'name': name, 'points': int(pts), 'share': share})
    return result, soup


def fetch(session, url):
    response = session.get(url, timeout=30)
    response.raise_for_status()
    return parse_page(response.text)


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default=URL, help='Limitless metagame URL with desired filters')
    args = parser.parse_args()
    with requests.Session() as session:
        session.headers.update({'User-Agent': 'ComputerSearch/1.0 (public metagame snapshot; daily)'})
        decks, soup = fetch(session, args.url)
        # Follow the pagination link only when the site exposes an explicit next-page URL.
        visited = {args.url}
        for _ in range(20):
            next_link = next((a for a in soup.select('a[href]') if a.get_text(' ', strip=True) in ('»', 'Next', '›')), None)
            if not next_link:
                break
            target = urljoin(args.url, next_link['href'])
            if target in visited or urlparse(target).netloc != urlparse(args.url).netloc:
                break
            visited.add(target)
            page_decks, soup = fetch(session, target)
            if not page_decks:
                break
            decks.extend(page_decks)
        if len(visited) > 20:
            raise ValueError('Pagination exceeded safety limit')
    if len(decks) < 10:
        raise ValueError(f'Refusing suspiciously small metagame table: {len(decks)} rows')
    seen = set()
    for d in decks:
        key = d['name'].casefold()
        if key in seen:
            raise ValueError(f'Duplicate archetype: {d["name"]}')
        seen.add(key)
    # Don't create commits for timestamps when the ranking is unchanged.
    previous = json.loads(OUTPUT.read_text()) if OUTPUT.exists() else None
    if previous and previous.get('source') == args.url and previous.get('decks') == decks:
        print(f'UNCHANGED: {len(decks)} archetypes; no file rewrite')
        return
    document = {'source': args.url, 'updated_at': datetime.now(timezone.utc).strftime('%Y-%m-%d'), 'decks': decks}
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + '\n')
    print(f'UPDATED: {len(decks)} archetypes')


if __name__ == '__main__':
    run()
