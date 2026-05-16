"""Unit tests for the proactive monitoring subsystem (Phase 8 / T044)."""

from __future__ import annotations

from typing import Any

from app.agent_runtime.proactive import (
    AlertDeduplicator,
    AutoDiagnosisTrigger,
    DegradedMetricProvider,
    InMemoryAlertStore,
    MetricAnomaly,
    ProactiveMonitor,
    ProbeResult,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeMetricProvider:
    """Configurable fake metric provider for testing."""

    def __init__(
        self,
        *,
        cpu_max: float = 50.0,
        memory_max: float = 40.0,
        cpu_alert_msg: str = "CPU 正常",
        mem_alert_msg: str = "内存正常",
    ) -> None:
        self._cpu_max = cpu_max
        self._mem_max = memory_max
        self._cpu_msg = cpu_alert_msg
        self._mem_msg = mem_alert_msg
        self.calls: list[str] = []

    def get_cpu_metrics(self, service_name: str, *, scenario: str = "critical") -> dict[str, Any]:
        self.calls.append(f"cpu:{service_name}")
        spike = self._cpu_max > 80.0
        return {
            "service_name": service_name,
            "metric_name": "cpu_usage_percent",
            "statistics": {
                "avg": self._cpu_max * 0.8,
                "max": self._cpu_max,
                "min": self._cpu_max * 0.5,
                "spike_detected": spike,
            },
            "alert_info": {
                "triggered": spike,
                "threshold": 80.0,
                "message": self._cpu_msg,
            },
        }

    def get_memory_metrics(
        self, service_name: str, *, scenario: str = "critical"
    ) -> dict[str, Any]:
        self.calls.append(f"mem:{service_name}")
        pressure = self._mem_max > 70.0
        return {
            "service_name": service_name,
            "metric_name": "memory_usage_percent",
            "statistics": {
                "avg": self._mem_max * 0.8,
                "max": self._mem_max,
                "min": self._mem_max * 0.5,
                "memory_pressure": pressure,
            },
            "alert_info": {
                "triggered": pressure,
                "threshold": 70.0,
                "message": self._mem_msg,
            },
        }


class _FailingMetricProvider:
    """Provider that raises on every call — tests degraded fallback path."""

    def get_cpu_metrics(self, service_name: str, *, scenario: str = "critical") -> dict[str, Any]:
        raise ConnectionError("external monitoring unavailable")

    def get_memory_metrics(
        self, service_name: str, *, scenario: str = "critical"
    ) -> dict[str, Any]:
        raise ConnectionError("external monitoring unavailable")


def _make_monitor(
    *,
    cpu_max: float = 50.0,
    memory_max: float = 40.0,
    services: list[str] | None = None,
    suppress_interval: float = 1800.0,
    trigger: AutoDiagnosisTrigger | None = None,
) -> tuple[ProactiveMonitor, _FakeMetricProvider, AlertDeduplicator]:
    provider = _FakeMetricProvider(cpu_max=cpu_max, memory_max=memory_max)
    store = InMemoryAlertStore()
    dedup = AlertDeduplicator(store=store, suppress_interval_seconds=suppress_interval)
    monitor = ProactiveMonitor(
        metric_provider=provider,
        deduplicator=dedup,
        trigger=trigger,
        services=services or ["api-gateway"],
    )
    return monitor, provider, dedup


# ---------------------------------------------------------------------------
# AlertDeduplicator tests
# ---------------------------------------------------------------------------


class TestAlertDeduplicator:
    def test_first_alert_not_suppressed(self):
        store = InMemoryAlertStore()
        dedup = AlertDeduplicator(store=store, suppress_interval_seconds=60)
        assert dedup.should_suppress("svc:cpu") is False

    def test_same_alert_suppressed_within_window(self):
        store = InMemoryAlertStore()
        clock_value = 1000.0
        dedup = AlertDeduplicator(
            store=store,
            suppress_interval_seconds=60,
            clock=lambda: clock_value,
        )
        dedup.record_alert("svc:cpu")
        assert dedup.should_suppress("svc:cpu") is True

    def test_same_alert_not_suppressed_after_window(self):
        store = InMemoryAlertStore()
        clock_value = 1000.0
        dedup = AlertDeduplicator(
            store=store,
            suppress_interval_seconds=60,
            clock=lambda: clock_value,
        )
        dedup.record_alert("svc:cpu")
        clock_value = 1070.0  # 70 seconds later > 60s window
        assert dedup.should_suppress("svc:cpu") is False

    def test_different_metric_not_suppressed(self):
        store = InMemoryAlertStore()
        clock_value = 1000.0
        dedup = AlertDeduplicator(
            store=store,
            suppress_interval_seconds=60,
            clock=lambda: clock_value,
        )
        dedup.record_alert("svc:cpu")
        assert dedup.should_suppress("svc:memory") is False


# ---------------------------------------------------------------------------
# ProactiveMonitor probe tests
# ---------------------------------------------------------------------------


class TestProactiveMonitorProbe:
    def test_no_anomalies_when_metrics_healthy(self):
        monitor, provider, _ = _make_monitor(cpu_max=30.0, memory_max=40.0)
        result = monitor.probe()
        assert result.anomalies == []
        assert result.alerts_emitted == []
        assert result.services_polled == 1

    def test_cpu_anomaly_detected(self):
        monitor, provider, _ = _make_monitor(cpu_max=92.0, memory_max=40.0)
        result = monitor.probe()
        assert len(result.anomalies) == 1
        assert result.anomalies[0].metric_type == "cpu"
        assert result.anomalies[0].max_value == 92.0
        assert len(result.alerts_emitted) == 1
        # 92% >= 80% threshold but < 96% (1.2x), so severity is "warning"
        assert result.alerts_emitted[0].severity == "warning"

    def test_memory_anomaly_detected(self):
        monitor, provider, _ = _make_monitor(cpu_max=30.0, memory_max=78.0)
        result = monitor.probe()
        assert len(result.anomalies) == 1
        assert result.anomalies[0].metric_type == "memory"

    def test_both_cpu_and_memory_anomalies(self):
        monitor, provider, _ = _make_monitor(cpu_max=90.0, memory_max=80.0)
        result = monitor.probe()
        assert len(result.anomalies) == 2
        assert len(result.alerts_emitted) == 2

    def test_alert_suppressed_on_second_probe(self):
        monitor, provider, _ = _make_monitor(cpu_max=90.0, memory_max=40.0, suppress_interval=60)
        r1 = monitor.probe()
        assert len(r1.alerts_emitted) == 1
        # Second probe immediately — same alert should be suppressed
        r2 = monitor.probe()
        assert r2.alerts_suppressed == 1
        assert len(r2.alerts_emitted) == 0

    def test_probe_multiple_services(self):
        monitor, provider, _ = _make_monitor(cpu_max=90.0, services=["svc-a", "svc-b"])
        result = monitor.probe()
        assert result.services_polled == 2
        assert len(result.anomalies) == 2  # one CPU anomaly per service

    def test_probe_with_no_services(self):
        provider = _FakeMetricProvider(cpu_max=30.0)
        store = InMemoryAlertStore()
        dedup = AlertDeduplicator(store=store)
        monitor = ProactiveMonitor(
            metric_provider=provider,
            deduplicator=dedup,
            services=[],
        )
        result = monitor.probe()
        assert result.services_polled == 0
        assert result.anomalies == []

    def test_provider_failure_does_not_crash_probe(self):
        store = InMemoryAlertStore()
        dedup = AlertDeduplicator(store=store)
        monitor = ProactiveMonitor(
            metric_provider=_FailingMetricProvider(),
            deduplicator=dedup,
            services=["broken-svc"],
        )
        result = monitor.probe()
        # Failing provider → no stats → no anomalies
        assert result.anomalies == []
        assert result.services_polled == 1

    def test_probe_records_timestamp(self):
        clock_value = 500.0
        monitor, _, _ = _make_monitor(cpu_max=30.0)
        monitor._clock = lambda: clock_value
        monitor.probe()
        assert monitor._last_probe_time == 500.0

    def test_should_probe_respects_interval(self):
        clock_value = 0.0
        monitor, _, _ = _make_monitor(cpu_max=30.0)
        monitor._clock = lambda: clock_value
        assert monitor.should_probe() is True
        monitor.probe()
        clock_value = 30.0  # 30s < 60s default interval
        assert monitor.should_probe() is False
        clock_value = 61.0
        assert monitor.should_probe() is True


# ---------------------------------------------------------------------------
# AutoDiagnosisTrigger tests
# ---------------------------------------------------------------------------


class TestAutoDiagnosisTrigger:
    def test_trigger_creates_run(self):
        created_runs: list[dict[str, Any]] = []

        def _create(scene_id: str, session_id: str, goal: str) -> str:
            created_runs.append({"scene": scene_id, "session": session_id, "goal": goal})
            return "run-42"

        trigger = AutoDiagnosisTrigger(run_creator=_create, scene_id="scene-1")
        anomaly = MetricAnomaly(
            service_name="api-gw",
            metric_type="cpu",
            max_value=95.0,
            threshold=80.0,
            message="CPU spike",
        )
        run_id = trigger.trigger(service_name="api-gw", anomalies=[anomaly])
        assert run_id == "run-42"
        assert len(created_runs) == 1
        assert created_runs[0]["scene"] == "scene-1"
        assert "api-gw" in created_runs[0]["goal"]
        assert "95%" in created_runs[0]["goal"]

    def test_trigger_returns_none_on_failure(self):
        def _fail(scene_id: str, session_id: str, goal: str) -> str | None:
            return None

        trigger = AutoDiagnosisTrigger(run_creator=_fail, scene_id="scene-1")
        anomaly = MetricAnomaly(
            service_name="svc",
            metric_type="cpu",
            max_value=90.0,
            threshold=80.0,
            message="spike",
        )
        assert trigger.trigger(service_name="svc", anomalies=[anomaly]) is None

    def test_trigger_increments_session_id(self):
        sessions: list[str] = []

        def _create(scene_id: str, session_id: str, goal: str) -> str:
            sessions.append(session_id)
            return f"run-{len(sessions)}"

        trigger = AutoDiagnosisTrigger(run_creator=_create, scene_id="s1")
        a = MetricAnomaly(
            service_name="svc",
            metric_type="cpu",
            max_value=90.0,
            threshold=80.0,
            message="spike",
        )
        trigger.trigger(service_name="svc", anomalies=[a])
        trigger.trigger(service_name="svc", anomalies=[a])
        assert sessions == ["proactive-1", "proactive-2"]


# ---------------------------------------------------------------------------
# Monitor + Trigger integration
# ---------------------------------------------------------------------------


class TestMonitorTriggerIntegration:
    def test_anomaly_triggers_diagnosis_run(self):
        created_runs: list[dict[str, str]] = []

        def _create(scene_id: str, session_id: str, goal: str) -> str:
            created_runs.append({"scene": scene_id, "goal": goal})
            return f"run-{len(created_runs)}"

        trigger = AutoDiagnosisTrigger(run_creator=_create, scene_id="scene-proactive")
        monitor, _, _ = _make_monitor(cpu_max=92.0, trigger=trigger)
        result = monitor.probe()
        assert result.diagnosis_triggered is True
        assert result.run_id == "run-1"
        assert len(created_runs) == 1

    def test_no_anomaly_no_trigger(self):
        created: list[str] = []

        def _create(scene_id: str, session_id: str, goal: str) -> str:
            created.append(goal)
            return "run-1"

        trigger = AutoDiagnosisTrigger(run_creator=_create, scene_id="s1")
        monitor, _, _ = _make_monitor(cpu_max=30.0, trigger=trigger)
        result = monitor.probe()
        assert result.diagnosis_triggered is False
        assert created == []


# ---------------------------------------------------------------------------
# DegradedMetricProvider tests
# ---------------------------------------------------------------------------


class TestDegradedMetricProvider:
    def test_returns_critical_synthetic_metrics(self):
        provider = DegradedMetricProvider()
        cpu = provider.get_cpu_metrics("any-service")
        assert cpu["statistics"]["max"] >= 90.0
        assert cpu["alert_info"]["triggered"] is True
        assert "_source" in cpu

    def test_memory_returns_pressure(self):
        provider = DegradedMetricProvider()
        mem = provider.get_memory_metrics("any-service")
        assert mem["statistics"]["max"] >= 80.0
        assert mem["alert_info"]["triggered"] is True


# ---------------------------------------------------------------------------
# MetricAnomaly auto alert_key
# ---------------------------------------------------------------------------


class TestMetricAnomaly:
    def test_alert_key_auto_generated(self):
        a = MetricAnomaly(
            service_name="svc",
            metric_type="cpu",
            max_value=90.0,
            threshold=80.0,
            message="spike",
        )
        assert a.alert_key == "svc:cpu"

    def test_alert_key_custom(self):
        a = MetricAnomaly(
            service_name="svc",
            metric_type="cpu",
            max_value=90.0,
            threshold=80.0,
            message="spike",
            alert_key="custom:key",
        )
        assert a.alert_key == "custom:key"


# ---------------------------------------------------------------------------
# ProbeResult
# ---------------------------------------------------------------------------


class TestProbeResult:
    def test_default_fields(self):
        r = ProbeResult(services_polled=0)
        assert r.anomalies == []
        assert r.alerts_emitted == []
        assert r.alerts_suppressed == 0
        assert r.diagnosis_triggered is False
        assert r.run_id is None
        assert r.degraded is False
