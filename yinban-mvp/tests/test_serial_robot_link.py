from __future__ import annotations

import sys
import threading
import time
from types import SimpleNamespace

from app.config import Settings
from app.services.robot_link import SerialRobotLink, build_robot_controller
from app.services.robot_protocol import RobotState


class FakeSerial:
    def __init__(self, *, block_writes: bool = False) -> None:
        self.is_open = True
        self.writes: list[bytes] = []
        self.fail_reads = threading.Event()
        self.fail_writes = False
        self.write_started = threading.Event()
        self.release_write = threading.Event()
        if not block_writes:
            self.release_write.set()

    def write(self, payload: bytes) -> None:
        self.write_started.set()
        self.release_write.wait(timeout=1)
        if self.fail_writes:
            raise PermissionError("write denied")
        self.writes.append(payload)

    def readline(self) -> bytes:
        if self.fail_reads.is_set():
            raise PermissionError("read denied")
        time.sleep(0.005)
        return b""

    def close(self) -> None:
        self.is_open = False
        self.release_write.set()


class SerialFactory:
    def __init__(self, outcomes) -> None:
        self.outcomes = list(outcomes)
        self.calls = 0
        self.kwargs: list[dict] = []

    def __call__(self, *args, **kwargs):
        self.calls += 1
        self.kwargs.append(kwargs)
        outcome = self.outcomes[min(self.calls - 1, len(self.outcomes) - 1)]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def install_fake_serial(monkeypatch, factory) -> None:
    serial_module = SimpleNamespace(Serial=factory)
    monkeypatch.setitem(sys.modules, "serial", serial_module)


def wait_until(predicate, timeout: float = 1.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    raise AssertionError("condition did not become true before timeout")


def test_hardware_link_sends_periodic_ping(monkeypatch) -> None:
    fake = FakeSerial()
    factory = SerialFactory([fake])
    install_fake_serial(monkeypatch, factory)
    link = SerialRobotLink("COM5", reconnect_interval_seconds=0.01)
    link.heartbeat_interval_seconds = 0.02

    link.connect()
    try:
        wait_until(lambda: fake.writes.count(b"PING\n") >= 3)
        assert link.status().connected is True
        assert factory.kwargs[0]["timeout"] == 0.2
        assert factory.kwargs[0]["write_timeout"] == 0.5
    finally:
        link.close()


def test_status_remains_fast_while_a_serial_write_is_blocked(monkeypatch) -> None:
    fake = FakeSerial(block_writes=True)
    install_fake_serial(monkeypatch, SerialFactory([fake]))
    link = SerialRobotLink("COM5", reconnect_interval_seconds=0.01)

    link.connect()
    try:
        wait_until(fake.write_started.is_set)
        started_at = time.monotonic()
        snapshot = link.status()
        elapsed = time.monotonic() - started_at

        assert elapsed < 0.1
        assert snapshot.mode == "hardware"
    finally:
        fake.release_write.set()
        link.close()


def test_initial_open_failures_retry_until_the_port_recovers(monkeypatch) -> None:
    fake = FakeSerial()
    factory = SerialFactory(
        [FileNotFoundError("missing"), PermissionError("busy"), fake]
    )
    install_fake_serial(monkeypatch, factory)
    link = SerialRobotLink("COM5", reconnect_interval_seconds=0.01)

    link.connect()
    try:
        wait_until(lambda: link.status().connected)
        assert factory.calls >= 3
        assert link.status().state == RobotState.IDLE
        assert b"PING\n" in fake.writes
    finally:
        link.close()


def test_read_failure_closes_stale_port_and_reconnects(monkeypatch) -> None:
    first = FakeSerial()
    second = FakeSerial()
    factory = SerialFactory([first, second])
    install_fake_serial(monkeypatch, factory)
    link = SerialRobotLink("COM5", reconnect_interval_seconds=0.01)

    link.connect()
    try:
        wait_until(lambda: link.status().connected)
        first.fail_reads.set()
        wait_until(lambda: first.is_open is False)
        wait_until(lambda: factory.calls >= 2 and link.status().connected)
        assert second.is_open is True
    finally:
        link.close()


def test_write_failure_is_not_reported_as_a_successful_stop(monkeypatch) -> None:
    fake = FakeSerial()
    factory = SerialFactory([fake, FileNotFoundError("gone")])
    install_fake_serial(monkeypatch, factory)
    link = SerialRobotLink("COM5", reconnect_interval_seconds=0.01)

    link.connect()
    try:
        wait_until(lambda: link.status().connected)
        fake.fail_writes = True
        accepted, message = link.stop()

        assert accepted is False
        assert message == "停止指令发送失败"
        wait_until(lambda: link.status().connected is False)
        assert "串口" in (link.status().error or "")
        assert fake.is_open is False
    finally:
        link.close()


def test_offline_command_fails_without_switching_to_simulation(monkeypatch) -> None:
    factory = SerialFactory([FileNotFoundError("missing")])
    install_fake_serial(monkeypatch, factory)
    link = SerialRobotLink("COM5", reconnect_interval_seconds=0.01)

    link.connect()
    try:
        wait_until(lambda: factory.calls >= 1)
        accepted, message = link.start("CARDIOLOGY")
        assert accepted is False
        assert message == "出发指令发送失败"
        assert link.status().mode == "hardware"
        assert link.status().connected is False
    finally:
        link.close()


def test_hardware_mode_never_falls_back_to_mock_robot() -> None:
    controller = build_robot_controller(
        Settings(mode="hardware", robot_port="COM5")
    )

    assert isinstance(controller, SerialRobotLink)
    assert controller.mode == "hardware"


def test_close_stops_workers_and_releases_the_port(monkeypatch) -> None:
    fake = FakeSerial()
    factory = SerialFactory([fake])
    install_fake_serial(monkeypatch, factory)
    link = SerialRobotLink("COM5", reconnect_interval_seconds=0.01)

    link.connect()
    wait_until(lambda: link.status().connected)
    link.close()

    assert fake.is_open is False
    assert link.status().connected is False
    assert link.worker_alive is False
