from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('sync_upstreams', ROOT / 'scripts' / 'sync_upstreams.py')
assert SPEC is not None and SPEC.loader is not None
sync = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = sync
SPEC.loader.exec_module(sync)


class SyncConfigurationTest(unittest.TestCase):
    def test_upstreams_match_recorded_provenance_and_bundles(self) -> None:
        upstreams = sync.configured_upstreams()
        _, records = sync.provenance_records()
        self.assertEqual([item.name for item in upstreams], ['engineering-workflow', 'tgrep-search'])
        for upstream in upstreams:
            record = records[upstream.name]
            sync.validate_record_shape(upstream, record)
            manifest = json.loads((ROOT / 'plugins' / upstream.name / '.codex-plugin' / 'plugin.json').read_text())
            self.assertEqual(manifest['version'], record['version'])

    def test_version_parser_rejects_non_semver_values(self) -> None:
        self.assertEqual(sync.version_key('1.2.3'), (1, 2, 3))
        for invalid in ('v1.2.3', '1.2', '01.2.3', '1.2.3-rc.1', '1.2.3+build.4'):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                sync.version_key(invalid)

    def test_source_version_must_strictly_increase(self) -> None:
        self.assertTrue(sync.is_strictly_newer('0.9.2', '0.9.1'))
        self.assertTrue(sync.is_strictly_newer('1.0.0', '0.9.99'))
        self.assertFalse(sync.is_strictly_newer('0.9.1', '0.9.1'))
        self.assertFalse(sync.is_strictly_newer('0.9.0', '0.9.1'))

    def test_latest_stable_tag_selects_only_annotated_stable_semver(self) -> None:
        remote_refs = '\n'.join((
            'a' * 40 + '\trefs/tags/v0.9.1',
            'b' * 40 + '\trefs/tags/v0.9.1^{}',
            'c' * 40 + '\trefs/tags/v0.10.0',
            'd' * 40 + '\trefs/tags/v0.10.0^{}',
            'e' * 40 + '\trefs/tags/v1.0.0-rc.1^{}',
            'f' * 40 + '\trefs/tags/v2.0.0',
            'g' * 40 + '\trefs/tags/not-a-version^{}',
        ))
        with mock.patch.object(sync, 'run', return_value=remote_refs):
            self.assertEqual(sync.latest_stable_tag('xeonvs/example'), 'v0.10.0')

    def test_latest_stable_tag_rejects_lightweight_or_prerelease_tags(self) -> None:
        remote_refs = '\n'.join((
            'a' * 40 + '\trefs/tags/v1.0.0',
            'b' * 40 + '\trefs/tags/v1.1.0-rc.1^{}',
        ))
        with mock.patch.object(sync, 'run', return_value=remote_refs):
            with self.assertRaisesRegex(ValueError, 'no eligible stable annotated'):
                sync.latest_stable_tag('xeonvs/example')

    def test_unknown_plugin_selection_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, 'unknown plugin selection'):
            sync.selected_upstreams(sync.configured_upstreams(), ['not-configured'])

    def test_tag_source_configuration_rejects_floating_ref(self) -> None:
        original_upstreams = sync.UPSTREAMS
        try:
            with tempfile.TemporaryDirectory() as temporary:
                sync.UPSTREAMS = Path(temporary) / 'UPSTREAMS.json'
                sync.UPSTREAMS.write_text(json.dumps({
                    'schema_version': 1,
                    'plugins': [{
                        'name': 'example',
                        'repository': 'xeonvs/example',
                        'bundle_path': 'plugins/example',
                        'source_policy': 'latest-tag',
                        'ref': 'main',
                    }],
                }))
                with self.assertRaisesRegex(ValueError, 'invalid latest-tag configuration'):
                    sync.configured_upstreams()
        finally:
            sync.UPSTREAMS = original_upstreams

    def test_mismatched_policy_and_provenance_are_rejected(self) -> None:
        upstream = sync.configured_upstreams()[0]
        _, records = sync.provenance_records()
        record = dict(records[upstream.name])
        record['source_policy'] = 'not-a-policy'
        with self.assertRaisesRegex(ValueError, 'source configuration drift'):
            sync.validate_record_shape(upstream, record)

    def test_recorded_provenance_must_match_configured_plugins(self) -> None:
        upstreams = sync.configured_upstreams()
        _, records = sync.provenance_records()
        records.pop('tgrep-search')
        with self.assertRaisesRegex(ValueError, 'cover exactly'):
            sync.require_matching_records(upstreams, records)

    def test_render_versions_rejects_missing_or_duplicate_markers(self) -> None:
        original_readme = sync.README
        try:
            with tempfile.TemporaryDirectory() as temporary:
                sync.README = Path(temporary) / 'README.md'
                sync.README.write_text('no generated table\n')
                with self.assertRaisesRegex(ValueError, 'exactly one'):
                    sync.render_versions([], {})
                sync.README.write_text(
                    f'{sync.VERSION_BEGIN}\n{sync.VERSION_BEGIN}\n{sync.VERSION_END}\n{sync.VERSION_END}\n'
                )
                with self.assertRaisesRegex(ValueError, 'exactly one'):
                    sync.render_versions([], {})
        finally:
            sync.README = original_readme


if __name__ == '__main__':
    unittest.main()
