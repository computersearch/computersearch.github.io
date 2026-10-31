#!/usr/bin/env python3
"""Non-destructive Pokédata snapshot fetcher; does not touch tournament archives."""
import argparse
import datetime as dt
import json
import pathlib
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
EVENTS = ROOT / 'observer' / 'events.txt'
MANIFEST = ROOT / 'observer' / 'events.json'
DATA = ROOT / 'observer' / 'data'
MAX_BYTES = 12 * 1024 * 1024


def fetch(url):
    if not url.startswith('https://www.pokedata.ovh/standings2/standings/') or not url.endswith('.json'):
        raise ValueError('Source URL must be a Pokédata standings JSON endpoint')
    req = urllib.request.Request(url, headers={'User-Agent': 'ComputerSearchObserver/1.0 (+https://computersearch.github.io/)', 'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=35) as response:
        payload = response.read(MAX_BYTES + 1)
    if len(payload) > MAX_BYTES:
        raise ValueError('JSON too large')
    parsed = json.loads(payload)
    if not isinstance(parsed, (dict, list)) or not parsed:
        raise ValueError('Unexpected empty JSON structure')
    return parsed


def configured_events():
    """Read one Pokédata standings URL per line; ignore blanks and # comments."""
    import re
    urls = []
    seen = set()
    for lineno, line in enumerate(EVENTS.read_text(encoding='utf-8-sig').splitlines(), 1):
        url = line.strip()
        if not url or url.startswith('#'):
            continue
        match = re.fullmatch(r'https://www\.pokedata\.ovh/standings2/standings/([A-Za-z0-9_-]+)\.json', url)
        if not match:
            raise ValueError(f'Invalid Pokédata URL on events.txt line {lineno}: {url}')
        original_id = match.group(1)
        event_id = original_id.lower()
        if event_id in seen:
            continue
        seen.add(event_id)
        division = original_id.rsplit('_', 1)[-1] if '_' in original_id else ''
        urls.append({'id': event_id, 'name': original_id.replace('_', ' '), 'division': division, 'source': url, 'enabled': True})
    return urls


def event_title(raw, fallback):
    if isinstance(raw, dict):
        tournament = raw.get('tournament')
        if isinstance(tournament, dict) and tournament.get('title'):
            return str(tournament['title'])
    return fallback


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--event', help='Fetch only one configured event ID')
    args = parser.parse_args()
    config = configured_events()
    DATA.mkdir(parents=True, exist_ok=True)
    failed = 0
    selected = 0
    # Preserve names from the existing manifest if an endpoint is temporarily unavailable.
    try:
        previous = {e['id']: e for e in json.loads(MANIFEST.read_text(encoding='utf-8')).get('events', [])}
    except (OSError, ValueError, KeyError, TypeError):
        previous = {}
    for event in config:
        event_id = event['id']
        if event_id in previous:
            event['name'] = previous[event_id].get('name') or event['name']
        if args.event and args.event.lower() != event_id:
            continue
        selected += 1
        dest = DATA / (event_id + '.json')
        try:
            raw = fetch(event['source'])
            event['name'] = event_title(raw, event['name'])
            stamp = dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
            snapshot = {'event_id': event_id, 'event_name': event['name'], 'division': event['division'], 'source': event['source'], 'fetched_at': stamp, 'raw': raw}
            tmp = dest.with_suffix('.json.tmp')
            tmp.write_text(json.dumps(snapshot, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
            tmp.replace(dest)
            print(f'Fetched {event_id}: {len(json.dumps(raw))} characters')
        except (urllib.error.URLError, ValueError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            failed += 1
            print(f'FAILED {event_id}: {exc}; keeping existing snapshot')
    if not selected:
        print('No matching events selected')
    # Keep the browser-readable event dropdown in sync with events.txt.
    # Only publish events that already have a snapshot, so new URLs are selectable
    # as soon as their first fetch succeeds.
    published = [e for e in config if (DATA / (e['id'] + '.json')).exists()]
    MANIFEST.write_text(json.dumps({'events': published}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    if failed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
