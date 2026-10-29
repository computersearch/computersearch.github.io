#!/usr/bin/env python3
"""Discover historical Pokémon TCG Regional IDs from Limitless public listings.

No guessed IDs: only event links explicitly labeled Regional Championship are kept.
Runs in GitHub Actions, which can access the live site.
"""
import argparse
import json
import re
from datetime import date
from urllib.parse import urljoin, urlparse, parse_qs

from bs4 import BeautifulSoup
from import_limitless import BASE, fetch, parse_date

SEASONS = {
    '2023-24': (date(2023, 9, 1), date(2024, 8, 31)),
    '2024-25': (date(2024, 9, 1), date(2025, 8, 31)),
    '2025-26': (date(2025, 9, 1), date(2026, 8, 31)),
    '2026-27': (date(2026, 9, 1), date(2027, 8, 31)),
}
REGIONAL = re.compile(r'\bregional(?:\s+championship)?\b', re.I)
EVENT = re.compile(r'^/tournaments/(\d+)/?$')


def discover(season, max_pages=30):
    start, end = SEASONS[season]
    queue = [BASE + '/tournaments', BASE + '/tournaments?show=all']
    visited, found = set(), {}
    while queue and len(visited) < max_pages:
        url = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)
        try:
            soup = BeautifulSoup(fetch(url), 'html.parser')
        except Exception as exc:
            print(f'WARNING: listing unavailable: {url}: {exc}', flush=True)
            continue
        for a in soup.select('a[href]'):
            absolute = urljoin(url, a['href'])
            parsed = urlparse(absolute)
            if parsed.netloc != urlparse(BASE).netloc:
                continue
            match = EVENT.fullmatch(parsed.path)
            if match:
                title = a.get_text(' ', strip=True)
                context = a.find_parent('tr') or a.parent
                text = context.get_text(' ', strip=True) if context else title
                if not REGIONAL.search(title) and not REGIONAL.search(text):
                    continue
                if re.search(r'\b(?:world|international|side event)\b', title, re.I):
                    continue
                date_text = parse_date(text)
                if date_text:
                    try:
                        event_date = date.fromisoformat(date_text)
                    except ValueError:
                        continue
                    if start <= event_date <= end:
                        found[match[1]] = {'id': match[1], 'name': title, 'date': date_text,
                                           'url': absolute}
                # Missing date is intentionally not guessed; a page's date must be verified.
            elif parsed.path.rstrip('/') == '/tournaments':
                # Follow pagination/filter links on the official tournament listing.
                qs = parse_qs(parsed.query)
                if qs and any(k in qs for k in ('page', 'show', 'year', 'season', 'offset')):
                    if absolute not in visited and absolute not in queue:
                        queue.append(absolute)
    return sorted(found.values(), key=lambda e: (e['date'], int(e['id'])))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--season', required=True, choices=SEASONS)
    p.add_argument('--max-pages', type=int, default=30)
    p.add_argument('--output', default='historical-regional-ids.json')
    args = p.parse_args()
    events = discover(args.season, args.max_pages)
    Path = __import__('pathlib').Path
    Path(args.output).write_text(json.dumps(events, indent=2, ensure_ascii=False) + '\n')
    print(f'Discovered {len(events)} dated Regional Championship IDs for {args.season}')
    for e in events:
        print(f"  {e['date']} | {e['id']} | {e['name']}")
    if not events:
        raise SystemExit('No verified event IDs discovered. Listing may not expose historical pages; no guessed IDs imported.')


if __name__ == '__main__':
    main()
