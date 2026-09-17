from __future__ import annotations

import threading
from datetime import UTC, datetime
from typing import Any, Protocol

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
    heartbeat_interval_seconds = 0.5

    def __init__(
        self,
        port: str,
        baud: int = 115200,
        reconnect_interval_seconds: float = 2.0,
    ) -> None:
        self.port = port
        self.baud = baud
        self.reconnect_interval_seconds = reconnect_interval_seconds
        self._serial: Any | None = None
        self._worker: threading.Thread | None = None
        self._heartbeat: threading.Thread | None = None
        self._shutdown = threading.Event()
        self._state_lock = threading.RLock()
        self._write_lock = threading.Lock()
        self._connect_lock = threading.Lock()
        self._snapshot = RobotSnapshot(
            mode=self.mode,
            connected=False,
            state=RobotState.ERROR,
            error=self._waiting_message(),
            updated_at=datetime.now(UTC),
        )

    @property
    def worker_alive(self) -> bool:
        with self._state_lock:
            worker = self._worker
            heartbeat = self._heartbeat
        return bool(
            (worker and worker.is_alive())
            or (heartbeat and heartbeat.is_alive())
        )

    def connect(self) -> None:
        """Start connection management without waiting for Windows to open the port."""
        with self._state_lock:
            if self._worker is not None and not self._shutdown.is_set():
                return
            self._shutdown.clear()
            self._snapshot = RobotSnapshot(
                mode=self.mode,
                connected=False,
                state=RobotState.ERROR,
                error=self._waiting_message(),
                updated_at=datetime.now(UTC),
            )
            worker = threading.Thread(
                target=self._connection_loop,
                name="yinban-serial-connection",
                daemon=True,
            )
            heartbeat = threading.Thread(
                target=self._heartbeat_loop,
                name="yinban-serial-heartbeat",
                daemon=True,
            )
            self._worker = worker
            self._heartbeat = heartbeat
        worker.start()
        heartbeat.start()

    def close(self) -> None:
        self._shutdown.set()
        with self._state_lock:
            connection = self._serial
            self._serial = None
            worker = self._worker
            heartbeat = self._heartbeat
            previous_route = self._snapshot.route_id
            self._snapshot = RobotSnapshot(
                mode=self.mode,
                connected=False,
                state=RobotState.ERROR,
                route_id=previous_route,
                error="机器人连接服务已停止",
                updated_at=datetime.now(UTC),
            )
        self._close_connection(connection)
        for thread in (worker, heartbeat):
            if thread and thread is not threading.current_thread() and thread.is_alive():
                thread.join(timeout=1)
        with self._state_lock:
            if self._worker is worker:
                self._worker = None
            if self._heartbeat is heartbeat:
                self._heartbeat = None

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
        # This lock never protects serial I/O, so the API stays responsive even
        # if a Windows Bluetooth driver stalls during open, read, or write.
        with self._state_lock:
            return self._snapshot

    def _waiting_message(self) -> str:
        if not self.port:
            return "未配置机器人串口，无法连接真实硬件"
        return f"机器人离线，正在重连 {self.port}"

    def _current_connection(self) -> Any | None:
        with self._state_lock:
            return self._serial

    def _connection_loop(self) -> None:
        while not self._shutdown.is_set():
            connection = self._current_connection()
            if connection is None:
                self._attempt_connection()
                connection = self._current_connection()
                if connection is None:
                    self._shutdown.wait(self.reconnect_interval_seconds)
                    continue
            try:
                raw = connection.readline()
                if not raw:
                    continue
                event = parse_event(raw.decode("utf-8", errors="replace"))
                with self._state_lock:
                    if self._serial is not connection:
                        continue
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
                if not self._shutdown.is_set():
                    self._mark_disconnected(
                        f"串口读取失败：{exc}；正在重连",
                        connection,
                    )

    def _attempt_connection(self) -> None:
        if not self.port:
            self._set_offline(self._waiting_message())
            return
        if not self._connect_lock.acquire(blocking=False):
            return
        candidate = None
        try:
            if self._shutdown.is_set() or self._current_connection() is not None:
                return
            self._set_offline(f"正在连接机器人串口 {self.port}")
            try:
                import serial

                candidate = serial.Serial(
                    self.port,
                    self.baud,
                    timeout=0.2,
                    write_timeout=0.5,
                )
            except Exception as exc:
                self._set_offline(
                    f"连接串口 {self.port} 失败：{exc}；正在重连"
                )
                return
            if self._shutdown.is_set():
                self._close_connection(candidate)
                return
            with self._state_lock:
                if self._serial is not None:
                    already_connected = True
                else:
                    already_connected = False
                    self._serial = candidate
                    self._snapshot = RobotSnapshot(
                        mode=self.mode,
                        connected=True,
                        state=RobotState.IDLE,
                        updated_at=datetime.now(UTC),
                    )
            if already_connected:
                self._close_connection(candidate)
                return
            self._write("PING", expected_connection=candidate)
        finally:
            self._connect_lock.release()

    def _write(
        self,
        command: str,
        value: str | None = None,
        *,
        expected_connection: Any | None = None,
    ) -> bool:
        with self._state_lock:
            connection = self._serial
        if connection is None or (
            expected_connection is not None and connection is not expected_connection
        ):
            self._set_offline(self._waiting_message())
            return False

        try:
            if not connection.is_open:
                raise ConnectionError("串口句柄已经关闭")
            with self._write_lock:
                with self._state_lock:
                    if self._serial is not connection:
                        return False
                connection.write(encode_command(command, value))
            return True
        except Exception as exc:
            self._mark_disconnected(
                f"串口写入失败：{exc}；正在重连",
                connection,
            )
            return False

    def _set_offline(self, error: str) -> None:
        with self._state_lock:
            if self._serial is not None:
                return
            previous_route = self._snapshot.route_id
            self._snapshot = RobotSnapshot(
                mode=self.mode,
                connected=False,
                state=RobotState.ERROR,
                route_id=previous_route,
                error=error,
                updated_at=datetime.now(UTC),
            )

    def _mark_disconnected(self, error: str, connection: Any) -> None:
        with self._state_lock:
            if self._serial is not connection:
                return
            self._serial = None
            previous_route = self._snapshot.route_id
            self._snapshot = RobotSnapshot(
                mode=self.mode,
                connected=False,
                state=RobotState.ERROR,
                route_id=previous_route,
                error=error,
                updated_at=datetime.now(UTC),
            )
        self._close_connection(connection)

    @staticmethod
    def _close_connection(connection: Any | None) -> None:
        if connection is None:
            return
        try:
            connection.close()
        except Exception:
            pass

    def _heartbeat_loop(self) -> None:
        while not self._shutdown.wait(self.heartbeat_interval_seconds):
            if self._current_connection() is not None:
                self._write("PING")


def build_robot_controller(settings: Settings) -> RobotController:
    if settings.mode == "hardware":
        return SerialRobotLink(settings.robot_port, settings.robot_baud)
    if settings.mode == "auto" and settings.robot_port:
        return SerialRobotLink(settings.robot_port, settings.robot_baud)
    return MockRobot()
