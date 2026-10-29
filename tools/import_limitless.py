#!/usr/bin/env python3
"""Computer Search: inspect Ciphermaniac's published tournament artifacts.

Ciphermaniac publishes precomputed LimitlessTCG tournament data in R2.
This importer uses its documented public data interface, NOT private scraper code.
It fails safely and never writes an incomplete/unverified tournament.

GitHub Actions: python tools/import_limitless.py --max-decks 100
Dependencies: Python standard library only.
"""
import argparse
import json
import re
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

BASE = 'https://r2.ciphermaniac.com/'
OUT = Path(__file__).resolve().parents[1] / 'tournaments'


def fetch(path):
    request = Request(BASE + path, headers={
        'User-Agent': 'ComputerSearch/1.0 (noncommercial tournament archive)',
        'Accept': 'application/json',
    })
    with urlopen(request, timeout=45) as response:
        return json.load(response)


def rows(obj, names):
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for name in names:
            if isinstance(obj.get(name), list):
                return obj[name]
    return []


def field(row, *names):
    for name in names:
        if row.get(name) is not None:
            return row[name]
    return None


def parse_cards(row):
    raw = field(row, 'cards', 'cardlist', 'decklist', 'list')
    if isinstance(raw, dict):
        raw = field(raw, 'cards', 'list', 'entries')
    if not isinstance(raw, list):
        return None
    cards = []
    for card in raw:
        if not isinstance(card, dict):
            return None
        quantity = field(card, 'quantity', 'qty', 'count', 'copies', 'amount')
        name = field(card, 'name', 'cardName', 'card')
        if isinstance(name, dict):
            name = name.get('name')
        set_code = field(card, 'set', 'setCode', 'set_code')
        number = field(card, 'number', 'collectorNumber', 'collector_number')
        try:
            quantity = int(quantity)
        except (ValueError, TypeError):
            return None
        if not (1 <= quantity <= 60 and name and set_code and number):
            return None
        cards.append({'quantity': quantity, 'name': str(name),
                      'set': str(set_code), 'number': str(number)})
    return cards if sum(card['quantity'] for card in cards) == 60 else None


def rank_of(row):
    value = field(row, 'placing', 'placement', 'place', 'rank', 'standing')
    if isinstance(value, str):
        match = re.search(r'\d+', value)
        value = match.group() if match else None
    try:
        value = int(value)
    except (ValueError, TypeError):
        return None
    return value if 1 <= value <= 64 else None


def name_of(row):
    value = field(row, 'pilot', 'player', 'playerName', 'name')
    if isinstance(value, dict):
        value = field(value, 'name', 'displayName')
    return value.strip() if isinstance(value, str) and value.strip() else None


def import_event(event, max_decks):
    prefix = 'reports/' + quote(event, safe='') + '/'
    print('Checking published report:', event, flush=True)
    try:
        deck_data = fetch(prefix + 'decks.json')
    except HTTPError as exc:
        if exc.code == 404:
            print('NO UPDATE: decks.json is not published at', prefix)
            return False
        raise
    deck_rows = rows(deck_data, ('decks', 'entries', 'items', 'data'))
    print('Deck records:', len(deck_rows), 'payload type:', type(deck_data).__name__, flush=True)
    if deck_rows:
        print('Deck fields:', sorted(deck_rows[0].keys()) if isinstance(deck_rows[0], dict) else 'non-object', flush=True)
    if len(deck_rows) > max_decks:
        print('INFO: --max-decks does not truncate verification of top 64')
    try:
        player_data = fetch(prefix + 'players.json')
        player_rows = rows(player_data, ('players', 'entries', 'results', 'items', 'data'))
    except HTTPError as exc:
        if exc.code != 404:
            raise
        player_rows = []
        print('INFO: players.json is not available')
    print('Player records:', len(player_rows), flush=True)
    ranked = {}
    for row in player_rows + deck_rows:
        if not isinstance(row, dict):
            continue
        rank = rank_of(row)
        name = name_of(row)
        if rank is None or name is None:
            continue
        previous = ranked.get(rank)
        if previous and previous['name'].casefold() != name.casefold():
            print('NO UPDATE: conflicting player at rank', rank)
            return False
        cards = parse_cards(row)
        if previous is None:
            previous = {'rank': rank, 'name': name, 'deck': None,
                        'decklist': None, 'decklist_url': None}
        previous['deck'] = field(row, 'archetype', 'deckName', 'deckType') or previous['deck']
        previous['decklist'] = cards or previous['decklist']
        ranked[rank] = previous
    if set(ranked) != set(range(1, 65)):
        print('NO UPDATE: only', len(ranked), 'of 64 placements verified')
        return False
    verified = sum(bool(item['decklist']) for item in ranked.values())
    if verified == 0:
        print('NO UPDATE: no complete 60-card decklists could be parsed')
        return False
    result = {'id': 'ciphermaniac-' + event[:10], 'name': event.split(', ', 1)[-1],
              'date': event[:10], 'source': BASE + prefix,
              'provider': 'Ciphermaniac (LimitlessTCG source)',
              'standings': [ranked[i] for i in range(1, 65)]}
    OUT.mkdir(parents=True, exist_ok=True)
    filename = 'ciphermaniac-' + event[:10] + '.json'
    (OUT / filename).write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    index_file = OUT / 'index.json'
    index = json.loads(index_file.read_text(encoding='utf-8')) if index_file.exists() else []
    index = [entry for entry in index if entry.get('id') != result['id']]
    index.append({'id': result['id'], 'name': result['name'], 'date': result['date'],
                  'file': filename, 'verified_decks': verified})
    index.sort(key=lambda item: item.get('date', ''), reverse=True)
    index_file.write_text(json.dumps(index, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('SUCCESS:', event, '- 64 placements and', verified, 'validated decklists')
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--max-decks', type=int, default=100)
    parser.add_argument('--event', help='Exact catalog event name')
    args = parser.parse_args()
    catalog = fetch('reports/tournaments.json')
    if not isinstance(catalog, list):
        raise ValueError('Unexpected tournament catalog format')
    events = [args.event] if args.event else [event for event in catalog
              if isinstance(event, str) and 'Regional Championship' in event]
    for event in events:
        try:
            if import_event(event, args.max_decks):
                return
        except (HTTPError, URLError, ValueError) as exc:
            print('SKIP:', event, '-', exc, flush=True)
    print('NO UPDATE: no complete report was available; existing tournament data preserved.')


if __name__ == '__main__':
    main()
