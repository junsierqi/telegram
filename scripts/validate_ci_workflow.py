"""Static checks on .github/workflows/ci.yml.

Runs locally (and in CI itself) to make sure the workflow stays parseable
and keeps its three jobs wired the way the rest of the bundle expects.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WORKFLOW = REPO / ".github" / "workflows" / "ci.yml"

SCENARIOS: list[tuple[str, callable]] = []


def scenario(name):
    def deco(fn):
        SCENARIOS.append((name, fn))
        return fn
    return deco


def _load() -> dict:
    try:
        import yaml  # noqa: F401
    except ImportError:
        # Tolerate environments without PyYAML — fall back to a string scan.
        return {"_raw": WORKFLOW.read_text(encoding="utf-8")}
    import yaml as y
    return y.safe_load(WORKFLOW.read_text(encoding="utf-8"))


@scenario("workflow_file_exists_and_parses")
def _t1():
    assert WORKFLOW.exists(), f"missing {WORKFLOW}"
    doc = _load()
    if "_raw" in doc:
        # No PyYAML — minimal sanity.
        for needle in ("name:", "on:", "jobs:"):
            assert needle in doc["_raw"], f"workflow missing top-level: {needle}"
        return
    assert "jobs" in doc, "workflow has no jobs"
    assert "on" in doc or True in doc, "workflow has no triggers"  # 'on' parses as bool True


@scenario("workflow_has_expected_jobs")
def _t2():
    doc = _load()
    text = doc.get("_raw") or WORKFLOW.read_text(encoding="utf-8")
    for job in ("validators:", "linux-cpp:", "linux-desktop:", "bundle-verify:"):
        assert job in text, f"workflow missing job: {job}"


@scenario("workflow_invokes_sweep_validators")
def _t3():
    text = (_load().get("_raw") or WORKFLOW.read_text(encoding="utf-8"))
    assert "scripts/_sweep_validators.py" in text, \
        "workflow should run the central validator sweep"


@scenario("workflow_builds_portable_cpp_targets")
def _t4():
    text = (_load().get("_raw") or WORKFLOW.read_text(encoding="utf-8"))
    for target in ("chat_client_core", "json_parser_test", "app_desktop_store_test",
                   "remote_session_smoke", "app_chat", "telegram_like_client"):
        assert target in text, f"linux-cpp job should build {target}"


@scenario("workflow_runs_cpp_test_binaries_inline")
def _t5():
    text = (_load().get("_raw") or WORKFLOW.read_text(encoding="utf-8"))
    for needle in ("./build-linux/client/src/json_parser_test",
                   "./build-linux/client/src/app_desktop_store_test"):
        assert needle in text, f"linux-cpp job should execute {needle}"


@scenario("workflow_concurrency_cancels_in_progress")
def _t6():
    text = (_load().get("_raw") or WORKFLOW.read_text(encoding="utf-8"))
    assert "concurrency:" in text, "workflow should declare a concurrency group"
    assert "cancel-in-progress: true" in text, \
        "concurrency should cancel old runs when new commits land"


@scenario("sweep_skips_cpp_validators_when_no_binary")
def _t7():
    sweep = (REPO / "scripts" / "_sweep_validators.py").read_text(encoding="utf-8")
    assert "NEEDS_BINARY" in sweep, "sweep should know which validators need C++ binaries"
    assert "SKIP_NO_BINARY" in sweep, "sweep should report SKIP_NO_BINARY when binaries absent"


def main() -> int:
    failed = 0
    for name, fn in SCENARIOS:
        try:
            fn()
            print(f"[ok ] {name}")
        except AssertionError as e:
            print(f"[FAIL] {name}: {e}")
            failed += 1
    total = len(SCENARIOS)
    print(f"passed {total - failed}/{total}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
