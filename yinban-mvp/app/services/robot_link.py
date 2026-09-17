from __future__ import annotations

import threading
from datetime import UTC, datetime
from typing import Any, Protocol

from app.config import Settings
from app.core.data_loader import load_json
from app.services.mock_robot import MockRobot
from app.services.physical_routes import PhysicalRouteCatalog
from app.services.robot_protocol import (
    RobotSnapshot,
    RobotState,
    encode_command,
    encode_run_command,
    parse_event,
)


class RobotController(Protocol):
    mode: str

    def connect(self) -> None: ...

    def close(self) -> None: ...

    def start(self, route_id: str, step_count: int = 2) -> tuple[bool, str]: ...

    def return_to_start(self, route_id: str) -> tuple[bool, str]: ...

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
        physical_routes: PhysicalRouteCatalog | None = None,
        reconnect_interval_seconds: float = 2.0,
    ) -> None:
        self.port = port
        self.baud = baud
        self.reconnect_interval_seconds = reconnect_interval_seconds
        self._routes = physical_routes or PhysicalRouteCatalog(
            load_json("physical_routes.json")
        )
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
            needs_reset=True,
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
                needs_reset=True,
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
                needs_reset=True,
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
        normalized = route_id.strip().upper()
        if not self._routes.supports(normalized):
            return False, "该实体路线尚未实现"
        with self._state_lock:
            snapshot = self._snapshot
        if not snapshot.connected:
            return False, "出发指令发送失败"
        if (
            snapshot.state != RobotState.IDLE
            or snapshot.needs_reset
            or snapshot.location_id != self._routes.start_location_id
        ):
            return False, "小车不在已确认的固定起点，请先归位并复位"
        actions = self._routes.actions_for_mission(normalized)
        accepted = self._write_run(normalized, actions)
        return accepted, "已发送出发指令" if accepted else "出发指令发送失败"

    def return_to_start(self, route_id: str) -> tuple[bool, str]:
        normalized = route_id.strip().upper()
        if not self._routes.supports(normalized):
            return False, "该实体返程路线尚未实现"
        route = self._routes.get(normalized)
        with self._state_lock:
            snapshot = self._snapshot
        if not snapshot.connected:
            return False, "返程指令发送失败"
        if (
            snapshot.state != RobotState.ARRIVED
            or snapshot.needs_reset
            or snapshot.location_id != route.location_id
            or snapshot.return_route_id != normalized
        ):
            return False, "当前位置与返程路线不匹配，不能启动返程"
        mission_id = self._routes.return_mission_id(normalized)
        actions = self._routes.actions_for_mission(mission_id)
        accepted = self._write_run(mission_id, actions)
        return accepted, "已发送返程指令" if accepted else "返程指令发送失败"

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
                    self._snapshot = self._snapshot_for_event(event)
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
                        state=RobotState.NEEDS_RESET,
                        needs_reset=True,
                        error="通信已恢复，请将小车放回固定起点并确认归位",
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
        return self._write_bytes(
            encode_command(command, value),
            expected_connection=expected_connection,
        )

    def _write_run(self, mission_id: str, actions: tuple[str, ...]) -> bool:
        return self._write_bytes(encode_run_command(mission_id, actions))

    def _write_bytes(
        self,
        payload: bytes,
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
                connection.write(payload)
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
                mission_direction=self._snapshot.mission_direction,
                node_index=self._snapshot.node_index,
                location_id=None,
                needs_reset=True,
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
                mission_direction=self._snapshot.mission_direction,
                node_index=self._snapshot.node_index,
                location_id=None,
                needs_reset=True,
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

    def _snapshot_for_event(self, event) -> RobotSnapshot:
        previous = self._snapshot
        now = datetime.now(UTC)
        if event.location_id == self._routes.start_location_id:
            return RobotSnapshot(
                mode=self.mode,
                connected=True,
                state=RobotState.IDLE,
                location_id=self._routes.start_location_id,
                needs_reset=False,
                updated_at=now,
            )
        if event.needs_reset:
            return RobotSnapshot(
                mode=self.mode,
                connected=True,
                state=event.state,
                route_id=event.route_id or previous.route_id,
                mission_direction=previous.mission_direction,
                node_index=event.node_index or previous.node_index,
                needs_reset=True,
                error=event.error,
                updated_at=now,
            )
        if event.state == RobotState.IDLE:
            return RobotSnapshot(
                mode=self.mode,
                connected=True,
                state=RobotState.NEEDS_RESET,
                needs_reset=True,
                error="固件尚未确认固定起点，请人工归位并复位",
                updated_at=now,
            )

        route_id = event.route_id or previous.route_id
        direction = previous.mission_direction
        if event.route_id:
            direction = "return" if event.route_id.startswith("RETURN_") else "outbound"
        node_index = event.node_index if event.node_index is not None else previous.node_index
        location_id = previous.location_id
        return_route_id = previous.return_route_id
        if event.state in {RobotState.MOVING, RobotState.TURNING}:
            location_id = None
            return_route_id = None
        if event.state == RobotState.ARRIVED and event.route_id:
            try:
                location_id = self._routes.location_for_arrival(event.route_id)
                base_route_id = self._routes.base_route_id(event.route_id)
            except KeyError:
                return RobotSnapshot(
                    mode=self.mode,
                    connected=True,
                    state=RobotState.ERROR,
                    route_id=event.route_id,
                    needs_reset=True,
                    error="固件返回了未知路线",
                    updated_at=now,
                )
            return_route_id = None if direction == "return" else base_route_id
        return RobotSnapshot(
            mode=self.mode,
            connected=True,
            state=event.state,
            route_id=route_id,
            distance_cm=event.distance_cm,
            error=event.error,
            mission_direction=direction,
            node_index=node_index,
            location_id=location_id,
            needs_reset=False,
            return_route_id=return_route_id,
            updated_at=now,
        )


def build_robot_controller(
    settings: Settings,
    physical_routes: PhysicalRouteCatalog | None = None,
) -> RobotController:
    routes = physical_routes or PhysicalRouteCatalog(load_json("physical_routes.json"))
    if settings.mode == "hardware":
        return SerialRobotLink(
            settings.robot_port, settings.robot_baud, physical_routes=routes
        )
    if settings.mode == "auto" and settings.robot_port:
        return SerialRobotLink(
            settings.robot_port, settings.robot_baud, physical_routes=routes
        )
    return MockRobot(physical_routes=routes)
