from __future__ import annotations

import threading
from datetime import UTC, datetime
from typing import Protocol

from app.config import Settings
from app.services.mock_robot import MockRobot
from app.services.robot_protocol import (
    RobotSnapshot,
    RobotState,
    encode_command,
    parse_event,
)


class RobotController(Protocol):
    mode: str

    def connect(self) -> None: ...

    def close(self) -> None: ...

    def start(self, route_id: str, step_count: int = 2) -> tuple[bool, str]: ...

    def stop(self) -> tuple[bool, str]: ...

    def resume(self) -> tuple[bool, str]: ...

    def reset(self) -> tuple[bool, str]: ...

    def status(self) -> RobotSnapshot: ...


class SerialRobotLink:
    mode = "hardware"

    def __init__(self, port: str, baud: int = 115200) -> None:
        self.port = port
        self.baud = baud
        self._serial = None
        self._reader: threading.Thread | None = None
        self._stop_reader = threading.Event()
        self._lock = threading.RLock()
        self._snapshot = RobotSnapshot(
            mode=self.mode,
            connected=False,
            state=RobotState.IDLE,
            error="尚未连接",
        )

    def connect(self) -> None:
        import serial

        with self._lock:
            if self._serial and self._serial.is_open:
                return
            self._serial = serial.Serial(self.port, self.baud, timeout=0.2)
            self._snapshot = RobotSnapshot(
                mode=self.mode,
                connected=True,
                state=RobotState.IDLE,
                updated_at=datetime.now(UTC),
            )
            self._stop_reader.clear()
            self._reader = threading.Thread(target=self._read_loop, daemon=True)
            self._reader.start()
            self._write("PING")

    def close(self) -> None:
        self._stop_reader.set()
        reader = self._reader
        if reader and reader.is_alive():
            reader.join(timeout=1)
        with self._lock:
            if self._serial:
                self._serial.close()
            self._serial = None

    def start(self, route_id: str, step_count: int = 2) -> tuple[bool, str]:
        if route_id != "CARDIOLOGY":
            return False, "该实体路线尚未实现"
        accepted = self._write("START", route_id)
        return accepted, "已发送出发指令" if accepted else "出发指令发送失败"

    def stop(self) -> tuple[bool, str]:
        accepted = self._write("STOP")
        return accepted, "已发送停止指令" if accepted else "停止指令发送失败"

    def resume(self) -> tuple[bool, str]:
        accepted = self._write("RESUME")
        return accepted, "已发送继续指令" if accepted else "继续指令发送失败"

    def reset(self) -> tuple[bool, str]:
        accepted = self._write("RESET")
        return accepted, "已发送复位指令" if accepted else "复位指令发送失败"

    def status(self) -> RobotSnapshot:
        with self._lock:
            return self._snapshot

    def _write(self, command: str, value: str | None = None) -> bool:
        with self._lock:
            if not self._serial or not self._serial.is_open:
                self._snapshot = RobotSnapshot(
                    mode=self.mode,
                    connected=False,
                    state=RobotState.ERROR,
                    error="串口未连接",
                    updated_at=datetime.now(UTC),
                )
                return False
            try:
                self._serial.write(encode_command(command, value))
                return True
            except Exception as exc:
                self._snapshot = RobotSnapshot(
                    mode=self.mode,
                    connected=False,
                    state=RobotState.ERROR,
                    error=f"串口写入失败：{exc}",
                    updated_at=datetime.now(UTC),
                )
                return False

    def _read_loop(self) -> None:
        while not self._stop_reader.is_set():
            try:
                raw = self._serial.readline()
                if not raw:
                    continue
                event = parse_event(raw.decode("utf-8", errors="replace"))
                with self._lock:
                    previous_route = self._snapshot.route_id
                    self._snapshot = RobotSnapshot(
                        mode=self.mode,
                        connected=True,
                        state=event.state,
                        route_id=event.route_id or previous_route,
                        distance_cm=event.distance_cm,
                        error=event.error,
                        updated_at=datetime.now(UTC),
                    )
            except ValueError:
                continue
            except Exception as exc:
                with self._lock:
                    self._snapshot = RobotSnapshot(
                        mode=self.mode,
                        connected=False,
                        state=RobotState.ERROR,
                        error=f"串口读取失败：{exc}",
                        updated_at=datetime.now(UTC),
                    )
                return


def build_robot_controller(settings: Settings) -> RobotController:
    if settings.mode in {"hardware", "auto"} and settings.robot_port:
        link = SerialRobotLink(settings.robot_port, settings.robot_baud)
        try:
            link.connect()
            return link
        except Exception as exc:
            mock = MockRobot()
            mock._error = f"真实串口不可用，已切换模拟模式：{exc}"
            return mock
    return MockRobot()
