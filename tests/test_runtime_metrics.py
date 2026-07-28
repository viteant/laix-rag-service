from app.pipeline import runtime_metrics


def test_worker_runtime_snapshot_reads_cgroup_and_load(monkeypatch):
    values = {
        "memory.current": "1073741824",
        "memory.max": "max",
        "memory.swap.current": "0",
        "memory.swap.max": "2147483648",
    }
    monkeypatch.setattr(runtime_metrics, "_read_cgroup_int", lambda name: None if values[name] == "max" else int(values[name]))
    monkeypatch.setattr(runtime_metrics.os, "getloadavg", lambda: (1.234, 2.345, 3.456))

    snapshot = runtime_metrics.worker_runtime_snapshot()

    assert snapshot["memory_bytes"] == 1073741824
    assert snapshot["memory_limit_bytes"] is None
    assert snapshot["swap_limit_bytes"] == 2147483648
    assert snapshot["load_1"] == 1.23
    assert snapshot["load_5"] == 2.35
    assert snapshot["load_15"] == 3.46
    assert snapshot["recorded_at"]
