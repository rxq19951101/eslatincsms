from __future__ import annotations

import asyncio
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping

from actors import AdminActor, AppUserActor, ChargerActor, FakePaymentActor
from actors.base import ActorResult, BaseActor
from assertions import AssertionFailure, evaluate_expectations, extract_path
from reports import write_all_reports
from scenario.schema import ActorSpec, ScenarioDocument, StepSpec
from scenario.variables import build_environment, resolve_value

from .result import RunResult, StepResult


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


ACTOR_CLASSES = {
    "charger": ChargerActor,
    "admin": AdminActor,
    "app": AppUserActor,
    "fake_payment": FakePaymentActor,
    "payment": FakePaymentActor,
}


class ScenarioRunner:
    def __init__(
        self,
        scenario: ScenarioDocument,
        *,
        report_dir: Path,
        process_environment: Mapping[str, str] | None = None,
        initial_variables: Mapping[str, Any] | None = None,
    ):
        self.scenario = scenario
        self.report_dir = report_dir
        self.run_id = str(uuid.uuid4())
        self.initialization_error: Exception | None = None
        try:
            builtins: Dict[str, Any] = {"run_id": self.run_id, "scenario_id": scenario.id}
            if initial_variables:
                builtins.update(initial_variables)
            self.variables = build_environment(
                scenario.environment,
                process_environment if process_environment is not None else os.environ,
                builtins,
            )
        except Exception as exc:
            self.variables = {"run_id": self.run_id, "scenario_id": scenario.id}
            self.initialization_error = exc
        self.actors: Dict[str, BaseActor] = {}
        self.step_outcomes: Dict[str, str] = {}

    def _create_actor(self, spec: ActorSpec) -> BaseActor:
        config = resolve_value(spec.config, self.variables)
        actor_class = ACTOR_CLASSES[spec.type]
        return actor_class(spec.name, config, self.run_id)

    async def _execute_system(self, step: StepSpec, params: Dict[str, Any]) -> ActorResult:
        if step.action == "sleep":
            seconds = float(params.get("seconds", params.get("duration", 0)))
            await asyncio.sleep(seconds)
            return ActorResult(status="ok", body={"slept": seconds})
        if step.action == "await":
            seconds = float(params.get("seconds", params.get("poll_interval", 1)))
            await asyncio.sleep(seconds)
            return ActorResult(status="ok", body=params)
        if step.action == "assert":
            actual = params.get("actual")
            if "equals" in params and actual != params["equals"]:
                raise AssertionFailure(f"system assert expected {params['equals']!r}, got {actual!r}")
            return ActorResult(status="ok", body={"actual": actual})
        if step.action == "provision":
            return ActorResult(
                status="ok",
                body={"mode": "public-api-only", "input": params},
            )
        raise ValueError(f"Unsupported system action: {step.action}")

    async def _execute_once(self, step: StepSpec) -> ActorResult:
        params = resolve_value(step.with_, self.variables)
        if step.actor == "system":
            result = await self._execute_system(step, params)
        else:
            actor = self.actors[step.actor]
            result = await actor.execute(step.action, params, step.id)
        resolved_expect = resolve_value(step.expect, self.variables)
        evaluate_expectations(result.as_dict(), resolved_expect)
        return result

    def _save_values(self, step: StepSpec, result: ActorResult) -> None:
        result_data = result.as_dict()
        for name, path in step.save.items():
            self.variables[name] = extract_path(result_data, path)

    async def _run_step(self, step: StepSpec) -> StepResult:
        start_wall = now_iso()
        start_time = time.monotonic()
        attempts = 0
        last_error: Exception | None = None
        last_result: ActorResult | None = None
        for attempts in range(1, step.retry + 2):
            try:
                last_result = await asyncio.wait_for(self._execute_once(step), timeout=step.timeout)
                self._save_values(step, last_result)
                end = now_iso()
                return StepResult(
                    run_id=self.run_id,
                    scenario_id=self.scenario.id,
                    step_id=step.id,
                    actor=step.actor,
                    action=step.action,
                    start=start_wall,
                    end=end,
                    duration_seconds=round(time.monotonic() - start_time, 6),
                    outcome="PASS",
                    trace_id=last_result.trace_id,
                    attempts=attempts,
                    result=last_result.as_dict(),
                )
            except Exception as exc:
                last_error = exc
                if attempts <= step.retry:
                    await asyncio.sleep(min(0.25 * attempts, 1.0))
        return StepResult(
            run_id=self.run_id,
            scenario_id=self.scenario.id,
            step_id=step.id,
            actor=step.actor,
            action=step.action,
            start=start_wall,
            end=now_iso(),
            duration_seconds=round(time.monotonic() - start_time, 6),
            outcome="FAIL",
            trace_id=last_result.trace_id if last_result else "",
            attempts=attempts,
            result=last_result.as_dict() if last_result else None,
            error=f"{type(last_error).__name__}: {last_error}",
        )

    async def run(self) -> RunResult:
        started = now_iso()
        step_results = []
        failed = False
        if self.initialization_error is not None:
            step_results.append(
                StepResult(
                    run_id=self.run_id,
                    scenario_id=self.scenario.id,
                    step_id="environment",
                    actor="system",
                    action="provision",
                    start=started,
                    end=now_iso(),
                    duration_seconds=0,
                    outcome="BLOCKED",
                    error=f"{type(self.initialization_error).__name__}: {self.initialization_error}",
                )
            )
            run_result = RunResult(
                run_id=self.run_id,
                scenario_id=self.scenario.id,
                start=started,
                end=now_iso(),
                outcome="BLOCKED",
                steps=step_results,
            )
            run_result.reports = write_all_reports(run_result.as_dict(), self.report_dir)
            return run_result
        try:
            try:
                self.actors = {name: self._create_actor(spec) for name, spec in self.scenario.actors.items()}
            except Exception as exc:
                step_results.append(
                    StepResult(
                        run_id=self.run_id,
                        scenario_id=self.scenario.id,
                        step_id="actors",
                        actor="system",
                        action="provision",
                        start=started,
                        end=now_iso(),
                        duration_seconds=0,
                        outcome="BLOCKED",
                        error=f"{type(exc).__name__}: {exc}",
                    )
                )
                run_result = RunResult(
                    run_id=self.run_id,
                    scenario_id=self.scenario.id,
                    start=started,
                    end=now_iso(),
                    outcome="BLOCKED",
                    steps=step_results,
                )
                run_result.reports = write_all_reports(run_result.as_dict(), self.report_dir)
                return run_result
            for step in self.scenario.steps:
                unmet = [dep for dep in step.depends_on if self.step_outcomes.get(dep) != "PASS"]
                if failed or unmet:
                    result = StepResult(
                        run_id=self.run_id,
                        scenario_id=self.scenario.id,
                        step_id=step.id,
                        actor=step.actor,
                        action=step.action,
                        start=now_iso(),
                        end=now_iso(),
                        duration_seconds=0,
                        outcome="NOT_RUN",
                        error="previous step failed" if failed else f"unmet dependencies: {', '.join(unmet)}",
                    )
                else:
                    result = await self._run_step(step)
                step_results.append(result)
                self.step_outcomes[step.id] = result.outcome
                if result.outcome == "FAIL":
                    failed = True
        finally:
            await asyncio.gather(*(actor.close() for actor in self.actors.values()), return_exceptions=True)

        run_result = RunResult(
            run_id=self.run_id,
            scenario_id=self.scenario.id,
            start=started,
            end=now_iso(),
            outcome="FAIL" if failed else "PASS",
            steps=step_results,
        )
        report_paths = write_all_reports(run_result.as_dict(), self.report_dir)
        run_result.reports = report_paths
        return run_result
