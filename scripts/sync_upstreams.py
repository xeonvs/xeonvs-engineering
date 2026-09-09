#!/usr/bin/env python3
"""Synchronize tagged public upstream bundles into this marketplace.

Default mode prepares a reviewable catalog update. --verify-recorded proves that
the already recorded immutable source commits still produce the vendored bytes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UPSTREAMS = ROOT / 'UPSTREAMS.json'
PROVENANCE = ROOT / 'PROVENANCE.json'
README = ROOT / 'README.md'
NAME = re.compile(r'^[a-z0-9-]+$')
REPOSITORY = re.compile(r'^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$')
SHA = re.compile(r'^[0-9a-f]{40}$')
# Marketplace imports are stable public packages.  Accepting a prerelease or a
# build-metadata-only version here would make the strict-increase policy
# ambiguous, so both source policies intentionally use the stable SemVer form.
SEMVER = re.compile(r'^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$')
VERSION_BEGIN = '<!-- BEGIN GENERATED PLUGIN VERSIONS -->'
VERSION_END = '<!-- END GENERATED PLUGIN VERSIONS -->'


def fail(message: str) -> None:
    raise ValueError(message)


def run(*args: str, cwd: Path | None = None) -> str:
    result = subprocess.run(args, cwd=cwd, text=True, capture_output=True, check=False)
    if result.returncode:
        fail(f"command failed ({' '.join(args[:4])}): {result.stderr.strip()}")
    return result.stdout


def load(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f'cannot read {path.name}: {exc}')
    if not isinstance(value, dict):
        fail(f'{path.name} must be an object')
    return value


def version_key(value: str) -> tuple[int, int, int]:
    match = SEMVER.fullmatch(value)
    if not match:
        fail(f'unsupported semantic version: {value!r}')
    return tuple(int(part) for part in match.groups()[:3])


def is_strictly_newer(source: str, recorded: str) -> bool:
    """Return whether a stable source package may replace a recorded package."""
    return version_key(source) > version_key(recorded)


def tree_digest(root: Path) -> str:
    if not root.is_dir():
        fail(f'missing bundle: {root}')
    digest = hashlib.sha256()
    for path in sorted(root.rglob('*')):
        relative = path.relative_to(root)
        if path.is_symlink():
            fail(f'symlink is not allowed: {relative}')
        if path.is_dir():
            continue
        if not path.is_file():
            fail(f'unsupported bundle entry: {relative}')
        name, data = relative.as_posix().encode(), path.read_bytes()
        digest.update(len(name).to_bytes(4, 'big'))
        digest.update(name)
        digest.update(len(data).to_bytes(8, 'big'))
        digest.update(data)
    return digest.hexdigest()


def latest_stable_tag(repository: str) -> str:
    """Resolve the greatest stable SemVer *annotated* tag without GitHub API state.

    An annotated tag supplies a durable public release boundary. Requiring its
    peeled ``^{}`` ref deliberately rejects lightweight tags and means the
    catalog does not depend on a separately maintained GitHub Release object.
    """
    candidates: list[tuple[tuple[int, int, int], str]] = []
    prefix = 'refs/tags/v'
    for line in run('git', 'ls-remote', '--tags', 'https://github.com/' + repository + '.git').splitlines():
        fields = line.split()
        if len(fields) != 2 or not fields[1].startswith(prefix) or not fields[1].endswith('^{}'):
            continue
        tag = fields[1][len('refs/tags/'):-3]
        if SEMVER.fullmatch(tag[1:]):
            candidates.append((version_key(tag[1:]), tag))
    if not candidates:
        fail(f'no eligible stable annotated semantic-version tag for {repository}')
    return max(candidates)[1]


def resolve_remote(repository: str, source_policy: str, configured_ref: str | None) -> tuple[str, str]:
    if source_policy == 'latest-tag' and configured_ref is None:
        source_ref = latest_stable_tag(repository)
        remote_ref = f'refs/tags/{source_ref}^{{}}'
    else:
        fail(f'unsupported source policy/ref for {repository}')
    lines = [line for line in run('git', 'ls-remote', 'https://github.com/' + repository + '.git', remote_ref).splitlines() if line]
    if len(lines) != 1:
        fail(f'cannot resolve a unique immutable commit for {repository}@{source_ref}')
    commit = lines[0].split()[0]
    if not SHA.fullmatch(commit):
        fail(f'invalid commit returned for {repository}@{source_ref}')
    return source_ref, commit


def checkout_bundle(repository: str, commit: str, bundle_path: str, root: Path) -> Path:
    checkout = root / repository.replace('/', '--')
    run('git', 'clone', '--quiet', '--no-checkout', 'https://github.com/' + repository + '.git', str(checkout))
    run('git', 'fetch', '--quiet', '--depth=1', 'origin', commit, cwd=checkout)
    run('git', 'checkout', '--quiet', '--detach', 'FETCH_HEAD', cwd=checkout)
    if run('git', 'rev-parse', 'HEAD', cwd=checkout).strip() != commit:
        fail(f'checkout commit drift for {repository}')
    bundle = checkout / bundle_path
    if not bundle.is_dir():
        fail(f'upstream bundle path is missing: {repository}:{bundle_path}')
    return bundle


def read_manifest(bundle: Path, name: str) -> dict:
    try:
        value = json.loads((bundle / '.codex-plugin/plugin.json').read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f'invalid Codex manifest for {name}: {exc}')
    if not isinstance(value, dict) or value.get('name') != name or not isinstance(value.get('version'), str):
        fail(f'upstream manifest identity drift: {name}')
    version_key(value['version'])
    return value


@dataclass(frozen=True)
class Upstream:
    name: str
    repository: str
    bundle_path: str
    source_policy: str
    ref: str | None


def configured_upstreams() -> list[Upstream]:
    data = load(UPSTREAMS)
    raw = data.get('plugins')
    if data.get('schema_version') != 1 or not isinstance(raw, list):
        fail('unsupported upstream configuration')
    values: list[Upstream] = []
    for item in raw:
        if not isinstance(item, dict):
            fail('upstream entry must be an object')
        name, repository, bundle_path = item.get('name'), item.get('repository'), item.get('bundle_path')
        policy, ref = item.get('source_policy'), item.get('ref')
        if not isinstance(name, str) or not NAME.fullmatch(name) or not isinstance(repository, str) or not REPOSITORY.fullmatch(repository):
            fail('invalid upstream identity')
        if not isinstance(bundle_path, str) or Path(bundle_path).is_absolute() or '..' in Path(bundle_path).parts:
            fail(f'invalid upstream bundle path: {name}')
        if policy == 'latest-tag':
            if set(item) != {'name', 'repository', 'bundle_path', 'source_policy'}:
                fail(f'invalid latest-tag configuration: {name}')
        else:
            fail(f'invalid upstream policy: {name}')
        values.append(Upstream(name, repository, bundle_path, policy, ref))
    if not values or len({item.name for item in values}) != len(values):
        fail('upstream names must be non-empty and unique')
    return values


def selected_upstreams(configured: list[Upstream], selected_names: list[str]) -> list[Upstream]:
    selected = set(selected_names) if selected_names else {item.name for item in configured}
    unknown = selected - {item.name for item in configured}
    if unknown:
        fail('unknown plugin selection: ' + ', '.join(sorted(unknown)))
    return [item for item in configured if item.name in selected]


def provenance_records() -> tuple[dict, dict[str, dict]]:
    provenance = load(PROVENANCE)
    raw = provenance.get('bundles')
    if provenance.get('schema_version') != 1 or not isinstance(raw, list) or not all(isinstance(item, dict) for item in raw):
        fail('invalid provenance bundles')
    records = {item.get('name'): item for item in raw}
    if len(records) != len(raw) or any(not isinstance(name, str) for name in records):
        fail('invalid provenance record names')
    return provenance, records


def require_matching_records(configured: list[Upstream], records: dict[str, dict]) -> None:
    configured_names = [item.name for item in configured]
    if set(records) != set(configured_names):
        fail('provenance records must cover exactly the configured upstreams')
    for upstream in configured:
        record = records[upstream.name]
        if not isinstance(record.get('version'), str):
            fail(f'invalid recorded version: {upstream.name}')
        version_key(record['version'])
        validate_record_shape(upstream, record)


def validate_record_shape(upstream: Upstream, record: dict) -> None:
    expected_repository = 'https://github.com/' + upstream.repository
    if record.get('source_repository') != expected_repository or record.get('source_policy') != upstream.source_policy:
        fail(f'provenance source configuration drift: {upstream.name}')
    if upstream.source_policy == 'latest-tag':
        ref = record.get('source_ref')
        if not isinstance(ref, str) or not ref.startswith('v') or not SEMVER.fullmatch(ref[1:]):
            fail(f'provenance tag drift: {upstream.name}')
    if record.get('source_path') != upstream.bundle_path or not SHA.fullmatch(record.get('source_commit', '')):
        fail(f'provenance immutable source drift: {upstream.name}')


def render_versions(configured: list[Upstream], records: dict[str, dict]) -> None:
    try:
        content = README.read_text(encoding='utf-8')
        if content.count(VERSION_BEGIN) != 1 or content.count(VERSION_END) != 1:
            fail('README must contain exactly one generated version-table marker pair')
        before, remainder = content.split(VERSION_BEGIN, 1)
        _, after = remainder.split(VERSION_END, 1)
    except (OSError, ValueError) as exc:
        fail(f'cannot render README version table: {exc}')
    rows = []
    for upstream in configured:
        record = records[upstream.name]
        manifest = read_manifest(ROOT / 'plugins' / upstream.name, upstream.name)
        description = manifest.get('description')
        if not isinstance(description, str) or '|' in description or '\n' in description:
            fail(f'unsupported manifest description for README: {upstream.name}')
        source = f'[`{upstream.repository}`](https://github.com/{upstream.repository})'
        rows.append(f'| [`{upstream.name}`](plugins/{upstream.name}/) | {record["version"]} | {description} | {source} |')
    header = '| Plugin | Version | Purpose | Canonical source |'
    divider = '| --- | --- | --- | --- |'
    generated = VERSION_BEGIN + '\n' + header + '\n' + divider + '\n' + '\n'.join(rows) + '\n' + VERSION_END
    README.write_text(before + generated + after, encoding='utf-8')


def verify_recorded(upstreams: list[Upstream], records: dict[str, dict]) -> None:
    with tempfile.TemporaryDirectory(prefix='xeonvs-engineering-verify-') as temporary:
        root = Path(temporary)
        for upstream in upstreams:
            record = records.get(upstream.name)
            if not isinstance(record, dict):
                fail(f'missing provenance record: {upstream.name}')
            validate_record_shape(upstream, record)
            if upstream.source_policy == 'latest-tag':
                tag = record['source_ref']
                lines = [line for line in run('git', 'ls-remote', 'https://github.com/' + upstream.repository + '.git', f'refs/tags/{tag}^{{}}').splitlines() if line]
                if len(lines) != 1 or lines[0].split()[0] != record['source_commit']:
                    fail(f'release tag no longer resolves to recorded commit: {upstream.name}')
            bundle = checkout_bundle(upstream.repository, record['source_commit'], upstream.bundle_path, root)
            source_manifest = read_manifest(bundle, upstream.name)
            catalog_bundle = ROOT / 'plugins' / upstream.name
            if source_manifest['version'] != record.get('version') or tree_digest(bundle) != record.get('bundle_sha256'):
                fail(f'recorded source metadata drift: {upstream.name}')
            if tree_digest(bundle) != tree_digest(catalog_bundle):
                fail(f'recorded source bundle bytes differ: {upstream.name}')
            print(f'{upstream.name}: verified {source_manifest["version"]} ({record["source_commit"]})')


def synchronize(configured: list[Upstream], selected: list[Upstream], records: dict[str, dict], check: bool) -> bool:
    changed = False
    with tempfile.TemporaryDirectory(prefix='xeonvs-engineering-sync-') as temporary:
        root = Path(temporary)
        for upstream in selected:
            source_ref, commit = resolve_remote(upstream.repository, upstream.source_policy, upstream.ref)
            bundle = checkout_bundle(upstream.repository, commit, upstream.bundle_path, root)
            source_manifest = read_manifest(bundle, upstream.name)
            digest = tree_digest(bundle)
            current = records.get(upstream.name)
            if isinstance(current, dict) and current.get('source_commit') == commit and current.get('bundle_sha256') == digest:
                print(f'{upstream.name}: already synchronized at {source_manifest["version"]} ({commit})')
                continue
            if isinstance(current, dict) and not is_strictly_newer(source_manifest['version'], current.get('version', '')):
                fail(f'{upstream.name}: source changed without a version increase')
            if check:
                fail(f'{upstream.name}: catalog is behind {source_manifest["version"]} ({commit})')
            target = ROOT / 'plugins' / upstream.name
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(bundle, target)
            records[upstream.name] = {
                'name': upstream.name,
                'version': source_manifest['version'],
                'source_repository': 'https://github.com/' + upstream.repository,
                'source_policy': upstream.source_policy,
                'source_ref': source_ref,
                'source_commit': commit,
                'source_path': upstream.bundle_path,
                'bundle_sha256': digest,
            }
            changed = True
            print(f'{upstream.name}: synchronized {source_manifest["version"]} from {source_ref} ({commit})')
    if changed:
        provenance = load(PROVENANCE)
        provenance['bundles'] = [records[item.name] for item in configured]
        PROVENANCE.write_text(json.dumps(provenance, indent=2) + '\n', encoding='utf-8')
        render_versions(configured, records)
    return changed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--plugin', action='append', default=[], metavar='NAME')
    parser.add_argument('--check', action='store_true', help='fail if selected current upstream is newer')
    parser.add_argument('--verify-recorded', action='store_true', help='verify catalog bytes against recorded commits')
    args = parser.parse_args()
    if args.check and args.verify_recorded:
        parser.error('--check and --verify-recorded are mutually exclusive')
    try:
        configured = configured_upstreams()
        selected = selected_upstreams(configured, args.plugin)
        _, records = provenance_records()
        require_matching_records(configured, records)
        if args.verify_recorded:
            verify_recorded(selected, records)
            return 0
        synchronize(configured, selected, records, args.check)
    except ValueError as exc:
        print(f'sync failed: {exc}')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
