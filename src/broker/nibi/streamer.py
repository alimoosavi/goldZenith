"""Live Nibi SignalR streamer — asyncio + aiohttp, multiplexed over one hub.

One `NibiStreamer` opens a single WebSocket to the Nibi SignalR hub,
performs the JSON-protocol handshake by hand (no signalrcore), POSTs
**the full ISIN list** to the REST `SubscribeInstrument` endpoint in a
single call, then runs two concurrent coroutines:

  - message loop      — `async for` over `aiohttp.ClientWebSocketResponse`
  - heartbeat loop    — sends `{"type": 6}\\x1e` every `heartbeat_interval` s

Every incoming BL payload carries an `instrumentId` field, which the
streamer uses to route the event onto the correct per-ISIN Redis stream
(`nibi:{isin}:orderbook`).

`run()` is blocking — it wraps `asyncio.run(_run_async())` — and `stop()`
is callable from any thread; it signals an `asyncio.Event` via
`loop.call_soon_threadsafe`. The outer loop reconnects after
`reconnect_delay` whenever `_connect_and_stream` returns (server close,
network error, exception); it exits cleanly only when `stop()` fires.
There is **no BL-staleness watchdog** — silence isn't treated as failure,
so quiet periods (off-hours, illiquid books) don't trigger reconnects.

`_subscribe` and `emit_bl` remain synchronous (they call `requests` and
the sync redis-py client respectively) and are dispatched off the event
loop via `run_in_executor`.

Multiplexing rationale: the broker auth token has a cap on the number
of concurrent hub connections. Per-connection batch size is configured
by `config.nibi_instruments_per_connection`; callers chunk the full
registry into batches of that size and spawn one `NibiStreamer` per
chunk.
"""

from __future__ import annotations

import asyncio
import json
import ssl
from typing import Any, Callable

import aiohttp
import requests

from redis_manager import RedisManager
from settings import config

from ..base_streamer import BaseStreamer

CONNECTION_ID_EVENT: str = "ConnectionId"
EVENT_BL: str = "BL"

# SignalR JSON protocol: a ping frame (type 6) terminated by U+001E.
HEARTBEAT_SIGNAL_MESSAGE: dict = {"type": 6}
HEARTBEAT_INTERVAL_SECONDS: float = 20.0

_RECORD_SEPARATOR: str = "\x1e"

MessageHandler = Callable[[str, list], None]


