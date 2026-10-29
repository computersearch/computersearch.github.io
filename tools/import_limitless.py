#!/usr/bin/env python3
"""Computer Search: import official Masters standings/decklists from Limitless Labs.

Adapted from Ciphermaniac's .github/scripts/download-tournament.py (MIT).
Copyright (c) 2025 rosematcha. See tools/CIPHERMANIAC-LICENSE.txt.
No R2 credentials or local Python installation needed (runs in GitHub Actions).
"""
import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE = 'https://limitlesstcg.com'
MEW = 'https://mew.limitlesstcg.com/labs/data/tcg'
LABS = 'https://labs.limitlesstcg.com'
OUT = Path(__file__).resolve().parents[1] / 'tournaments'
S = requests.Session()
S.headers.update({'User-Agent': 'ComputerSearch/1.0 (community tournament archive)'})


def fetch(url, json_data=False):
    last = None
    for attempt in range(3):
        try:
            response = S.get(url, timeout=35)
            response.raise_for_status()
            return response.json() if json_data else response.text
        except (requests.RequestException, ValueError) as exc:
            last = exc
            if attempt < 2:
                time.sleep(attempt + 1)
    raise RuntimeError(f'Cannot retrieve {url}: {last}')


def api(endpoint, **params):
    from urllib.parse import urlencode
    url = MEW + '/' + endpoint + '?' + urlencode(params)
    data = fetch(url, True)
    if not isinstance(data, dict) or data.get('ok') is not True:
        raise RuntimeError(f'Labs API did not return a successful response for {endpoint}: {str(data)[:180]}')
    return data.get('message')


def labs_code(tournament_id):
    if re.fullmatch(r'\d{4}', str(tournament_id)):
        return str(tournament_id)
    html = fetch(f'{BASE}/tournaments/{tournament_id}')
    match = re.search(r'https?://labs\.limitlesstcg\.com/(\d{4})/standings', html)
    if not match:
        raise RuntimeError(f'Tournament {tournament_id} has no discoverable Limitless Labs standings link')
    return match.group(1)


def recent_regionals(limit=3):
    soup = BeautifulSoup(fetch(BASE + '/tournaments'), 'html.parser')
    found = []
    for a in soup.select('a[href]'):
        href = a.get('href', '')
        match = re.search(r'(?:^|/)tournaments/(\d+)(?:[/?#]|$)', href)
        if match and 'regional' in a.get_text(' ', strip=True).lower():
            if match.group(1) not in found:
                found.append(match.group(1))
    return found[:limit]


def card_rows(payload):
    if not isinstance(payload, dict):
        return []
    cards = []
    for section, entries in payload.items():
        if not isinstance(entries, list):
            continue
        for item in entries:
            if not isinstance(item, dict):
                continue
            try:
                qty = int(item.get('count') or 0)
            except (ValueError, TypeError):
                return []
            name = str(item.get('name') or '').strip()
            set_code = str(item.get('set') or '').strip().upper()
            number = str(item.get('number') or '').strip()
            if qty < 1 or qty > 60 or not all((name, set_code, number)):
                return []
            cards.append({'quantity': qty, 'name': name, 'set': set_code, 'number': number})
    return cards if sum(c['quantity'] for c in cards) == 60 else []


def parse_date(value):
    text = str(value or '')
    if match := re.search(r'\b(20\d{2}-\d{2}-\d{2})\b', text):
        return match.group(1)
    if match := re.search(r'([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?(?:\s*[-–]\s*\d{1,2})?,?\s+(20\d{2})', text):
        try:
            return datetime.strptime(f'{match[1]} {match[2]} {match[3]}', '%B %d %Y').date().isoformat()
        except ValueError:
            pass
    return ''


def import_one(tournament_id, delay=0.5, max_decks=100):
    code = labs_code(tournament_id)
    tid = int(code)
    print(f'Checking Limitless tournament {tournament_id} -> Labs {code}', flush=True)
    meta = api('tournament', id=tid, division='MA')
    standings = api('standings', tournamentId=tid, division='MA')
    if not isinstance(meta, dict) or not isinstance(standings, list):
        raise RuntimeError('Invalid Labs metadata or standings response')
    players = {}
    for row in standings:
        try:
            rank = int(row.get('placement'))
        except (ValueError, TypeError, AttributeError):
            continue
        if rank not in range(1, 65) or rank in players:
            continue
        name = str(row.get('name') or '').strip()
        if not name:
            continue
        players[rank] = {'rank': rank, 'name': name, 'deck': row.get('deck_name') or '',
                         'decklist': None, 'decklist_url': None, '_tp_id': row.get('tp_id'),
                         '_published': row.get('decklist')}
    if len(players) != 64:
        print(f'NO UPDATE: only {len(players)} top-64 placements available', flush=True)
        return False
    verified = 0
    for rank in range(1, 65):
        player = players[rank]
        if str(player.pop('_published') or '0').lower() not in ('1', 'true'):
            player.pop('_tp_id')
            continue
        tp_id = player.pop('_tp_id')
        if tp_id is None or verified >= max_decks:
            continue
        try:
            payload = api('decklist', tournamentId=tid, playerId=int(tp_id))
            cards = card_rows(payload)
            if cards:
                player['decklist'] = cards
                player['decklist_url'] = f'{LABS}/{code}/standings'
                verified += 1
        except (RuntimeError, ValueError) as exc:
            print(f'SKIP rank {rank}: {exc}', flush=True)
        time.sleep(max(0.3, delay))
    if not verified:
        print('NO UPDATE: no verified 60-card decklists; existing data preserved', flush=True)
        return False
    date = parse_date(meta.get('date'))
    name = str(meta.get('name') or f'Regional Championship {tournament_id}').strip()
    source = f'{BASE}/tournaments/{tournament_id}' if len(str(tournament_id)) != 4 else f'{LABS}/{code}/standings'
    result = {'id': 'limitless-' + str(tournament_id), 'name': name, 'date': date,
              'source': source, 'standings': [players[i] for i in range(1, 65)]}
    OUT.mkdir(parents=True, exist_ok=True)
    filename = f'limitless-{tournament_id}.json'
    index_path = OUT / 'index.json'
    old = json.loads(index_path.read_text(encoding='utf-8')) if index_path.exists() else []
    if not isinstance(old, list):
        raise RuntimeError('Existing tournaments/index.json is not a list; refusing to overwrite')
    entry = {'id': result['id'], 'name': name, 'date': date, 'file': filename, 'source': source}
    updated = [x for x in old if x.get('id') != entry['id']] + [entry]
    updated.sort(key=lambda x: x.get('date') or '', reverse=True)
    (OUT / filename).write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    index_path.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'SUCCESS: {name}: 64 placements, {verified} verified 60-card decklists', flush=True)
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--tournament-id', help='Limitless tournament ID or four-digit Labs code')
    parser.add_argument('--max-decks', type=int, default=100)
    parser.add_argument('--delay', type=float, default=0.5)
    args = parser.parse_args()
    ids = [args.tournament_id] if args.tournament_id else recent_regionals()
    if not ids:
        raise RuntimeError('No Regional Championships found on tournament index')
    for event_id in ids:
        try:
            if import_one(event_id, args.delay, args.max_decks):
                return
        except RuntimeError as exc:
            print(f'SKIP {event_id}: {exc}', flush=True)
    raise RuntimeError('No validated import. Existing tournament data was preserved.')


if __name__ == '__main__':
    main()
