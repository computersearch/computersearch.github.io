#!/usr/bin/env python3
"""Non-destructive Pokédata snapshot fetcher; does not touch tournament archives."""
import argparse
import datetime as dt
import json
import pathlib
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
EVENTS = ROOT / 'observer' / 'events.json'
DATA = ROOT / 'observer' / 'data'
MAX_BYTES = 12 * 1024 * 1024


def fetch(event):
    url = event['source']
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--event', help='Fetch only one configured event ID')
    args = parser.parse_args()
    config = json.loads(EVENTS.read_text(encoding='utf-8'))
    DATA.mkdir(parents=True, exist_ok=True)
    failed = 0
    selected = 0
    for event in config['events']:
        if not event.get('enabled', True) or (args.event and args.event != event['id']):
            continue
        event_id = event['id']
        if not event_id.replace('_', '').replace('-', '').isalnum():
            raise ValueError('Invalid event ID')
        selected += 1
        dest = DATA / (event_id + '.json')
        try:
            raw = fetch(event)
            stamp = dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
            snapshot = {'event_id': event_id, 'event_name': event['name'], 'division': event.get('division', ''), 'source': event['source'], 'fetched_at': stamp, 'raw': raw}
            tmp = dest.with_suffix('.json.tmp')
            tmp.write_text(json.dumps(snapshot, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
            tmp.replace(dest)
            print(f'Fetched {event_id}: {len(json.dumps(raw))} characters')
        except (urllib.error.URLError, ValueError, TimeoutError, OSError) as exc:
            failed += 1
            print(f'FAILED {event_id}: {exc}; keeping existing snapshot')
    if not selected:
        print('No enabled events selected')
    if failed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
