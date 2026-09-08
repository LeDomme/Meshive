import datetime as dt
import importlib.util
import pathlib
import sys
import unittest
from unittest import mock


MODULE_PATH = pathlib.Path(__file__).parents[1] / "cleanup-ghcr.py"
SPEC = importlib.util.spec_from_file_location("cleanup_ghcr", MODULE_PATH)
cleanup = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = cleanup
SPEC.loader.exec_module(cleanup)


NOW = dt.datetime(2026, 9, 9, tzinfo=dt.timezone.utc)
CUTOFF = NOW - dt.timedelta(days=7)


def version(identifier, tags, age_days, value=None):
    return cleanup.Version(identifier, value or f"sha256:{identifier:064x}", tuple(tags), NOW - dt.timedelta(days=age_days))


class CandidateTests(unittest.TestCase):
    def selected(self, versions, protected=()):
        dev, orphaned, _ = cleanup.candidates(versions, set(protected), CUTOFF)
        return {item.id for item in [*dev, *orphaned]}

    def test_release_tag_set_is_protected(self):
        self.assertEqual(self.selected([version(1, ["1.6.4", "sha-abc", "1.6", "1", "latest"], 8)]), set())

    def test_edge_tag_is_protected(self):
        self.assertEqual(self.selected([version(1, ["edge"], 8)]), set())

    def test_unknown_tag_is_protected(self):
        self.assertEqual(self.selected([version(1, ["testing"], 8)]), set())

    def test_old_dev_tags_are_candidates(self):
        self.assertEqual(self.selected([version(1, ["sha-abc", "pr-150"], 8)]), {1})

    def test_young_dev_tags_are_retained(self):
        self.assertEqual(self.selected([version(1, ["sha-abc"], 6)]), set())

    def test_release_referenced_untagged_digest_is_protected(self):
        referenced = version(1, [], 8)
        self.assertEqual(self.selected([referenced], {referenced.digest}), set())

    def test_edge_referenced_untagged_digest_is_protected(self):
        referenced = version(1, [], 8)
        self.assertEqual(self.selected([referenced], {referenced.digest}), set())

    def test_old_orphan_is_a_candidate(self):
        self.assertEqual(self.selected([version(1, [], 8)]), {1})

    def test_young_orphan_is_retained(self):
        self.assertEqual(self.selected([version(1, [], 6)]), set())

    def test_manifest_discovery_failure_is_fail_closed(self):
        protected = version(1, ["edge"], 8)
        with mock.patch.object(cleanup, "inspect_manifest", side_effect=cleanup.DiscoveryError("broken manifest")):
            with self.assertRaises(cleanup.DiscoveryError):
                cleanup.protected_graph([protected], "ledomme/meshive")

    def test_final_recheck_rejects_new_release_tag(self):
        self.assertFalse(cleanup.safe_to_delete(version(1, ["1.6.4"], 8), set(), CUTOFF))

    def test_dry_run_does_not_call_delete(self):
        current = version(1, ["sha-abc"], 8)
        api = mock.Mock(get_version=mock.Mock(return_value=current))
        self.assertEqual(cleanup.delete_candidates(api, [current], set(), CUTOFF, True), 0)
        api.delete.assert_not_called()


class WorkflowSafetyTests(unittest.TestCase):
    def test_schedule_without_enablement_is_a_dry_run(self):
        self.assertTrue(cleanup.resolve_dry_run("schedule", False, None))
        self.assertTrue(cleanup.resolve_dry_run("schedule", False, "false"))

    def test_schedule_with_enablement_can_delete(self):
        self.assertFalse(cleanup.resolve_dry_run("schedule", True, "true"))

    def test_manual_dispatch_respects_dry_run_input(self):
        self.assertTrue(cleanup.resolve_dry_run("workflow_dispatch", True, None))
        self.assertFalse(cleanup.resolve_dry_run("workflow_dispatch", False, None))

    def test_protected_index_children_are_discovered_recursively(self):
        root = version(1, ["1.6.4"], 8)
        child = "sha256:" + "a" * 64
        nested = "sha256:" + "b" * 64
        manifests = {
            "1.6.4": {"manifests": [{"digest": child}]},
            root.digest: {"manifests": [{"digest": nested}]},
            child: {"manifests": []},
            nested: {"manifests": []},
        }
        with mock.patch.object(cleanup, "inspect_manifest", side_effect=lambda _, ref: manifests[ref]):
            _, protected = cleanup.protected_graph([root], "ledomme/meshive")
        self.assertTrue({root.digest, child, nested}.issubset(protected))

    def test_subject_digest_is_discovered(self):
        root = version(1, ["edge"], 8)
        subject = "sha256:" + "c" * 64
        manifests = {
            "edge": {"manifests": [], "subject": {"digest": subject}},
            root.digest: {"manifests": []},
            subject: {"manifests": []},
        }
        with mock.patch.object(cleanup, "inspect_manifest", side_effect=lambda _, ref: manifests[ref]):
            _, protected = cleanup.protected_graph([root], "ledomme/meshive")
        self.assertIn(subject, protected)

    def test_current_graph_does_not_require_referrers_endpoint(self):
        self.assertFalse(hasattr(cleanup, "referrers"))


if __name__ == "__main__":
    unittest.main()
