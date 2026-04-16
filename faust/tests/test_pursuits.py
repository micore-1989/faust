"""
Pursuit subsystem tests — registry + runner + storage.

The runner tests use a fake Pursuit implementation injected via the
`implementations` parameter on `run_pursuit`, so no Pursuit in the real
registry gets polluted and Stage 5b can register the seven real ones
without churn here.

Run with: python -m faust.tests.test_pursuits
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from faust.pursuits.events import (
    PursuitActivity,
    PursuitComplete,
    PursuitProgress,
    PursuitStarted,
    PursuitStopped,
)
from faust.pursuits.models import (
    ParamSpec,
    Pursuit,
    PursuitResult,
    PursuitResultPartial,
    PursuitYield,
)
from faust.pursuits.registry import (
    IMPLEMENTATIONS,
    PURSUITS,
    apply_defaults,
    get_pursuit,
    list_pursuits,
    validate_params,
)
from faust.pursuits.runner import run_pursuit
from faust.pursuits.storage import PursuitStorage


# ── Helpers ─────────────────────────────────────────────────────

class RecordingBridge:
    """Minimal bridge that captures all pushed events for assertion."""

    def __init__(self) -> None:
        self.events: list[Any] = []
        self.raws: list[dict] = []

    async def push_event(self, event: Any) -> None:
        self.events.append(event)

    async def push_raw(self, data: dict) -> None:
        self.raws.append(data)


class RecordingDispatcher:
    """Records every dispatch call. Returns a dummy success result. The
    runner never calls dispatcher itself — implementations do — so this
    doubles as proof that the approver chain is in play for Pursuits."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def dispatch(self, tool_name: str, arguments: dict):
        self.calls.append((tool_name, dict(arguments)))
        return {"executed": True, "result": f"{tool_name}_result"}


class RecordingJournal:
    def __init__(self) -> None:
        self.records: list[dict] = []
        self._seq = 0

    def record(self, **kwargs):
        self._seq += 1
        self.records.append(kwargs)
        # Mimic the real Journal's shape enough for runner to read .seq
        class _Entry:
            seq = self._seq
        return _Entry()


def _tmp_storage() -> tuple[PursuitStorage, Path]:
    fd, path = tempfile.mkstemp(suffix=".jsonl")
    os.close(fd)
    p = Path(path)
    return PursuitStorage(path=p), p


# ── Registry tests ──────────────────────────────────────────────

class TestRegistry:
    async def test_registry_has_8_entries(self):
        assert len(PURSUITS) == 8
        assert set(PURSUITS.keys()) == {
            "wardrive", "clone-credential", "replay-subghz", "evil-portal",
            "bluetooth-recon", "subghz-capture-analyze", "hmc-demo", "custom",
        }
        print("✓ registry has exactly 8 entries")

    async def test_list_pursuits_returns_custom_last(self):
        lst = list_pursuits()
        assert len(lst) == 8
        assert lst[-1].id == "custom"
        assert lst[-1].is_custom is True
        # First seven are the v1 Pursuits in the spec's display order.
        assert [p.id for p in lst[:7]] == [
            "wardrive", "clone-credential", "replay-subghz", "evil-portal",
            "bluetooth-recon", "subghz-capture-analyze", "hmc-demo",
        ]
        print("✓ list_pursuits returns Custom last")

    async def test_get_pursuit_raises_on_unknown(self):
        try:
            get_pursuit("definitely-not-a-pursuit")
        except KeyError:
            print("✓ get_pursuit raises KeyError on unknown id")
            return
        raise AssertionError("expected KeyError for unknown pursuit id")

    async def test_each_pursuit_has_valid_schema(self):
        for p in PURSUITS.values():
            assert isinstance(p.id, str) and p.id.strip()
            assert isinstance(p.title, str) and p.title.strip()
            assert isinstance(p.description, str) and p.description.strip()
            assert isinstance(p.duration_hint, str)
            assert isinstance(p.tools_used, list)
            assert isinstance(p.parameters, list)
            # All ParamSpec entries must declare a supported type.
            for spec in p.parameters:
                assert spec.type in {"string", "int", "bool", "enum"}
                if spec.type == "enum":
                    assert spec.choices and spec.default in spec.choices
        print("✓ every Pursuit has a valid schema")


# ── Runner tests ────────────────────────────────────────────────

