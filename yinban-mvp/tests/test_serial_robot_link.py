from __future__ import annotations

import sys
import threading
import time
from types import SimpleNamespace

from app.services.robot_link import SerialRobotLink
from app.services.robot_protocol import RobotState


class FakeSerial:
    def __init__(self) -> None:
        self.is_open = True
        self.writes: list[bytes] = []
        self.fail_reads = threading.Event()
        self.fail_writes = False

    def write(self, payload: bytes) -> None:
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


def install_fake_serial(monkeypatch, fake: FakeSerial) -> None:
    serial_module = SimpleNamespace(Serial=lambda *args, **kwargs: fake)
    monkeypatch.setitem(sys.modules, "serial", serial_module)


def wait_until(predicate, timeout: float = 0.5) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    raise AssertionError("condition did not become true before timeout")


def test_hardware_link_sends_periodic_ping(monkeypatch) -> None:
    fake = FakeSerial()
    install_fake_serial(monkeypatch, fake)
    link = SerialRobotLink("COM5")
    link.heartbeat_interval_seconds = 0.02

    link.connect()
    try:
        wait_until(lambda: fake.writes.count(b"PING\n") >= 3)
        assert link.status().connected is True
    finally:
        link.close()


def test_read_failure_marks_link_disconnected_and_closes_port(monkeypatch) -> None:
    fake = FakeSerial()
    install_fake_serial(monkeypatch, fake)
    link = SerialRobotLink("COM5")

    link.connect()
    fake.fail_reads.set()
    wait_until(lambda: link.status().connected is False)

    snapshot = link.status()
    assert snapshot.state == RobotState.ERROR
    assert "串口读取失败" in (snapshot.error or "")
    assert fake.is_open is False
    link.close()


def test_write_failure_is_not_reported_as_a_successful_stop(monkeypatch) -> None:
    fake = FakeSerial()
    install_fake_serial(monkeypatch, fake)
    link = SerialRobotLink("COM5")

    link.connect()
    fake.fail_writes = True
    accepted, message = link.stop()

    assert accepted is False
    assert message == "停止指令发送失败"
    assert link.status().connected is False
    assert "串口写入失败" in (link.status().error or "")
    assert fake.is_open is False
    link.close()
