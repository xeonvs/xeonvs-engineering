#!/usr/bin/env python3
"""Validate the public marketplace and optionally checked-out source bundles."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CODEX_CATALOG = ROOT / '.agents/plugins/marketplace.json'
CLAUDE_CATALOG = ROOT / '.claude-plugin/marketplace.json'
PROVENANCE = ROOT / 'PROVENANCE.json'
EXPECTED_NAMES = ['engineering-workflow', 'tgrep-search']
FORBIDDEN_TEXT = re.compile(
    r'(?<![A-Za-z0-9])(' + '|'.join((
        r'ghp_[A-Za-z0-9]{20,}', r'github_pat_[A-Za-z0-9_]{20,}',
        r'glpat-[A-Za-z0-9_-]{20,}', r'AKIA[0-9A-Z]{16}',
        r'sk-[A-Za-z0-9_-]{20,}', r'xox[baprs]-[A-Za-z0-9-]{20,}',
        r'AIZ' + r'a[0-9A-Za-z_-]{20,}',
        r'-----BEGIN [A-Z ]+PRIVATE KEY-----',
        r'/' + r'Users/[A-Za-z0-9._-]+/(?!\[A-Za-z0-9._-\])',
    )) + r')'
)


def fail(message: str) -> None:
    raise ValueError(message)


def tree_digest(root: Path) -> str:
    if not root.is_dir():
        fail(f'missing directory: {root}')
    digest = hashlib.sha256()
    for path in sorted(root.rglob('*')):
        relative = path.relative_to(root)
        if path.is_symlink():
            fail(f'symlink is not allowed: {relative}')
        if path.is_dir():
            continue
        if not path.is_file():
            fail(f'unsupported filesystem entry: {relative}')
        name, data = relative.as_posix().encode(), path.read_bytes()
        digest.update(len(name).to_bytes(4, 'big'))
        digest.update(name)
        digest.update(len(data).to_bytes(8, 'big'))
        digest.update(data)
    return digest.hexdigest()


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f'invalid JSON in {path.relative_to(ROOT)}: {exc}')
    if not isinstance(value, dict):
        fail(f'JSON object required in {path.relative_to(ROOT)}')
    return value


def tracked_files() -> list[Path]:
    result = subprocess.run(
        ['git', '-C', str(ROOT), 'ls-files', '-z'],
        text=False, capture_output=True, check=False,
    )
    if result.returncode:
        fail('cannot enumerate tracked public files')
    return [ROOT / item.decode() for item in result.stdout.split(b'\0') if item]


def public_hygiene() -> None:
    for path in tracked_files():
        relative = path.relative_to(ROOT)
        if path.is_symlink():
            fail(f'symlink is not allowed: {relative}')
        try:
            content = path.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            fail(f'non-text public artifact: {relative}')
        if FORBIDDEN_TEXT.search(content):
            fail(f'forbidden public-content pattern: {relative}')


def git_revision(path: Path, revision: str) -> str:
    result = subprocess.run(
        ['git', '-C', str(path), 'rev-parse', revision],
        text=True, capture_output=True, check=False,
    )
    if result.returncode:
        fail(f'cannot resolve source revision {revision!r} for {path}: {result.stderr.strip()}')
    return result.stdout.strip()


def validate_catalog(sources: dict[str, Path]) -> None:
    provenance = read_json(PROVENANCE)
    if provenance.get('schema_version') != 1 or provenance.get('catalog_version') != '1.0.0':
        fail('unsupported provenance identity')
    bundles = provenance.get('bundles')
    if not isinstance(bundles, list) or not all(isinstance(item, dict) for item in bundles):
        fail('provenance bundles must be objects')
    names = [item.get('name') for item in bundles]
    if names != EXPECTED_NAMES:
        fail('provenance bundle order or identities drifted')
    if sources and set(sources) != set(names):
        fail('sources must cover exactly the catalog bundles')

    codex, claude = read_json(CODEX_CATALOG), read_json(CLAUDE_CATALOG)
    if codex.get('name') != 'xeonvs-engineering' or codex.get('interface', {}).get('displayName') != 'Xeonvs Engineering':
        fail('Codex catalog identity drift')
    if claude.get('name') != 'xeonvs-engineering' or claude.get('owner', {}).get('name') != 'xeonvs':
        fail('Claude catalog identity drift')
    codex_plugins, claude_plugins = codex.get('plugins'), claude.get('plugins')
    if not isinstance(codex_plugins, list) or not isinstance(claude_plugins, list):
        fail('catalog plugin arrays required')
    if not all(isinstance(entry, dict) for entry in [*codex_plugins, *claude_plugins]):
        fail('catalog plugin arrays must contain objects')
    if [entry.get('name') for entry in codex_plugins] != names or [entry.get('name') for entry in claude_plugins] != names:
        fail('catalog plugin order or identities drifted')

    for item in bundles:
        name, bundle = item['name'], ROOT / 'plugins' / item['name']
        expected_path = f'./plugins/{name}'
        if tree_digest(bundle) != item.get('bundle_sha256'):
            fail(f'catalog bundle checksum drift: {name}')
        codex_entry = next(entry for entry in codex_plugins if entry['name'] == name)
        if codex_entry.get('source') != {'source': 'local', 'path': expected_path}:
            fail(f'Codex local source drift: {name}')
        if codex_entry.get('policy') != {'installation': 'AVAILABLE', 'authentication': 'ON_INSTALL'}:
            fail(f'Codex policy drift: {name}')
        if codex_entry.get('category') != 'Developer Tools':
            fail(f'Codex category drift: {name}')
        claude_entry = next(entry for entry in claude_plugins if entry['name'] == name)
        if claude_entry.get('source') != expected_path or claude_entry.get('category') != 'Developer Tools':
            fail(f'Claude catalog entry drift: {name}')

        codex_manifest = read_json(bundle / '.codex-plugin/plugin.json')
        claude_manifest = read_json(bundle / '.claude-plugin/plugin.json')
        for manifest in (codex_manifest, claude_manifest):
            if manifest.get('name') != name or manifest.get('version') != item.get('version'):
                fail(f'manifest identity drift: {name}')
            if manifest.get('repository') != item.get('source_repository'):
                fail(f'manifest source repository drift: {name}')
        if codex_manifest.get('skills') != './skills/' or not (bundle / 'skills').is_dir():
            fail(f'Codex skill layout drift: {name}')

        source = sources.get(name)
        if source is not None:
            if git_revision(source, 'HEAD') != item.get('source_commit'):
                fail(f'source checkout revision drift: {name}')
            if git_revision(source, f"{item['source_tag']}^{{}}") != item.get('source_commit'):
                fail(f'source tag does not resolve to recorded commit: {name}')
            if tree_digest(source / item['source_path']) != tree_digest(bundle):
                fail(f'source bundle bytes differ: {name}')
    public_hygiene()


def parse_sources(values: list[str]) -> dict[str, Path]:
    sources: dict[str, Path] = {}
    for value in values:
        name, separator, raw_path = value.partition('=')
        if not separator or not name or not raw_path or name in sources:
            fail(f'source must be unique NAME=PATH: {value}')
        sources[name] = Path(raw_path).resolve()
    return sources


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', action='append', default=[], metavar='NAME=PATH')
    args = parser.parse_args()
    try:
        validate_catalog(parse_sources(args.source))
    except ValueError as exc:
        print(f'catalog validation failed: {exc}')
        return 1
    print('catalog validation passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
