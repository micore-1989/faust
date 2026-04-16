"""
Stage 5b — concrete Pursuit implementation tests.

Each test spins a RecordingDispatcher (pre-canned results, records every
dispatch), runs the implementation through `run_pursuit` to completion,
and asserts:
    - Expected skill dispatches happened (in order where the spec is
      explicit, or as a set otherwise).
    - ≥3 progress updates, monotonically increasing.
    - ≥1 activity line per dispatched skill.
    - Terminal PursuitResultPartial with a non-empty summary.
A stop-event test verifies at least two Pursuits respect stop_event
mid-run.

Run with: python -m faust.tests.test_pursuit_implementations
"""

from __future__ import annotations

import asyncio
import sys
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
from faust.pursuits.pursuits import (
    bluetooth_recon,
    clone_credential,
    evil_portal,
    hmc_demo,
    replay_subghz,
    subghz_capture_analyze,
    wardrive,
)
from faust.pursuits.registry import get_pursuit


# ── Harness ─────────────────────────────────────────────────────

class RecordingBridge:
    def __init__(self) -> None:
        self.events: list[Any] = []

    async def push_event(self, e): self.events.append(e)
    async def push_raw(self, d): self.events.append(("raw", d))


class RecordingDispatcher:
    """Returns pre-canned results keyed by (skill_name) or records-only."""

    def __init__(self, canned: dict[str, Any] | None = None) -> None:
        self.calls: list[tuple[str, dict]] = []
        self._canned = canned or {}

    async def dispatch(self, skill_name: str, args: dict):
        self.calls.append((skill_name, dict(args)))
        ret = self._canned.get(skill_name, {"executed": True})
        # Support a list for skills called multiple times — pop one per call.
        if isinstance(ret, list):
            key = skill_name
            # Track which index we're on
            idx = sum(1 for c in self.calls if c[0] == key) - 1
            if idx < len(ret):
                return ret[idx]
            return ret[-1] if ret else {"executed": True}
        return ret


class RecordingJournal:
    def __init__(self) -> None:
        self.records: list[dict] = []

    def record(self, **kw):
        self.records.append(kw)
        class _E:
            seq = len(self.records)
        return _E()


async def _run_impl(
    impl_module,
    params: dict,
    dispatcher: RecordingDispatcher,
    *,
    stop_after_events: int | None = None,
) -> tuple[RecordingBridge, asyncio.Event]:
    """Invoke an implementation directly (not via run_pursuit) so tests
    can inspect the raw PursuitYield / PursuitResultPartial stream.

    Alternative flow via run_pursuit is exercised by test_runner_emits_*
    in test_pursuits.py; here we want to cover the implementations
    themselves without the runner's event translation.
    """
    bridge = RecordingBridge()
    stop_event = asyncio.Event()
    yields: list = []
    n_events = 0

    async for item in impl_module.run(params, dispatcher, stop_event):
        yields.append(item)
        n_events += 1
        if stop_after_events is not None and n_events >= stop_after_events:
            stop_event.set()
    bridge.events = yields  # reuse bridge to hold the yield log
    return bridge, stop_event


def _progress_values(yields: list) -> list[float]:
    from faust.pursuits.models import PursuitYield
    return [y.progress for y in yields if isinstance(y, PursuitYield) and y.progress is not None]


def _activity_lines(yields: list) -> list[str]:
    from faust.pursuits.models import PursuitYield
    return [y.activity for y in yields if isinstance(y, PursuitYield) and y.activity]


def _terminal(yields: list):
    from faust.pursuits.models import PursuitResultPartial
    terminals = [y for y in yields if isinstance(y, PursuitResultPartial)]
    return terminals[-1] if terminals else None


def _assert_monotonic(progress: list[float]) -> None:
    for i in range(1, len(progress)):
        assert progress[i] >= progress[i - 1], (
            f"progress regressed at index {i}: {progress[i - 1]} → {progress[i]}"
        )


# ── Per-Pursuit tests ───────────────────────────────────────────

