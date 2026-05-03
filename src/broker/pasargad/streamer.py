"""Live Pasargad SignalR streamer — emits BL events to a Redis stream.

`PasargadStreamer(isin=..., redis_manager=...)` opens a dedicated
websocket to the Pasargad SignalR hub for one ISIN, runs the
connection-id handshake + REST `SubscribeInstrument` POST, holds the
socket open with periodic SignalR pings, supervises reconnects, and
republishes every incoming BL payload onto `{isin}:orderbook`.

Pasargad-style handshake:

  1. Open WS at  wss://pasargad-signal.tsetab.ir/SignalHub/?id=<random>&access_token=<token>
     (`id` is signalrcore's transport id, NOT the application connection-id).
  2. signalrcore sends the JSON SignalR handshake `{"protocol":"json","version":1}\\x1e`.
  3. Server pushes a hub-method invocation back:
         {"type":1,"target":"ConnectionId","arguments":["<realConnectionId>"]}
     This is the connection-id we must use for REST subscribe calls.
  4. POST that id to  <PASARGAD_API_BASE_URL>/api/Subscribes/SubscribeInstrument
     with `{"ConnectionId": "<realConnectionId>", "InstrumentIds": ["<isin>"]}`.
  5. BL invocations (5-depth orderbook updates) start flowing.

We DO NOT enable signalrcore's built-in auto-reconnect: it would silently
re-open the socket without re-running our REST subscribe step, leaving
us with an open-but-silent feed. The supervisor loop in `run()` rebuilds
the hub end-to-end on disconnect; the fresh handshake re-fires the
`ConnectionId` event, which re-fires `_subscribe`.

The heartbeat thread sends `{"type":6}` (SignalR ping) on the underlying
websocket every `heartbeat_interval` seconds (default 60s) to keep the
broker's load-balancer from closing the socket during quiet periods.
"""

from __future__ import annotations

import json
import threading
from typing import Callable

import requests
from signalrcore.hub_connection_builder import HubConnectionBuilder

from redis_manager import RedisManager
from settings import config

from ..base_streamer import BaseStreamer

CONNECTION_ID_EVENT: str = "ConnectionId"

# SignalR JSON-protocol ping frame. Type 6 = Ping. Sent verbatim (followed by
# the record separator) so the broker's load balancer keeps the socket open
# even when the market is quiet.
HEARTBEAT_SIGNAL_MESSAGE: dict = {"type": 6}
HEARTBEAT_INTERVAL_SECONDS: float = 60.0

# SignalR JSON protocol terminates each frame with U+001E (record separator).
_RECORD_SEPARATOR: str = "\x1e"

MessageHandler = Callable[[str, list], None]


