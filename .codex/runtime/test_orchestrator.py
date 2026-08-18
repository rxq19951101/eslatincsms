import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ORCH = ROOT / ".codex/runtime/orchestrator.py"


def run(runtime_dir, *args, stdin=None):
    env = os.environ.copy()
    env["CODEX_RUNTIME_DIR"] = str(runtime_dir)
    return subprocess.run([sys.executable, str(ORCH), *args], input=stdin, text=True, capture_output=True, env=env, check=False)


class OrchestratorTests(unittest.TestCase):
    def register(self, runtime):
        result = run(runtime, "register-agent", "--role", "backend-agent-test", "--runtime-agent-id", "runtime-1", "--change-id", "TEST-ORCH", "--scope", "test")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_wait_timeout_is_not_terminal_and_stop_blocks(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime = Path(temp)
            self.register(runtime)
            timeout = json.loads(run(runtime, "poll", "--role", "backend-agent-test", "--timeout").stdout)
            self.assertEqual(timeout["event"], "POLL_INTERVAL_EXPIRED")
            self.assertFalse(timeout["may_interpret_as_terminal"])
            registry = json.loads((runtime / "agents.json").read_text())
            self.assertEqual(registry["agents"][0]["status"], "pending_init")
            self.assertEqual(json.loads(run(runtime, "stop-hook").stdout)["decision"], "block")

    def test_two_stale_checkpoints_trigger_self_correction(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime = Path(temp)
            self.register(runtime)
            for _ in range(2):
                result = run(runtime, "checkpoint", "--role", "backend-agent-test", "--meaningful-progress", "false")
                self.assertEqual(result.returncode, 0, result.stdout)
            state = json.loads((runtime / "orchestrator-state.json").read_text())
            self.assertEqual(state["convergence_status"], "self-correction-required")
            self.assertEqual(state["self_correction_rounds"], 1)

    def test_terminal_result_converges_and_hooks_allow(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime = Path(temp)
            self.register(runtime)
            state_path = runtime / "orchestrator-state.json"
            state = json.loads(state_path.read_text())
            state.update({
                "mandatory_agents": ["backend-agent-test"],
                "mandatory_convergence_checks": ["qa", "scope"],
                "completed_convergence_checks": ["qa", "scope"],
                "current_stage_gate_status": "passed",
                "must_continue_workflow": False,
            })
            state_path.write_text(json.dumps(state))
            result = run(runtime, "record-terminal", "--role", "backend-agent-test", "--status", "completed", "--scope-complete", "true", "--self-check-complete", "true", "--convergence-recorded", "true", "--verification-complete", "true")
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertTrue(json.loads(run(runtime, "convergence-check").stdout)["allow_main_thread_stop"])
            self.assertEqual(json.loads(run(runtime, "stop-hook").stdout)["decision"], "allow")
            event = json.dumps({"runtime_agent_id": "runtime-1"})
            self.assertEqual(json.loads(run(runtime, "subagent-stop-hook", stdin=event).stdout)["decision"], "allow")

    def test_new_agent_resets_previous_stop_allow(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime = Path(temp)
            self.register(runtime)
            state_path = runtime / "orchestrator-state.json"
            state = json.loads(state_path.read_text())
            state.update({"current_stage_gate_status": "passed", "must_continue_workflow": False, "mandatory_convergence_checks": [], "completed_convergence_checks": []})
            state_path.write_text(json.dumps(state))
            run(runtime, "record-terminal", "--role", "backend-agent-test", "--status", "completed", "--scope-complete", "true", "--self-check-complete", "true", "--convergence-recorded", "true", "--verification-complete", "true")
            run(runtime, "convergence-check")
            self.assertEqual(json.loads(run(runtime, "stop-hook").stdout)["decision"], "allow")
            register = run(runtime, "register-agent", "--role", "frontend-agent-test", "--runtime-agent-id", "runtime-2", "--change-id", "TEST-ORCH", "--scope", "test")
            self.assertEqual(register.returncode, 0, register.stdout)
            self.assertEqual(json.loads(run(runtime, "stop-hook").stdout)["decision"], "block")

    def test_stop_hook_revalidates_cached_allow_flag(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime = Path(temp)
            self.register(runtime)
            state_path = runtime / "orchestrator-state.json"
            state = json.loads(state_path.read_text())
            state.update({
                "allow_main_thread_stop": True,
                "convergence_status": "converged",
                "current_stage_gate_status": "pending",
                "must_continue_workflow": False,
            })
            state_path.write_text(json.dumps(state))
            result = json.loads(run(runtime, "stop-hook").stdout)
            self.assertEqual(result["decision"], "block")
            self.assertFalse(result["conditions"]["current_stage_gate_formal"])
            persisted = json.loads(state_path.read_text())
            self.assertFalse(persisted["allow_main_thread_stop"])

    def test_register_persists_runtime_identity_in_state_projection(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime = Path(temp)
            self.register(runtime)
            state = json.loads((runtime / "orchestrator-state.json").read_text())
            self.assertEqual(state["active_agents"][0]["runtime_agent_id"], "runtime-1")
            self.assertEqual(state["pending_agents"][0]["status"], "pending_init")
            self.assertFalse(state["allow_main_thread_stop"])

    def test_resume_reactivates_terminal_agent_without_duplicate(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime = Path(temp)
            self.register(runtime)
            run(runtime, "record-terminal", "--role", "backend-agent-test", "--status", "blocked", "--blocked-reason", "test blocker", "--scope-complete", "true", "--self-check-complete", "true", "--convergence-recorded", "true", "--verification-complete", "true")
            result = json.loads(run(runtime, "resume", "--role", "backend-agent-test", "--change-id", "TEST-ORCH").stdout)
            self.assertEqual(result["event"], "AGENT_REACTIVATED")
            self.assertEqual(result["runtime_agent_id"], "runtime-1")
            registry = json.loads((runtime / "agents.json").read_text())
            self.assertEqual(registry["agents"][0]["status"], "pending_init")
            state = json.loads((runtime / "orchestrator-state.json").read_text())
            self.assertIn("runtime-1", state["pending_results"])
            self.assertFalse(state["allow_main_thread_stop"])


if __name__ == "__main__":
    unittest.main()