class NibiStreamer(BaseStreamer):
    """Live multi-ISIN streamer driven by one Nibi SignalR hub connection.

        from redis_manager import RedisManager
        from broker.nibi import NibiStreamer

        rm = RedisManager(uri=config.redis_uri, port=config.redis_port)
        rm.ping()
        NibiStreamer(
            isins=["IRTKMOFD0001", "IRTKROBA0001", "IRTKZARA0001"],
            redis_manager=rm,
        ).run()

    Auth defaults to `config.nibi_auth_token` / `config.nibi_cookie`;
    pass `auth_token=` / `cookie=` to override. `on_message` receives
    `(event, payload)` after each successful Redis publish.
    """

    def __init__(
        self,
        *,
        isins: list[str],
        redis_manager: RedisManager,
        auth_token: str | None = None,
        cookie: str | None = None,
        supervisor_interval: float = 2.0,
        reconnect_delay: float = 3.0,
        heartbeat_interval: float = HEARTBEAT_INTERVAL_SECONDS,
        stream_maxlen: int | None = 10_000,
        on_message: MessageHandler | None = None,
    ) -> None:
        super().__init__(isins=isins, redis_manager=redis_manager, stream_maxlen=stream_maxlen)

        token = auth_token if auth_token is not None else config.nibi_auth_token
        if not token:
            raise ValueError("NibiStreamer: NIBI_AUTH_TOKEN is empty")
        if not config.nibi_hub_url:
            raise ValueError("NibiStreamer: nibi_hub_url is empty")
        if not config.nibi_subscribe_url:
            raise ValueError("NibiStreamer: nibi_subscribe_url is empty")
        if heartbeat_interval <= 0:
            raise ValueError("NibiStreamer: heartbeat_interval must be > 0")

        self.hub_url: str = config.nibi_hub_url
        self.subscribe_url: str = config.nibi_subscribe_url
        self.auth_token: str = token
        self.cookie: str = cookie if cookie is not None else config.nibi_cookie
        # `supervisor_interval` is unused (the async core has no polling
        # supervisor); kept on the surface for backwards compatibility.
        # `reconnect_delay` gates the outer reconnect loop in `_run_async`.
        self.supervisor_interval = supervisor_interval
        self.reconnect_delay = reconnect_delay
        self.heartbeat_interval = heartbeat_interval

        self._on_message_user = on_message
        self._connection_id: str | None = None
        # Loop + stop-event are created when `_run_async` enters; `stop()`
        # may be called from any thread and dispatches via
        # `loop.call_soon_threadsafe`.
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop_event: asyncio.Event | None = None

    # ── stream-key contract ──────────────────────────────────────────────

    @classmethod
    def orderbook_stream_key(cls, isin: str) -> str:
        return f"nibi:{isin}:orderbook"

    # ── public lifecycle ─────────────────────────────────────────────────

    def run(self) -> None:
        """Blocking. Runs the asyncio loop until `stop()` is called."""
        try:
            asyncio.run(self._run_async())
        except KeyboardInterrupt:
            self._log("main", "interrupted, stopping")

    def stop(self) -> None:
        """Thread-safe shutdown signal. May be called from any thread."""
        loop = self._loop
        event = self._stop_event
        if loop is None or event is None:
            return
        loop.call_soon_threadsafe(event.set)

    # ── async core ───────────────────────────────────────────────────────

    async def _run_async(self) -> None:
        """Reconnect loop. Each iteration runs one `_connect_and_stream`
        attempt and, if it returns for any reason other than `stop()`,
        waits `reconnect_delay` before trying again. Exits when
        `_stop_event` fires."""
        self._loop = asyncio.get_running_loop()
        self._stop_event = asyncio.Event()
        while not self._stop_event.is_set():
            try:
                await self._connect_and_stream()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._log("connection error", f"{type(exc).__name__}: {exc}")
            if self._stop_event.is_set():
                break
            self._log("reconnect", f"in {self.reconnect_delay}s")
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=self.reconnect_delay,
                )
                break  # stop_event fired during the wait
            except asyncio.TimeoutError:
                pass  # reconnect_delay elapsed; loop and reconnect

    async def _connect_and_stream(self) -> None:
        url = f"{self.hub_url}/?access_token={self.auth_token}"
        # The broker's cert isn't on the local trust store — same as the
        # `verify=False` we use for the REST subscribe call.
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE

        timeout = aiohttp.ClientTimeout(total=None, sock_connect=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.ws_connect(
                url, ssl=ssl_ctx, heartbeat=None, autoping=False,
            ) as ws:
                self._log("on_open", "websocket connected, sending handshake")
                await ws.send_str(
                    json.dumps({"protocol": "json", "version": 1}) + _RECORD_SEPARATOR
                )

                stop_task = asyncio.create_task(self._stop_event.wait())
                msg_task = asyncio.create_task(self._message_loop(ws))
                heartbeat_task = asyncio.create_task(self._heartbeat_loop(ws))
                tasks = [stop_task, msg_task, heartbeat_task]

                try:
                    done, pending = await asyncio.wait(
                        tasks, return_when=asyncio.FIRST_COMPLETED,
                    )
                    for t in pending:
                        t.cancel()
                    for t in pending:
                        try:
                            await t
                        except (asyncio.CancelledError, Exception):
                            pass
                    # Surface non-stop task exceptions so the outer
                    # reconnect loop can log and back off.
                    for t in done:
                        if t is stop_task:
                            continue
                        exc = t.exception()
                        if exc is not None:
                            raise exc
                finally:
                    if not ws.closed:
                        await ws.close()

    # ── frame routing ────────────────────────────────────────────────────

    async def _message_loop(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                # A single TEXT message can contain multiple `\x1e`-
                # terminated frames; split and dispatch each.
                for frame in msg.data.split(_RECORD_SEPARATOR):
                    if not frame:
                        continue
                    await self._handle_frame(frame)
            elif msg.type == aiohttp.WSMsgType.ERROR:
                self._log("signalr error", str(ws.exception()))
                return
            elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSING):
                self._log("ws closed", f"type={msg.type.name}")
                return

    async def _handle_frame(self, frame_text: str) -> None:
        try:
            data = json.loads(frame_text)
        except Exception as exc:
            self._log("frame parse error", str(exc))
            return
        # Handshake response has no `type` field — `{}` on success or
        # `{"error":"..."}` on failure.
        if "type" not in data:
            err = data.get("error")
            if err:
                self._log("handshake error", str(err))
            else:
                self._log("handshake", "completed")
            return
        msg_type = data["type"]
        if msg_type == 1:  # Invocation
            target = data.get("target")
            args = data.get("arguments") or []
            if target == CONNECTION_ID_EVENT:
                await self._on_connection_id(args)
            elif target == EVENT_BL:
                await self._on_bl(args)
            # ignore other targets
        elif msg_type == 6:  # Ping
            return
        elif msg_type == 7:  # Close
            self._log("close frame", str(data))
            return
        # Types 2-5 (StreamItem/Completion/StreamInvocation/CancelInvocation)
        # don't apply to the BL hub; safely ignored.

    async def _on_connection_id(self, args: list) -> None:
        if not args or not args[0]:
            self._log("ConnectionId", "empty payload")
            return
        cid = str(args[0])
        self._connection_id = cid
        self._log("ConnectionId", f"received {cid}")
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._subscribe, cid)
        except Exception as exc:
            self._log("subscribe failed", str(exc))

    async def _on_bl(self, args: list) -> None:
        # `args` is the list of arguments to the hub invocation — the
        # same shape `_isin_of` expects (a `[envelope_dict]` list).
        message = args
        isin = self._isin_of(message)
        if isin is None:
            self._log("emit_bl error", "could not resolve instrumentId from BL message")
            return
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(None, self.emit_bl, isin, message)
        except Exception as exc:
            self._log("emit_bl error", str(exc))
            return
        if self._on_message_user is not None:
            try:
                await loop.run_in_executor(
                    None, self._on_message_user, self.EVENT_BL, message,
                )
            except Exception as exc:
                self._log("on_message error", str(exc))

    @staticmethod
    def _isin_of(message: Any) -> str | None:
        """Pull `instrumentId` out of a Nibi BL outer envelope.

        Envelope shape: `[{"id": ..., "instrumentId": "<isin>", "data": [...]}]`.
        Returns `None` if the message doesn't match — that's logged by
        the caller, not raised, so one malformed event can't kill the
        message loop.
        """
        try:
            return str(message[0]["instrumentId"])
        except (IndexError, KeyError, TypeError):
            return None

    # ── concurrent coroutines ────────────────────────────────────────────

    async def _heartbeat_loop(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        payload = json.dumps(HEARTBEAT_SIGNAL_MESSAGE) + _RECORD_SEPARATOR
        self._log(
            "heartbeat",
            f"sending {HEARTBEAT_SIGNAL_MESSAGE} every {self.heartbeat_interval}s",
        )
        while not ws.closed:
            try:
                await asyncio.sleep(self.heartbeat_interval)
            except asyncio.CancelledError:
                raise
            if ws.closed:
                return
            try:
                await ws.send_str(payload)
            except Exception as exc:
                self._log("heartbeat failed", str(exc))
                return

    # ── REST subscribe (sync) ────────────────────────────────────────────

    def _subscribe(self, connection_id: str) -> None:
        """Sync REST POST registering this hub's `connection_id` for the
        full ISIN batch. Called via `run_in_executor` from the async
        message loop."""
        headers = {
            "Authorization": self.auth_token,
            "Cookie": self.cookie,
            "Content-Type": "application/json",
        }
        r = requests.post(
            f"{self.subscribe_url}/api/Subscribes/SubscribeInstrument",
            headers=headers,
            json={"ConnectionId": connection_id, "InstrumentIds": list(self.isins)},
            verify=False,
            timeout=10,
        )
        self._log(
            "subscribe instruments",
            f"HTTP {r.status_code} for {len(self.isins)} isin(s)",
        )
