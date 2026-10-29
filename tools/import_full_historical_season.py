#!/usr/bin/env python3
"""Import every discovered Regional for one season; preserve partial successes."""
import argparse
import json
import subprocess
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--season', required=True, choices=['2023-24', '2024-25', '2025-26', '2026-27'])
    parser.add_argument('--discovered-file', required=True)
    args = parser.parse_args()
    events = json.loads(Path(args.discovered_file).read_text(encoding='utf-8'))
    ids = list(dict.fromkeys(str(event['id']) for event in events))
    if not ids:
        parser.error('No discovered Regional IDs. Nothing imported.')
    print(f'Full-season import: {len(ids)} discovered Regional Championships', flush=True)
    succeeded, failed = [], []
    for number, event_id in enumerate(ids, 1):
        print(f'\n=== [{number}/{len(ids)}] Importing {event_id} ===', flush=True)
        result = subprocess.run([sys.executable, 'tools/import_historical_regionals.py',
                                 '--season', args.season, '--ids', event_id], check=False)
        (succeeded if result.returncode == 0 else failed).append(event_id)
    print(f'\nCompleted: {len(succeeded)} succeeded; {len(failed)} failed.', flush=True)
    if failed:
        print('Failed/unsupported IDs: ' + ', '.join(failed), flush=True)
    Path('historical-import-summary.txt').write_text(
        f'Season: {args.season}\nDiscovered: {len(ids)}\nImported: {len(succeeded)}\n'
        f'Failed: {len(failed)}\nFailed IDs: {", ".join(failed)}\n', encoding='utf-8')
    # Return success for partial imports so the following step can commit the good files.
    # If every event failed, fail the workflow and report the underlying errors.
    if not succeeded:
        sys.exit('No tournaments imported. Check the Labs-link errors above; older seasons may not be supported.')


if __name__ == '__main__':
    main()
