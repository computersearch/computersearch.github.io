#!/usr/bin/env python3
"""Discover verified Regional IDs from paginated Limitless tournament database."""
import argparse
import json
import re
import time
from datetime import date, datetime
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup

SEASONS = {'2023-24': (date(2023,9,1), date(2024,8,31)),
           '2024-25': (date(2024,9,1), date(2025,8,31)),
           '2025-26': (date(2025,9,1), date(2026,8,31)),
           '2026-27': (date(2026,9,1), date(2027,8,31))}
BASE = 'https://limitlesstcg.com/tournaments'
LINK = re.compile(r'^/tournaments/(\d+)/?$')
DATE = re.compile(r'\b(\d{1,2}\s+[A-Za-z]{3}\s+\d{2,4})\b')

def discover(season, max_pages=40):
    first, last = SEASONS[season]
    session = requests.Session()
    session.headers['User-Agent'] = 'ComputerSearch/1.0 (historical tournament discovery)'
    found = {}
    pages_checked = 0
    for page in range(1, max_pages + 1):
        url = BASE + f'?page={page}'
        response = session.get(url, timeout=40)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        rows = soup.select('tr')
        on_page = 0
        for tr in rows:
            text = tr.get_text(' ', strip=True)
            mdate = DATE.search(text)
            if not mdate:
                continue
            raw_date = mdate.group(1)
            event_date = None
            for fmt in ('%d %b %y', '%d %b %Y'):
                try:
                    event_date = datetime.strptime(raw_date, fmt).date()
                    break
                except ValueError:
                    pass
            if event_date is None or not first <= event_date <= last:
                continue
            for a in tr.select('a[href]'):
                full = urljoin(BASE, a['href'])
                parsed = urlparse(full)
                if parsed.netloc not in ('limitlesstcg.com', 'www.limitlesstcg.com'):
                    continue
                match = LINK.fullmatch(parsed.path)
                title = a.get_text(' ', strip=True)
                if match and re.match(r'^Regional\b', title, re.I):
                    found[match.group(1)] = {'id': match.group(1), 'name': title,
                                              'date': event_date.isoformat(), 'url': full}
                    on_page += 1
        pages_checked += 1
        print(f'Page {page}: {on_page} qualifying Regionals; total {len(found)}', flush=True)
        # Stop on an empty listing page. Otherwise scan all requested pages:
        # site sorting and season filters may not be stable.
        if not rows or not soup.select('a[href*="/tournaments/"]'):
            break
        time.sleep(0.5)
    print(f'Scanned {pages_checked} pages', flush=True)
    return sorted(found.values(), key=lambda e: (e['date'], int(e['id'])))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--season', required=True, choices=SEASONS)
    parser.add_argument('--max-pages', type=int, default=40)
    parser.add_argument('--output', default='historical-regional-ids.json')
    args = parser.parse_args()
    events = discover(args.season, args.max_pages)
    from pathlib import Path
    Path(args.output).write_text(json.dumps(events, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    for e in events:
        print(f"{e['date']} | {e['id']} | {e['name']}")
    print(f'Discovered {len(events)} Regional Championship IDs for {args.season}', flush=True)
    if not events:
        raise SystemExit('No verified IDs found; check listing pagination in workflow logs.')

if __name__ == '__main__':
    main()
