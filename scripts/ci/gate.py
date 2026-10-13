"""Always-running required result gates: explicit N/A, never skipped-needed PASS."""
import argparse
import json
import os
from pathlib import Path

from impact import read_plan


def expected_jobs(gate: str, selection: dict) -> list[str]:
    if gate == "frontend":
        # A product change can require the Windows shell even when the full
        # installer matrix is not selected. Its build must block this gate.
        return [job for job, selected in (
            ("frontend-work", selection["jobs"]["frontend"]),
            ("tauri-windows", selection["jobs"]["tauri-windows"]),
        ) if selected]
    if not selection["jobs"][gate]:
        return []
    if gate == "backend":
        return ["backend-preflight", "backend-tests"]
    if gate == "windows-installer":
        jobs = ["release-candidate", "installed-runtime-smoke"]
        if selection["windows"] == "full":
            jobs.extend(["windows-installer-supported-upgrade", "windows-installer-failure-recovery"])
        elif selection["windows"] == "installer-smoke":
            jobs.append("windows-installer-representative-upgrade")
        return jobs
    return [gate + "-work"]


def verify(gate: str, plan: dict, needs: dict) -> dict:
    if needs.get("impact", {}).get("result") != "success":
        raise ValueError("ci_impact_job_not_successful")
    selected = expected_jobs(gate, plan["effective"])
    if any(needs.get(job, {}).get("result") != "success" for job in selected):
        raise ValueError("ci_required_work_missing_failed_or_cancelled")
    # Unexpected execution is permitted (wider validation); unexpected failure
    # or cancellation is not. Unneeded work must really be skipped or succeed.
    if any(value.get("result") not in {"success", "skipped"} for job, value in needs.items() if job != "impact"):
        raise ValueError("ci_dependency_failed_or_cancelled")
    return {"gate": gate, "status": "passed" if selected else "not_applicable",
            "required_jobs": selected, "profile": plan["effective"]["backend" if gate == "backend" else "windows"] if gate in {"backend", "windows-installer"} else gate,
            "selection_sha256": plan["selection_sha256"], "reasons": plan["effective"]["reasons"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gate", required=True)
    args = parser.parse_args()
    path = Path(".ci/impact.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(os.environ["CI_IMPACT_PLAN"], encoding="utf-8")
    result = verify(args.gate, read_plan(path), json.loads(os.environ["CI_NEEDS"]))
    rendered = json.dumps(result, indent=2)
    print(rendered)
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(summary, "a", encoding="utf-8") as stream:
            stream.write(f"## {args.gate}: {result['status']}\n\n```json\n{rendered}\n```\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