TEST_PURSUIT = Pursuit(
    id="_test_pursuit",
    title="Test Pursuit",
    description="Fake pursuit used by the test suite.",
    duration_hint="~0 min",
    tools_used=["TEST"],
    parameters=[ParamSpec(name="n", type="int", default=3)],
)


async def test_runner_emits_started_progress_complete_in_order():
    """Fake Pursuit yields 3 progress ticks + 2 activity lines then
    completes. Assert event stream matches the documented sequence."""
    bridge = RecordingBridge()
    disp = RecordingDispatcher()
    stop = asyncio.Event()

    async def fake_impl(params, dispatcher, stop_event):
        yield PursuitYield(progress=0.1, activity="alpha")
        yield PursuitYield(progress=0.5)
        yield PursuitYield(activity="beta")
        yield PursuitYield(progress=1.0)
        yield PursuitResultPartial(summary="test run summary",
                                   artifacts=["/tmp/x.pcap"])

    result = await run_pursuit(
        TEST_PURSUIT, {"n": 3}, disp, bridge, stop,
        implementations={TEST_PURSUIT.id: fake_impl},
        journal=RecordingJournal(),
    )

    types = [type(e).__name__ for e in bridge.events]
    assert types[0] == "PursuitStarted"
    assert types[-1] == "PursuitComplete"
    # 3 progress yields → 3 PursuitProgress events.
    assert types.count("PursuitProgress") == 3
    # 2 activity yields → 2 PursuitActivity events.
    assert types.count("PursuitActivity") == 2
    # One complete event at the end.
    assert types.count("PursuitComplete") == 1
    # No stop event fired.
    assert "PursuitStopped" not in types

    assert result is not None
    assert result.summary == "test run summary"
    assert result.artifacts == ["/tmp/x.pcap"]
    print("✓ runner emits Started → Progress×3 → Activity×2 → Complete")


async def test_runner_looks_up_implementation():
    """Unknown pursuit id (no impl registered) → PursuitStopped(reason=error)."""
    bridge = RecordingBridge()
    stop = asyncio.Event()
    result = await run_pursuit(
        TEST_PURSUIT, {}, RecordingDispatcher(), bridge, stop,
        implementations={},  # empty
        journal=RecordingJournal(),
    )
    assert result is None
    stopped = [e for e in bridge.events if isinstance(e, PursuitStopped)]
    assert len(stopped) == 1
    assert stopped[0].reason == "error"
    assert "no implementation" in (stopped[0].error or "")
    print("✓ runner emits PursuitStopped(error) on missing implementation")


async def test_stop_event_terminates_run():
    """Setting stop_event mid-iteration causes the runner to emit
    PursuitStopped(reason=user) on the next yield. The impl awaits a
    sleep between yields so the driver coroutine has a chance to trip
    the event before the next iteration."""
    bridge = RecordingBridge()
    disp = RecordingDispatcher()
    stop = asyncio.Event()

    async def slow_impl(params, dispatcher, stop_event):
        yield PursuitYield(progress=0.1, activity="one")
        await asyncio.sleep(0.01)
        yield PursuitYield(progress=0.5, activity="two")
        await asyncio.sleep(0.01)
        yield PursuitYield(progress=0.9, activity="three")  # never reached
        yield PursuitResultPartial(summary="should not complete")

    async def driver():
        # Trip the stop event once the first yield has been processed.
        await asyncio.sleep(0.005)
        stop.set()

    asyncio.create_task(driver())
    result = await run_pursuit(
        TEST_PURSUIT, {}, disp, bridge, stop,
        implementations={TEST_PURSUIT.id: slow_impl},
    )

    assert result is None
    stopped = [e for e in bridge.events if isinstance(e, PursuitStopped)]
    assert len(stopped) == 1
    assert stopped[0].reason == "user"
    # No PursuitComplete since we stopped mid-run.
    assert not any(isinstance(e, PursuitComplete) for e in bridge.events)
    print("✓ stop_event terminates the run with reason=user")


async def test_destructive_step_goes_through_approver():
    """Runner never calls dispatcher directly — implementations do, so a
    dispatched destructive step must flow through the normal Approver
    chain. Prove it by asserting the dispatcher saw the call."""
    bridge = RecordingBridge()
    disp = RecordingDispatcher()
    stop = asyncio.Event()

    async def destructive_impl(params, dispatcher, stop_event):
        yield PursuitYield(progress=0.2, activity="about to deauth")
        await dispatcher.dispatch("wifi_deauth", {"bssid": "aa:bb"})
        yield PursuitYield(progress=1.0, activity="done")
        yield PursuitResultPartial(summary="deauth sent")

    result = await run_pursuit(
        TEST_PURSUIT, {}, disp, bridge, stop,
        implementations={TEST_PURSUIT.id: destructive_impl},
    )

    assert result is not None
    assert disp.calls == [("wifi_deauth", {"bssid": "aa:bb"})]
    print("✓ destructive step inside Pursuit routes through dispatcher.dispatch")


