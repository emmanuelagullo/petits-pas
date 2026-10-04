#!/usr/bin/env python3
"""Préparer manifestes et notes avec les octets construits, sans publication."""
import argparse
import json
from pathlib import Path
from publication import describe, manifest, release_notes

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--mode', required=True, choices=['programme', 'navigateur'])
parser.add_argument('--target', required=True)
parser.add_argument('--destination', type=Path, required=True)
parser.add_argument('files', nargs='+', type=Path)
args = parser.parse_args()
record = manifest(args.mode, args.target, args.files)
notes = args.destination.parent / 'notes-version.md'
notes.write_text(release_notes(record['tag']), encoding='utf-8')
record['files'].append(describe(notes))
args.destination.write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
