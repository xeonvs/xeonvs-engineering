#!/usr/bin/env python3
"""Validate the public marketplace, its source policy, and its local bundles."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import subprocess
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CODEX_CATALOG = ROOT / '.agents/plugins/marketplace.json'
CLAUDE_CATALOG = ROOT / '.claude-plugin/marketplace.json'
UPSTREAMS = ROOT / 'UPSTREAMS.json'
PROVENANCE = ROOT / 'PROVENANCE.json'
LOGO_SVG = ROOT / 'assets/logo.svg'
LOGO_PNG = ROOT / 'assets/logo.png'
ICON_FIELDS = {
    'composerIcon': (128, 128),
    'logo': (1024, 1024),
    'logoDark': (1024, 1024),
}
EXPECTED_NAMES = ['engineering-workflow', 'tgrep-search']
SHA = re.compile(r'^[0-9a-f]{40}$')
NAME = re.compile(r'^[a-z0-9-]+$')
REPOSITORY = re.compile(r'^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$')
# Catalog releases contain stable packages only.  Keep this deliberately
# identical to the synchronizer's accepted version form.
SEMVER = re.compile(r'^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$')
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


def validate_opaque_png(path: Path, dimensions: tuple[int, int], label: str) -> None:
    try:
        png = path.read_bytes()
    except OSError as exc:
        fail(f'missing {label}: {exc}')
    if png[:8] != b'\x89PNG\r\n\x1a\n' or len(png) < 45:
        fail(f'invalid PNG: {label}')
    width, height, bit_depth, color_type, compression, filtering, interlace = struct.unpack(
        '>IIBBBBB', png[16:29]
    )
    if (width, height) != dimensions or (bit_depth, color_type) != (8, 2):
        fail(f'{label} must be {dimensions[0]}x{dimensions[1]} fully opaque RGB')
    if (compression, filtering, interlace) != (0, 0, 0):
        fail(f'unsupported PNG encoding: {label}')
    offset, idat, seen_ihdr, seen_iend = 8, [], False, False
    while offset < len(png):
        if offset + 12 > len(png):
            fail(f'truncated PNG chunk: {label}')
        length = int.from_bytes(png[offset:offset + 4], 'big')
        chunk_type = png[offset + 4:offset + 8]
        chunk_end = offset + 12 + length
        if chunk_end > len(png):
            fail(f'truncated PNG chunk: {label}')
        chunk_data = png[offset + 8:offset + 8 + length]
        expected_crc = int.from_bytes(png[offset + 8 + length:chunk_end], 'big')
        if zlib.crc32(chunk_data, zlib.crc32(chunk_type)) != expected_crc:
            fail(f'invalid PNG checksum: {label}')
        if chunk_type == b'IHDR':
            if seen_ihdr or offset != 8 or length != 13:
                fail(f'invalid PNG header order: {label}')
            seen_ihdr = True
        elif chunk_type == b'IDAT':
            idat.append(chunk_data)
        elif chunk_type == b'IEND':
            if length or chunk_end != len(png):
                fail(f'invalid PNG ending: {label}')
            seen_iend = True
        offset = chunk_end
    if not seen_ihdr or not seen_iend or not idat:
        fail(f'incomplete PNG: {label}')
    try:
        pixels = zlib.decompress(b''.join(idat))
    except zlib.error:
        fail(f'invalid PNG pixel stream: {label}')
    row_size = 1 + dimensions[0] * 3
    if len(pixels) != dimensions[1] * row_size:
        fail(f'invalid PNG pixel dimensions: {label}')
    if any(pixels[row * row_size] > 4 for row in range(dimensions[1])):
        fail(f'invalid PNG row filter: {label}')


def declared_binary_assets() -> dict[Path, tuple[int, int]]:
    assets = {Path('assets/logo.png'): (1024, 1024)}
    for name in EXPECTED_NAMES:
        bundle = ROOT / 'plugins' / name
        manifest = read_json(bundle / '.codex-plugin/plugin.json')
        interface = manifest.get('interface')
        if not isinstance(interface, dict):
            fail(f'Codex interface metadata missing: {name}')
        present = {field for field in ICON_FIELDS if field in interface}
        if present and present != set(ICON_FIELDS):
            fail(f'incomplete Codex icon metadata: {name}')
        if present:
            brand_color = interface.get('brandColor')
            if not isinstance(brand_color, str) or not re.fullmatch(r'#[0-9A-Fa-f]{6}', brand_color):
                fail(f'invalid Codex brand color: {name}')
        for field in present:
            raw = interface[field]
            if not isinstance(raw, str) or not raw.startswith('./'):
                fail(f'invalid Codex icon path: {name}:{field}')
            relative = Path(raw.removeprefix('./'))
            if relative.is_absolute() or '..' in relative.parts or relative.suffix.lower() != '.png':
                fail(f'unsafe Codex icon path: {name}:{field}')
            public_path = Path('plugins') / name / relative
            if public_path in assets and assets[public_path] != ICON_FIELDS[field]:
                fail(f'conflicting Codex icon path: {name}:{field}')
            validate_opaque_png(ROOT / public_path, ICON_FIELDS[field], f'{name}:{field}')
            assets[public_path] = ICON_FIELDS[field]
        claude = read_json(bundle / '.claude-plugin/plugin.json')
        if any(field in claude for field in (*ICON_FIELDS, 'brandColor')):
            fail(f'unsupported Claude image metadata: {name}')
    return assets


def public_files() -> list[Path]:
    commands = (
        ['git', '-C', str(ROOT), 'ls-files', '-z'],
        ['git', '-C', str(ROOT), 'ls-files', '--others', '--exclude-standard', '-z'],
    )
    results: set[Path] = set()
    for command in commands:
        result = subprocess.run(command, text=False, capture_output=True, check=False)
        if result.returncode:
            fail('cannot enumerate public files')
        results.update(ROOT / item.decode() for item in result.stdout.split(b'\0') if item)
    return sorted(results)


def public_hygiene() -> None:
    binary_assets = declared_binary_assets()
    for path in public_files():
        relative = path.relative_to(ROOT)
        if path.is_symlink():
            fail(f'symlink is not allowed: {relative}')
        try:
            content = path.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            dimensions = binary_assets.get(relative)
            if dimensions is None:
                fail(f'non-text public artifact: {relative}')
            validate_opaque_png(path, dimensions, relative.as_posix())
            continue
        if FORBIDDEN_TEXT.search(content):
            fail(f'forbidden public-content pattern: {relative}')


def git_revision(path: Path) -> str:
    result = subprocess.run(['git', '-C', str(path), 'rev-parse', 'HEAD'], text=True, capture_output=True, check=False)
    if result.returncode:
        fail(f'cannot read source revision for {path}: {result.stderr.strip()}')
    return result.stdout.strip()


def validate_source_policy(entry: dict, record: dict) -> None:
    name = record['name']
    if entry.get('repository') != record['source_repository'].removeprefix('https://github.com/'):
        fail(f'upstream repository drift: {name}')
    if entry.get('bundle_path') != record.get('source_path') or entry.get('source_policy') != record.get('source_policy'):
        fail(f'upstream policy or path drift: {name}')
    policy, ref = record.get('source_policy'), record.get('source_ref')
    if policy == 'latest-tag':
        if 'ref' in entry or not isinstance(ref, str) or not ref.startswith('v') or not SEMVER.fullmatch(ref[1:]):
            fail(f'tag source policy drift: {name}')
    else:
        fail(f'unsupported source policy: {name}')


def validate_catalog(sources: dict[str, Path]) -> None:
    if not LOGO_SVG.is_file() or not LOGO_PNG.is_file():
        fail('marketplace branding assets are missing')
    validate_opaque_png(LOGO_PNG, (1024, 1024), 'marketplace logo')
    provenance = read_json(PROVENANCE)
    bundles = provenance.get('bundles')
    if provenance.get('schema_version') != 1 or provenance.get('catalog_version') != '1.0.0':
        fail('unsupported provenance identity')
    if not isinstance(bundles, list) or not all(isinstance(item, dict) for item in bundles):
        fail('provenance bundles must be objects')
    names = [item.get('name') for item in bundles]
    if names != EXPECTED_NAMES:
        fail('provenance bundle order or identities drifted')
    if sources and set(sources) != set(names):
        fail('sources must cover exactly the catalog bundles')

    upstream_config = read_json(UPSTREAMS)
    upstreams = upstream_config.get('plugins')
    if upstream_config.get('schema_version') != 1 or not isinstance(upstreams, list) or not all(isinstance(entry, dict) for entry in upstreams):
        fail('upstream configuration must contain plugin objects')
    if [entry.get('name') for entry in upstreams] != names:
        fail('upstream plugin order or identities drifted')

    codex, claude = read_json(CODEX_CATALOG), read_json(CLAUDE_CATALOG)
    if any('logo' in entry for entry in (codex, claude, *codex.get('plugins', []), *claude.get('plugins', []))):
        fail('unsupported marketplace logo field')
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

    for record, upstream in zip(bundles, upstreams, strict=True):
        name = record['name']
        if not isinstance(name, str) or not NAME.fullmatch(name):
            fail('invalid bundle name')
        if set(upstream) != {'name', 'repository', 'bundle_path', 'source_policy'}:
            fail(f'unsupported upstream configuration fields: {name}')
        if not isinstance(upstream.get('repository'), str) or not REPOSITORY.fullmatch(upstream['repository']):
            fail(f'invalid upstream repository: {name}')
        validate_source_policy(upstream, record)
        if not isinstance(record.get('source_repository'), str) or not SHA.fullmatch(record.get('source_commit', '')):
            fail(f'provenance source identity drift: {name}')
        bundle, expected_path = ROOT / 'plugins' / name, f'./plugins/{name}'
        if tree_digest(bundle) != record.get('bundle_sha256'):
            fail(f'catalog bundle checksum drift: {name}')
        codex_entry = next(entry for entry in codex_plugins if entry['name'] == name)
        if codex_entry.get('source') != {'source': 'local', 'path': expected_path}:
            fail(f'Codex local source drift: {name}')
        if codex_entry.get('policy') != {'installation': 'AVAILABLE', 'authentication': 'ON_INSTALL'} or codex_entry.get('category') != 'Developer Tools':
            fail(f'Codex catalog policy drift: {name}')
        claude_entry = next(entry for entry in claude_plugins if entry['name'] == name)
        if claude_entry.get('source') != expected_path or claude_entry.get('category') != 'Developer Tools':
            fail(f'Claude catalog entry drift: {name}')
        manifests = (read_json(bundle / '.codex-plugin/plugin.json'), read_json(bundle / '.claude-plugin/plugin.json'))
        for manifest in manifests:
            if manifest.get('name') != name or manifest.get('version') != record.get('version') or manifest.get('repository') != record['source_repository']:
                fail(f'manifest identity drift: {name}')
        if manifests[0].get('skills') != './skills/' or not (bundle / 'skills').is_dir():
            fail(f'Codex skill layout drift: {name}')
        source = sources.get(name)
        if source is not None:
            if git_revision(source) != record['source_commit'] or tree_digest(source / record['source_path']) != tree_digest(bundle):
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
