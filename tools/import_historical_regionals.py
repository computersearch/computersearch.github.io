#!/usr/bin/env python3
"""Manual historical Regional Championship backfill; daily importer is unchanged.

Provide confirmed Limitless tournament IDs from limitlesstcg.com/tournaments/<ID>.
Each selected event is fully downloaded again (no decklist caching).
"""
import argparse
import json
import re
import sys
from datetime import date

from import_limitless import api, import_one, labs_code, parse_date

SEASONS = {
    '2023-24': (date(2023, 9, 1), date(2024, 8, 31)),
    '2024-25': (date(2024, 9, 1), date(2025, 8, 31)),
    '2025-26': (date(2025, 9, 1), date(2026, 8, 31)),
    '2026-27': (date(2026, 9, 1), date(2027, 8, 31)),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--season', choices=SEASONS, required=True)
    parser.add_argument('--ids', default='', help='Comma/space-separated Limitless tournament IDs, e.g. 583,582')
    parser.add_argument('--discovered-file', default='', help='JSON from discover_historical_regionals.py')
    parser.add_argument('--batch', type=int, default=1, help='1-based batch number')
    parser.add_argument('--batch-size', type=int, default=5)
    parser.add_argument('--delay', type=float, default=0.5)
    args = parser.parse_args()
    ids = list(dict.fromkeys(re.findall(r'\d+', args.ids)))
    if not ids or len(ids) > 5:
        parser.error('No IDs in this batch; select an existing batch or supply 1-5 IDs.')
    start, end = SEASONS[args.season]
    success = 0
    for event_id in ids:
        try:
            code = labs_code(event_id)
            metadata = api('tournament', id=int(code), division='MA')
            if not isinstance(metadata, dict):
                raise ValueError('Missing tournament metadata')
            date_text = parse_date(metadata.get('date'))
            if not date_text:
                raise ValueError('Unknown tournament date; refusing to import into a selected season')
            event_date = date.fromisoformat(date_text)
            if not start <= event_date <= end:
                print(f'SKIP {event_id}: date {event_date} outside {args.season}', flush=True)
                continue
            # Explicit IDs are required: this tool never guesses historic events.
            if import_one(event_id, delay=args.delay):
                success += 1
        except Exception as exc:
            print(f'ERROR {event_id}: {exc}', flush=True)
    print(f'Historical backfill: {success}/{len(ids)} events imported', flush=True)
    if success != len(ids):
        sys.exit(1)


if __name__ == '__main__':
    main()
