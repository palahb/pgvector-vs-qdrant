from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MANAGE = REPO / "orchestration/manage.py"


class OrchestrationManageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.registry = self.root / "registry"
        self.commit = subprocess.run(
            ["git", "-C", str(REPO), "rev-parse", "HEAD"], check=True, capture_output=True, text=True
        ).stdout.strip()
        self.config = self.root / "config.json"
        self.config.write_text(json.dumps({
            "schema_version": 1,
            "experiment_id": "test-e1",
            "code_commit": self.commit,
            "registry_root": str(self.registry),
            "requires_smoke": True,
            "max_retries": 2,
            "resources": {"partition": "debug", "cpus": 2, "memory": "2G", "time": "00:10:00", "array_concurrency": 2, "exclude": []},
            "storage": {"min_free_gb": 0, "min_inode_free_percent": 0},
            "base_args": {"synthetic": True, "n": 10},
            "stages": {
                "pilot": {"matrix": {"seed": [1, 2]}, "engines": ["pg", "qdrant"]},
                "full": {"matrix": {"seed": [1, 2, 3]}, "engines": ["pg", "qdrant"]},
            },
        }))

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_manage(self, *args: str, ok: bool = True) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [sys.executable, str(MANAGE), *args], cwd=REPO, text=True, capture_output=True,
            env=os.environ | {"BENCH_ROOT": str(self.root / "bench")},
        )
        if ok and result.returncode:
            self.fail(result.stdout + result.stderr)
        return result

    def record_smoke(self) -> None:
        manifest = self.root / "smoke.json"
        manifest.write_text(json.dumps({
            "code_commit": self.commit,
            "slurm": {"state": "COMPLETED", "job_id": "123", "node": "hamsi1"},
            "audit": {"verdict": "validated"},
        }))
        self.run_manage("record-smoke", str(manifest), "--registry-root", str(self.registry))

    def test_render_and_pilot_gate(self) -> None:
        deployment_dir = self.root / "pilot"
        self.run_manage("render", str(self.config), "pilot", "--output", str(deployment_dir))
        deployment = json.loads((deployment_dir / "deployment.json").read_text())
        self.assertEqual(deployment["task_count"], 2)
        script = (deployment_dir / "submit.sbatch").read_text()
        self.assertIn("#SBATCH --array=0-1%2", script)
        self.assertIn("git rev-parse --show-toplevel", script)
        rejected = self.run_manage("submit", str(deployment_dir / "deployment.json"), "--dry-run", ok=False)
        self.assertNotEqual(rejected.returncode, 0)
        self.record_smoke()
        accepted = self.run_manage("submit", str(deployment_dir / "deployment.json"), "--dry-run")
        self.assertIn("gate_evidence", accepted.stdout)

    def test_full_requires_complete_pilot_same_commit(self) -> None:
        self.record_smoke()
        deployment_dir = self.root / "full"
        self.run_manage("render", str(self.config), "full", "--output", str(deployment_dir))
        rejected = self.run_manage("submit", str(deployment_dir / "deployment.json"), "--dry-run", ok=False)
        self.assertIn("completed pilot", rejected.stderr)
        pilot = self.registry / "submissions/pilot-1/summary.json"
        pilot.parent.mkdir(parents=True)
        pilot.write_text(json.dumps({
            "experiment_id": "test-e1", "stage": "pilot", "code_commit": self.commit, "verdict": "complete"
        }))
        accepted = self.run_manage("submit", str(deployment_dir / "deployment.json"), "--dry-run")
        self.assertIn(str(pilot), accepted.stdout)

    def test_status_detects_invalid_completed_record(self) -> None:
        deployment_dir = self.root / "pilot-status"
        self.run_manage("render", str(self.config), "pilot", "--output", str(deployment_dir), "--submission-id", "status-test")
        task = self.registry / "submissions/status-test/tasks/task_0000.json"
        task.parent.mkdir(parents=True)
        task.write_text(json.dumps({"task_index": 0, "status": "completed", "attempts": [], "validator": {"verdict": "invalid"}}))
        result = self.run_manage("status", str(deployment_dir / "deployment.json"), ok=False)
        summary = json.loads(result.stdout)
        self.assertFalse(summary["consistency"]["ok"])


if __name__ == "__main__":
    unittest.main()