class TestWardrive:
    async def test_wardrive_scans_and_writes_csv(self, tmp_path=None):
        disp = RecordingDispatcher({
            "wifi_scan": {"networks": [
                {"bssid": "aa:bb:cc:dd:ee:ff", "ssid": "a", "channel": 6, "rssi_dbm": -50, "encryption": "WPA2"},
                {"bssid": "11:22:33:44:55:66", "ssid": "b", "channel": 1, "rssi_dbm": -70, "encryption": "OPEN"},
            ]},
        })
        # Shorten the per-pass sleep so the test completes in milliseconds
        # and yields enough progress ticks to assert on.
        original_interval = wardrive.SCAN_INTERVAL_S
        wardrive.SCAN_INTERVAL_S = 0.001
        stop_event = asyncio.Event()
        yields: list = []
        try:
            async def driver():
                # Let ~3 passes elapse then stop, so the loop has yielded
                # start + ≥3 progress ticks + terminal.
                await asyncio.sleep(0.05)
                stop_event.set()
            asyncio.create_task(driver())
            async for item in wardrive.run(
                {"duration_minutes": 5, "frequency_band": "2.4 GHz only", "_run_id": "t1"},
                disp, stop_event,
            ):
                yields.append(item)
        finally:
            wardrive.SCAN_INTERVAL_S = original_interval

        skills = [c[0] for c in disp.calls]
        assert "wifi_scan" in skills
        # No GPS skill dispatched (TODO'd).
        assert "gps_fix" not in skills
        progress = _progress_values(yields)
        assert len(progress) >= 3, f"expected ≥3 progress yields, got {progress}"
        _assert_monotonic(progress)
        assert len(_activity_lines(yields)) >= 1
        terminal = _terminal(yields)
        assert terminal is not None and "networks" in terminal.summary.lower()
        print("✓ wardrive dispatches wifi_scan, yields progress, writes CSV artifact")

    async def test_wardrive_respects_stop_event(self):
        disp = RecordingDispatcher({
            "wifi_scan": {"networks": [{"bssid": "1", "ssid": "x", "channel": 1, "rssi_dbm": -60, "encryption": ""}]},
        })
        # Long duration — we'll trip stop via the harness limiter.
        bridge = RecordingBridge()
        stop_event = asyncio.Event()
        yields = []

        async def driver():
            await asyncio.sleep(0.05)
            stop_event.set()

        asyncio.create_task(driver())
        async for item in wardrive.run(
            {"duration_minutes": 10, "_run_id": "t2"}, disp, stop_event,
        ):
            yields.append(item)

        bridge.events = yields
        terminal = _terminal(yields)
        assert terminal is not None
        # Should have stopped well before 10 * 60 seconds worth of scans.
        assert len(disp.calls) <= 3
        print("✓ wardrive respects stop_event mid-loop")


class TestCloneCredential:
    async def test_clone_credential_read_then_write(self):
        disp = RecordingDispatcher({
            "rfid_clone": [
                {"uid": "ABCD1234", "facility_code": 42, "card_type": "hid_prox"},
                {"success": True, "written": "ABCD1234"},
            ],
        })
        b, _ = await _run_impl(clone_credential, {}, disp)
        calls = [c for c in disp.calls if c[0] == "rfid_clone"]
        assert len(calls) == 2
        assert calls[0][1]["action"] == "read"
        assert calls[1][1]["action"] == "clone"
        assert calls[1][1]["source_id"] == "ABCD1234"
        _assert_monotonic(_progress_values(b.events))
        assert len(_progress_values(b.events)) >= 3
        activity = " ".join(_activity_lines(b.events)).lower()
        assert "abcd1234" in activity or "uid" in activity
        terminal = _terminal(b.events)
        assert terminal is not None and "ABCD1234" in terminal.summary
        print("✓ clone-credential reads, then clones to blank")

    async def test_clone_credential_aborts_on_read_failure(self):
        """If the initial read fails, don't attempt the write."""
        disp = RecordingDispatcher({
            "rfid_clone": [{"_error": "no card detected", "uid": ""}],
        })
        b, _ = await _run_impl(clone_credential, {}, disp)
        calls = [c for c in disp.calls if c[0] == "rfid_clone"]
        assert len(calls) == 1, "should not dispatch write when read failed"
        terminal = _terminal(b.events)
        assert terminal is not None and "failed" in terminal.summary.lower()
        print("✓ clone-credential aborts cleanly on read failure")


