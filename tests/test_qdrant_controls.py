from __future__ import annotations

import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "bench"))

from engines import Qdrant, qdrant_segment_summary  # noqa: E402


def arguments(**overrides):
    values = {
        "qdrant_search_threads": 1,
        "qdrant_indexing_threshold_kb": 1,
        "qdrant_segments": 2,
        "qdrant_on_disk": False,
        "qdrant_require_indexed": True,
        "qdrant_control_grace_s": 0.01,
    }
    values.update(overrides)
    return Namespace(**values)


class FakeClient:
    def __init__(self):
        self.created = None

    def collection_exists(self, _name):
        return False

    def create_collection(self, _name, **kwargs):
        self.created = kwargs

    def upload_collection(self, *_args, **_kwargs):
        return None


class QdrantControlTests(unittest.TestCase):
    def test_segment_summary_distinguishes_empty_appendable_segment(self) -> None:
        telemetry = {"collections": [{"shards": [{"local": {"segments": [
            {"info": {"segment_type": "plain", "num_vectors": 0, "num_indexed_vectors": 0, "is_appendable": True}},
            {"info": {"segment_type": "indexed", "num_vectors": 100, "num_indexed_vectors": 100, "is_appendable": False}},
        ]}}]}]}
        summary = qdrant_segment_summary(telemetry)
        self.assertEqual(summary["public_segment_count"], 2)
        self.assertEqual(summary["nonempty_segment_count"], 1)
        self.assertEqual(summary["indexed_nonempty_segment_count"], 1)
        self.assertEqual(summary["empty_appendable_segment_count"], 1)

    def test_search_threads_are_injected_as_documented_environment_key(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            server = Qdrant(directory, [0], arguments(qdrant_search_threads=1))
            self.assertEqual(
                server._env()["QDRANT__STORAGE__PERFORMANCE__MAX_SEARCH_THREADS"], "1"
            )

    def test_build_records_and_enforces_segment_target(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            server = Qdrant(directory, [0], arguments())
            client = FakeClient()
            server.client = lambda _proto="grpc": client
            server.collection_state = lambda _client=None: {
                "status": "green", "points": 4, "indexed": 4, "segments": 2
            }
            server.storage = directory
            with patch("time.sleep", return_value=None):
                result = server.build(np.ones((4, 3), dtype=np.float32), 16, 64)
            optimizer = client.created["optimizers_config"].model_dump(exclude_none=True)
            self.assertEqual(optimizer["default_segment_number"], 2)
            self.assertEqual(optimizer["indexing_threshold"], 1)
            self.assertTrue(result["segment_target_met"])
            self.assertTrue(result["fully_indexed"])
            self.assertEqual(result["requested_search_threads"], 1)

    def test_optimizer_target_may_have_an_extra_public_segment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            server = Qdrant(directory, [0], arguments(qdrant_segments=1))
            client = FakeClient()
            server.client = lambda _proto="grpc": client
            server.collection_state = lambda _client=None: {
                "status": "green", "points": 4, "indexed": 4, "segments": 2
            }
            server.storage = directory
            with patch("time.sleep", return_value=None):
                result = server.build(np.ones((4, 3), dtype=np.float32), 16, 64)
            self.assertFalse(result["segment_target_met"])
            self.assertEqual(result["requested_segments"], 1)
            self.assertEqual(result["actual_segments"], 2)


if __name__ == "__main__":
    unittest.main()