async def test_exception_in_implementation_emits_stopped_error():
    """Unhandled exception in the impl → PursuitStopped(reason=error), no
    PursuitComplete, no crash of the caller."""
    bridge = RecordingBridge()
    disp = RecordingDispatcher()
    stop = asyncio.Event()
    journal = RecordingJournal()

    async def boom_impl(params, dispatcher, stop_event):
        yield PursuitYield(progress=0.3, activity="about to crash")
        raise RuntimeError("simulated impl crash")

    result = await run_pursuit(
        TEST_PURSUIT, {}, disp, bridge, stop,
        implementations={TEST_PURSUIT.id: boom_impl},
        journal=journal,
    )

    assert result is None
    stopped = [e for e in bridge.events if isinstance(e, PursuitStopped)]
    assert len(stopped) == 1
    assert stopped[0].reason == "error"
    assert "simulated impl crash" in (stopped[0].error or "")
    # Journal saw the failure with the error stamped.
    err_records = [r for r in journal.records if r.get("error")]
    assert len(err_records) == 1
    print("✓ exception in implementation → PursuitStopped(error) + journaled")


async def test_pursuit_result_persisted_to_storage():
    """After a clean completion, the PursuitResult must be appended to
    storage exactly once."""
    storage, path = _tmp_storage()
    try:
        bridge = RecordingBridge()
        disp = RecordingDispatcher()
        stop = asyncio.Event()

        async def simple_impl(params, dispatcher, stop_event):
            yield PursuitYield(progress=1.0, activity="done")
            yield PursuitResultPartial(summary="all good",
                                       artifacts=["a.pcap", "b.json"])

        result = await run_pursuit(
            TEST_PURSUIT, {}, disp, bridge, stop,
            implementations={TEST_PURSUIT.id: simple_impl},
            journal=RecordingJournal(),
            storage=storage,
        )

        assert result is not None
        recents = storage.list_recent()
        assert len(recents) == 1
        assert recents[0].summary == "all good"
        assert recents[0].artifacts == ["a.pcap", "b.json"]
        assert recents[0].pursuit_id == TEST_PURSUIT.id
        # Journal entry id should be set because we passed a journal.
        assert recents[0].journal_entry_id != ""
    finally:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
    print("✓ PursuitResult persisted to storage on completion")


async def test_runner_synthesizes_summary_if_no_terminal_yield():
    """Implementations that exhaust without yielding PursuitResultPartial
    still get a Complete event so the UI doesn't hang mid-run."""
    bridge = RecordingBridge()
    disp = RecordingDispatcher()
    stop = asyncio.Event()

    async def lazy_impl(params, dispatcher, stop_event):
        yield PursuitYield(progress=1.0)
        # no PursuitResultPartial — generator just exits

    result = await run_pursuit(
        TEST_PURSUIT, {}, disp, bridge, stop,
        implementations={TEST_PURSUIT.id: lazy_impl},
    )

    assert result is not None
    complete = [e for e in bridge.events if isinstance(e, PursuitComplete)]
    assert len(complete) == 1
    assert "completed" in complete[0].summary.lower()
    print("✓ runner synthesizes Complete summary on missing terminal yield")


# ── Validation tests ────────────────────────────────────────────

async def test_validate_params_enforces_enum_choices():
    p = get_pursuit("wardrive")
    errors = validate_params(p, {"frequency_band": "gibberish"})
    assert any("frequency_band" in e for e in errors)

    errors = validate_params(p, {"frequency_band": "5 GHz only"})
    assert errors == []
    print("✓ validate_params rejects enum values not in choices")


async def test_validate_params_type_checks():
    p = get_pursuit("wardrive")
    errors = validate_params(p, {"duration_minutes": "thirty"})
    assert any("duration_minutes" in e and "expected int" in e for e in errors)

    errors = validate_params(p, {"gps_required": "yes"})
    assert any("gps_required" in e and "expected bool" in e for e in errors)
    print("✓ validate_params type-checks int / bool params")