class PasargadStreamer(BaseStreamer):
    """Live single-ISIN streamer driven by the Pasargad SignalR hub.

        from redis_manager import RedisManager
        from broker.pasargad import PasargadStreamer
        from settings import config

        rm = RedisManager(uri=config.redis_uri, port=config.redis_port)
        rm.ping()
        PasargadStreamer(isin="IRTKMOFD0001", redis_manager=rm).run()

    Auth defaults to `config.pasargad_auth_token` / `config.pasargad_cookie`;
    pass `auth_token=` / `cookie=` to override (e.g. for a one-off session).
    `on_message` receives `(event, payload)` after each successful Redis
    publish — useful for in-process consumers that want a callback in
    addition to the Redis stream.
    """

    def __init__(
        self,
        *,
        isin: str,
        redis_manager: RedisManager,
        auth_token: str | None = None,
        cookie: str | None = None,
        supervisor_interval: float = 2.0,
        reconnect_delay: float = 3.0,
        heartbeat_interval: float = HEARTBEAT_INTERVAL_SECONDS,
        stream_maxlen: int | None = 10_000,
        on_message: MessageHandler | None = None,
    ) -> None:
        super().__init__(isin=isin, redis_manager=redis_manager, stream_maxlen=stream_maxlen)

        token = auth_token if auth_token is not None else config.pasargad_auth_token
        if not token:
            raise ValueError("PasargadStreamer: PASARGAD_AUTH_TOKEN is empty")
        if heartbeat_interval <= 0:
            raise ValueError("PasargadStreamer: heartbeat_interval must be > 0")

        self.hub_url: str = config.pasargad_signalr_url
        self.api_base_url: str = config.pasargad_api_base_url
        self.auth_token: str = token
        self.cookie: str = cookie if cookie is not None else config.pasargad_cookie
        self.supervisor_interval = supervisor_interval
        self.reconnect_delay = reconnect_delay
        self.heartbeat_interval = heartbeat_interval

        self._on_message_user = on_message
        self._hub = None
        self._connection_id: str | None = None

        self._run_stop = threading.Event()
        self._heartbeat_stop = threading.Event()
        self._heartbeat_thread: threading.Thread | None = None

    # ── hub plumbing ─────────────────────────────────────────────────────

    def _build_hub(self):
        # Push signalrcore's built-in keep-alive past our heartbeat interval so
        # our heartbeat thread is what actually drives pings on the wire.
        options = {
            "verify_ssl": False,
            "keep_alive_interval": self.heartbeat_interval + 60,
        }
        hub = (
            HubConnectionBuilder()
            .with_url(
                f"{self.hub_url}/?access_token={self.auth_token}",
                options=options,
            )
            .build()
        )
        hub.on(self.EVENT_BL, self._on_bl)
        hub.on(CONNECTION_ID_EVENT, self._on_connection_id)
        hub.on_open(self._on_connected)
        hub.on_error(self._on_error)
        return hub

    def _on_connected(self) -> None:
        self._log("on_open", "websocket connected, awaiting ConnectionId")

    def _on_connection_id(self, message) -> None:
        if not message or not message[0]:
            self._log("ConnectionId", "empty payload")
            return
        cid = message[0]
        self._connection_id = cid
        self._log("ConnectionId", f"received {cid}")
        try:
            self._subscribe(cid)
        except Exception as exc:
            self._log("subscribe failed", str(exc))

    def _on_error(self, error) -> None:
        self._log("signalr error", str(error))

    def _on_bl(self, message) -> None:
        try:
            self.emit_bl(message)
        except Exception as exc:
            self._log("emit_bl error", str(exc))
            return
        if self._on_message_user is not None:
            try:
                self._on_message_user(self.EVENT_BL, message)
            except Exception as exc:
                self._log("on_message error", str(exc))

    # ── heartbeat ────────────────────────────────────────────────────────

    def _start_heartbeat(self) -> None:
        self._heartbeat_stop.clear()
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            name=f"pasargad-heartbeat-{self.isin}",
            daemon=True,
        )
        self._heartbeat_thread.start()
        self._log(
            "heartbeat",
            f"sending {HEARTBEAT_SIGNAL_MESSAGE} every {self.heartbeat_interval}s",
        )

    def _heartbeat_loop(self) -> None:
        while not self._heartbeat_stop.wait(self.heartbeat_interval):
            self._send_heartbeat()

    def _send_heartbeat(self) -> None:
        hub = self._hub
        if hub is None:
            return
        try:
            ws = hub.transport._ws
        except AttributeError:
            return
        if ws is None:
            return
        payload = json.dumps(HEARTBEAT_SIGNAL_MESSAGE) + _RECORD_SEPARATOR
        try:
            ws.send(payload)
        except Exception as exc:
            self._log("heartbeat failed", str(exc))

    def _stop_heartbeat(self) -> None:
        if self._heartbeat_thread is None:
            return
        self._heartbeat_stop.set()
        self._heartbeat_thread.join(timeout=2)
        self._heartbeat_thread = None

    # ── REST subscribe ───────────────────────────────────────────────────

    def _subscribe(self, connection_id: str) -> None:
        headers = {
            "Authorization": self.auth_token,
            "Cookie": self.cookie,
            "Content-Type": "application/json",
        }
        r = requests.post(
            f"{self.api_base_url}/api/Subscribes/SubscribeInstrument",
            headers=headers,
            json={"ConnectionId": connection_id, "InstrumentIds": [self.isin]},
            verify=False,
            timeout=10,
        )
        self._log("subscribe instruments", f"HTTP {r.status_code}")

    # ── supervisor ───────────────────────────────────────────────────────

    def _state(self) -> str:
        try:
            return self._hub.transport.state.name.lower()
        except AttributeError:
            return "unknown"

    def run(self) -> None:
        """Blocking. Runs until `stop()` is called or KeyboardInterrupt fires
        (the latter only in main-thread direct use; thread runners get
        signalled via `stop()` instead)."""
        self._run_stop.clear()
        self._start_heartbeat()
        try:
            self._hub = self._build_hub()
            self._hub.start()
            while not self._run_stop.wait(self.supervisor_interval):
                if self._state() == "disconnected":
                    self._log("supervisor", "transport disconnected, rebuilding")
                    self._safe_stop_hub()
                    if self._run_stop.wait(self.reconnect_delay):
                        break
                    self._connection_id = None
                    self._hub = self._build_hub()
                    self._hub.start()
        except KeyboardInterrupt:
            self._log("main", "interrupted, stopping")
        finally:
            self._safe_stop_hub()
            self._stop_heartbeat()

    def stop(self) -> None:
        self._run_stop.set()

    def _safe_stop_hub(self) -> None:
        if self._hub is None:
            return
        try:
            self._hub.stop()
        except Exception as exc:
            self._log("stop error", str(exc))
        finally:
            self._hub = None