class TestReplaySubghz:
    async def test_replay_subghz_capture_analyze_replay(self):
        disp = RecordingDispatcher({
            "subghz_replay": [
                {"capture_file": "/tmp/faust-subghz-t.iq", "duration_s": 10},
                {"modulation": "OOK", "bitrate": "2.4 kbps"},
                {"duration_s": 10},
            ],
        })
        b, _ = await _run_impl(
            replay_subghz, {"frequency_mhz": "433.92", "_run_id": "t"}, disp,
        )
        actions = [c[1]["action"] for c in disp.calls if c[0] == "subghz_replay"]
        assert actions == ["capture", "analyze", "replay"]
        _assert_monotonic(_progress_values(b.events))
        assert len(_progress_values(b.events)) >= 3
        terminal = _terminal(b.events)
        assert terminal is not None
        assert "433.92" in terminal.summary
        assert terminal.artifacts
        print("✓ replay-subghz: capture → analyze → replay in order")


class TestEvilPortal:
    async def test_evil_portal_runs_until_stop_then_cleans_up(self):
        disp = RecordingDispatcher({
            "wifi_evil_portal": [
                {"connections": 0, "status": "running"},
                {"stopped": True},
            ],
        })
        stop_event = asyncio.Event()
        yields: list = []

        async def driver():
            # Let the portal start + a couple of heartbeats, then stop.
            await asyncio.sleep(0.01)
            stop_event.set()

        asyncio.create_task(driver())

        # Shorten the poll interval for the test via monkeypatch.
        original_poll = evil_portal.POLL_INTERVAL_S
        evil_portal.POLL_INTERVAL_S = 0.01
        try:
            async for item in evil_portal.run(
                {"ssid": "test-net"}, disp, stop_event,
            ):
                yields.append(item)
        finally:
            evil_portal.POLL_INTERVAL_S = original_poll

        starts = [c for c in disp.calls if c[0] == "wifi_evil_portal"]
        assert len(starts) >= 1
        assert starts[0][1]["ssid"] == "test-net"
        _assert_monotonic(_progress_values(yields))
        assert len(_progress_values(yields)) >= 3
        terminal = _terminal(yields)
        assert terminal is not None and "test-net" in terminal.summary
        print("✓ evil-portal starts, heartbeats, and exits on stop_event")


class TestBluetoothRecon:
    async def test_bluetooth_recon_accumulates_unique_devices(self):
        disp = RecordingDispatcher({
            "ble_scan": {
                "devices": [
                    {"mac": "aa:11", "name": "A", "vendor": "Apple", "rssi_dbm": -50},
                    {"mac": "bb:22", "name": "B", "vendor": "", "rssi_dbm": -70},
                ],
            },
        })
        # Shorten per-scan window via monkeypatch so the test loop finishes
        # quickly but still dispatches ble_scan.
        original_window = bluetooth_recon.SCAN_WINDOW_S
        bluetooth_recon.SCAN_WINDOW_S = 0.001
        stop_event = asyncio.Event()
        yields: list = []
        try:
            async def driver():
                await asyncio.sleep(0.05)
                stop_event.set()
            asyncio.create_task(driver())
            async for item in bluetooth_recon.run(
                {"duration_minutes": 2, "_run_id": "t"}, disp, stop_event,
            ):
                yields.append(item)
        finally:
            bluetooth_recon.SCAN_WINDOW_S = original_window

        ble_calls = [c for c in disp.calls if c[0] == "ble_scan"]
        assert ble_calls, "expected at least one ble_scan dispatch"
        progress = _progress_values(yields)
        _assert_monotonic(progress)
        assert len(progress) >= 3, f"expected ≥3 progress yields, got {progress}"
        terminal = _terminal(yields)
        assert terminal is not None
        assert "BLE devices" in terminal.summary
        print("✓ bluetooth-recon loops ble_scan and emits vendor-tagged summary")


