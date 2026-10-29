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


def recent_regionals(limit=8):
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


def tournament_display_name(tournament_id, metadata_name):
    """Prefer a real event title; never show a generic numeric placeholder."""
    raw = str(metadata_name or '').strip()
    if raw and not re.fullmatch(r'(?:Regional Championship|Tournament)\\s*#?\\d+', raw, re.I):
        return raw
    # Limitless's public event page often has the city in its heading/title,
    # whereas the Labs metadata can contain only a generic event number.
    if str(tournament_id).isdigit() and len(str(tournament_id)) != 4:
        try:
            page = BeautifulSoup(fetch(f'{BASE}/tournaments/{tournament_id}'), 'html.parser')
            candidates = []
            for node in page.select('h1, meta[property="og:title"], title'):
                label = node.get('content', '') if node.name == 'meta' else node.get_text(' ', strip=True)
                label = re.split(r'\\s+[|–—]\\s+Limitless(?:TCG)?', label, maxsplit=1, flags=re.I)[0].strip()
                if label:
                    candidates.append(label)
            for label in candidates:
                if 'regional' in label.lower() and not re.fullmatch(r'Regional Championship\\s*#?\\d+', label, re.I):
                    return label
        except (RuntimeError, requests.RequestException) as exc:
            print(f'WARNING: event title lookup failed for {tournament_id}: {exc}', flush=True)
    # Grounded IDs from the tournament list; fallback only if no full title found.
    known = {'583': 'Puebla Regional Championship',
             '582': 'Nice Regional Championship',
             '581': 'Louisville Regional Championship'}
    return known.get(str(tournament_id), raw or f'Tournament {tournament_id}')


def import_one(tournament_id, delay=0.3, max_decks=None):
    code = labs_code(tournament_id)
    tid = int(code)
    print(f'Checking Limitless tournament {tournament_id} -> Labs {code}', flush=True)
    meta = api('tournament', id=tid, division='MA')
    standings = api('standings', tournamentId=tid, division='MA')
    if not isinstance(meta, dict) or not isinstance(standings, list):
        raise RuntimeError('Invalid Labs metadata or standings response')
    # Limitless Labs explicitly marks Day 2 players with day2 == 1.
    # Never infer qualification from final rank or a top-64 cutoff.
    players = {}
    for row in standings:
        if not isinstance(row, dict):
            continue
        try:
            is_day2 = int(row.get('day2') or 0) == 1
            rank = int(row.get('placement'))
        except (ValueError, TypeError):
            continue
        if not is_day2 or rank < 1 or rank in players:
            continue
        name = str(row.get('name') or '').strip()
        if not name:
            continue
        players[rank] = {'rank': rank, 'name': name, 'deck': row.get('deck_name') or '',
                         'day2': True, 'decklist': None, 'decklist_url': None,
                         '_tp_id': row.get('tp_id'), '_published': row.get('decklist')}
    if not players:
        print('NO UPDATE: Labs did not explicitly identify any Day 2 players; existing data preserved', flush=True)
        return False
    print(f'Full Masters standings: {len(standings)}; confirmed Day 2 participants: {len(players)}', flush=True)
    verified = 0
    for rank in sorted(players):
        player = players[rank]
        if str(player.pop('_published') or '0').lower() not in ('1', 'true'):
            player.pop('_tp_id')
            continue
        tp_id = player.pop('_tp_id')
        if tp_id is None:
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
        print('WARNING: No published 60-card Day 2 decklists were verified; saving confirmed Day 2 standings only', flush=True)
    date = parse_date(meta.get('date'))
    name = tournament_display_name(tournament_id, meta.get('name'))
    source = f'{BASE}/tournaments/{tournament_id}' if len(str(tournament_id)) != 4 else f'{LABS}/{code}/standings'
    result = {'id': 'limitless-' + str(tournament_id), 'name': name, 'date': date,
              'source': source, 'day2_only': True, 'standings': [players[i] for i in sorted(players)]}
    OUT.mkdir(parents=True, exist_ok=True)
    filename = f'limitless-{tournament_id}.json'
    index_path = OUT / 'index.json'
    old = json.loads(index_path.read_text(encoding='utf-8')) if index_path.exists() else []
    if not isinstance(old, list):
        raise RuntimeError('Existing tournaments/index.json is not a list; refusing to overwrite')
    entry = {'id': result['id'], 'name': name, 'date': date, 'file': filename, 'source': source, 'day2_only': True, 'day2_players': len(players), 'verified_decks': verified}
    updated = [x for x in old if x.get('id') != entry['id']] + [entry]
    updated.sort(key=lambda x: x.get('date') or '', reverse=True)
    (OUT / filename).write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    index_path.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'SUCCESS: {name}: {len(players)} confirmed Day 2 players (all ranks), {verified} verified 60-card decklists', flush=True)
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--tournament-id', help='Limitless tournament ID or four-digit Labs code')
    parser.add_argument('--max-decks', type=int, default=None, help='Deprecated; all published Day 2 decklists are imported regardless of this value')
    parser.add_argument('--delay', type=float, default=0.5)
    parser.add_argument('--limit', type=int, default=8, help='Number of recent Regionals to check')
    args = parser.parse_args()
    ids = [args.tournament_id] if args.tournament_id else recent_regionals(max(1, args.limit))
    if not ids:
        raise RuntimeError('No Regional Championships found on tournament index')
    successes = 0
    failures = 0
    for event_id in ids:
        try:
            if import_one(event_id, args.delay, args.max_decks):
                successes += 1
            else:
                failures += 1
        except (RuntimeError, requests.RequestException, ValueError) as exc:
            failures += 1
            print(f'SKIP {event_id}: {exc}', flush=True)
    print(f'IMPORT SUMMARY: {successes} tournaments updated; {failures} unavailable or incomplete', flush=True)
    if not successes:
        print('NO UPDATE: existing tournament data preserved', flush=True)


if __name__ == '__main__':
    main()