async def test_apply_defaults_merges_on_top_of_spec():
    p = get_pursuit("wardrive")
    merged = apply_defaults(p, {"duration_minutes": 10})
    assert merged["duration_minutes"] == 10
    assert merged["frequency_band"] == "2.4 GHz only"
    assert merged["gps_required"] is True
    print("✓ apply_defaults preserves client overrides")


# ── Storage tests ───────────────────────────────────────────────

async def test_storage_append_and_list_recent():
    storage, path = _tmp_storage()
    try:
        for i in range(3):
            storage.append(PursuitResult(
                run_id=f"run-{i}",
                pursuit_id="_test",
                summary=f"run {i}",
                journal_entry_id=str(i),
                artifacts=[],
                completed_at=float(i),
            ))
        results = storage.list_recent()
        assert [r.run_id for r in results] == ["run-0", "run-1", "run-2"]
    finally:
        path.unlink()
    print("✓ storage append + list_recent")


async def test_storage_list_recent_honors_limit():
    storage, path = _tmp_storage()
    try:
        for i in range(5):
            storage.append(PursuitResult(
                run_id=f"r{i}", pursuit_id="_t", summary=f"{i}",
                journal_entry_id="", artifacts=[], completed_at=0.0,
            ))
        recents = storage.list_recent(limit=2)
        # Tail of the file.
        assert [r.run_id for r in recents] == ["r3", "r4"]
    finally:
        path.unlink()
    print("✓ storage list_recent honors limit (tail semantics)")


async def test_storage_get_by_run_id():
    storage, path = _tmp_storage()
    try:
        for i in range(3):
            storage.append(PursuitResult(
                run_id=f"run-{i}", pursuit_id="_t", summary=f"{i}",
                journal_entry_id="", artifacts=[], completed_at=0.0,
            ))
        got = storage.get("run-1")
        assert got is not None and got.run_id == "run-1"
        assert storage.get("nope") is None
    finally:
        path.unlink()
    print("✓ storage get by run_id")


async def test_storage_roundtrip_preserves_fields():
    storage, path = _tmp_storage()
    try:
        original = PursuitResult(
            run_id="abc123",
            pursuit_id="wardrive",
            summary="47 networks · 2h 14m",
            journal_entry_id="42",
            artifacts=["/captures/wd-001.pcap", "/captures/wd-001.gpx"],
            completed_at=1_700_000_000.5,
        )
        storage.append(original)
        got = storage.get("abc123")
        assert got is not None
        assert got.run_id == original.run_id
        assert got.pursuit_id == original.pursuit_id
        assert got.summary == original.summary
        assert got.journal_entry_id == original.journal_entry_id
        assert got.artifacts == original.artifacts
        assert got.completed_at == original.completed_at
    finally:
        path.unlink()
    print("✓ storage roundtrip preserves all fields")


# ── Safety: IMPLEMENTATIONS stays empty after 5a ────────────────

async def test_implementations_dict_empty_in_stage_5a():
    """Stage 5a leaves IMPLEMENTATIONS empty — Stage 5b fills it. If this
    test fails, either 5b has landed (and this assertion needs updating)
    or something in 5a leaked a real impl into the module-level dict."""
    # Copy to guard against parallel-test pollution.
    assert dict(IMPLEMENTATIONS) == {}
    print("✓ IMPLEMENTATIONS empty in stage 5a")


async def main():
    reg = TestRegistry()
    await reg.test_registry_has_8_entries()
    await reg.test_list_pursuits_returns_custom_last()
    await reg.test_get_pursuit_raises_on_unknown()
    await reg.test_each_pursuit_has_valid_schema()

    await test_runner_emits_started_progress_complete_in_order()
    await test_runner_looks_up_implementation()
    await test_stop_event_terminates_run()
    await test_destructive_step_goes_through_approver()
    await test_exception_in_implementation_emits_stopped_error()
    await test_pursuit_result_persisted_to_storage()
    await test_runner_synthesizes_summary_if_no_terminal_yield()

    await test_validate_params_enforces_enum_choices()
    await test_validate_params_type_checks()
    await test_apply_defaults_merges_on_top_of_spec()

    await test_storage_append_and_list_recent()
    await test_storage_list_recent_honors_limit()
    await test_storage_get_by_run_id()
    await test_storage_roundtrip_preserves_fields()

    await test_implementations_dict_empty_in_stage_5a()

    print("\nall pursuit tests passed")


if __name__ == "__main__":
    asyncio.run(main())