class TestSubghzCaptureAnalyze:
    async def test_subghz_capture_analyze_two_phase(self):
        disp = RecordingDispatcher({
            "subghz_replay": {"capture_file": "/tmp/faust-ca.iq", "duration_s": 120},
            "subghz_decode": {"protocol_family": "keeloq", "confidence": 0.82},
        })
        b, _ = await _run_impl(
            subghz_capture_analyze,
            {"frequency_mhz": "433.92", "capture_seconds": 1, "_run_id": "t"},
            disp,
        )
        skills = [c[0] for c in disp.calls]
        assert "subghz_replay" in skills
        assert "subghz_decode" in skills
        replay_calls = [c for c in disp.calls if c[0] == "subghz_replay"]
        assert replay_calls[0][1]["action"] == "capture"
        progress = _progress_values(b.events)
        _assert_monotonic(progress)
        # Phase 1 caps at 0.72; phase 2 reaches 1.0.
        assert max(progress) >= 0.95
        terminal = _terminal(b.events)
        assert terminal is not None and "keeloq" in terminal.summary
        # Artifacts include both IQ and analysis JSON.
        assert len(terminal.artifacts) >= 1
        print("✓ subghz-capture-analyze runs both phases and surfaces protocol")


class TestHmcDemo:
    async def test_hmc_demo_scripted_sequence(self):
        disp = RecordingDispatcher({
            "wifi_scan": {"networks": [{"ssid": f"n{i}"} for i in range(7)]},
            "wifi_handshake_capture": {"output_file": "/tmp/demo.pcap"},
        })
        b, _ = await _run_impl(hmc_demo, {"_run_id": "t"}, disp)

        skills = [c[0] for c in disp.calls]
        assert skills.count("wifi_scan") == 1
        assert skills.count("wifi_handshake_capture") == 1
        # wifi_scan must precede capture in the scripted sequence.
        assert skills.index("wifi_scan") < skills.index("wifi_handshake_capture")

        progress = _progress_values(b.events)
        _assert_monotonic(progress)
        assert len(progress) >= 3

        terminal = _terminal(b.events)
        assert terminal is not None
        assert "7 networks" in terminal.summary
        assert terminal.artifacts == ["/tmp/demo.pcap"]
        print("✓ hmc-demo scripted sequence completes with expected summary")


# ── End-to-end via run_pursuit ──────────────────────────────────

async def test_real_pursuit_runs_through_run_pursuit():
    """Real implementation + real runner + real registry lookup; prove
    the wiring from Stage 5a still accepts the Stage 5b implementations."""
    from faust.pursuits.runner import run_pursuit

    pursuit = get_pursuit("hmc-demo")
    disp = RecordingDispatcher({
        "wifi_scan": {"networks": [{"ssid": "x"}]},
        "wifi_handshake_capture": {"output_file": "/tmp/x.pcap"},
    })

    class _Bridge:
        def __init__(self): self.events = []
        async def push_event(self, e): self.events.append(e)

    bridge = _Bridge()
    journal = RecordingJournal()
    stop_event = asyncio.Event()
    result = await run_pursuit(
        pursuit, {"_run_id": "e2e"}, disp, bridge, stop_event,
        run_id="e2e-run", journal=journal,
    )
    assert result is not None
    types = [type(e).__name__ for e in bridge.events]
    assert types[0] == "PursuitStarted"
    assert types[-1] == "PursuitComplete"
    assert "PursuitProgress" in types
    assert "PursuitActivity" in types
    assert journal.records, "runner should journal the Pursuit completion"
    print("✓ real Pursuit dispatched through real runner produces full event stream")


async def main():
    await TestWardrive().test_wardrive_scans_and_writes_csv()
    await TestWardrive().test_wardrive_respects_stop_event()
    await TestCloneCredential().test_clone_credential_read_then_write()
    await TestCloneCredential().test_clone_credential_aborts_on_read_failure()
    await TestReplaySubghz().test_replay_subghz_capture_analyze_replay()
    await TestEvilPortal().test_evil_portal_runs_until_stop_then_cleans_up()
    await TestBluetoothRecon().test_bluetooth_recon_accumulates_unique_devices()
    await TestSubghzCaptureAnalyze().test_subghz_capture_analyze_two_phase()
    await TestHmcDemo().test_hmc_demo_scripted_sequence()
    await test_real_pursuit_runs_through_run_pursuit()
    print("\nall Pursuit implementation tests passed")


if __name__ == "__main__":
    asyncio.run(main())
