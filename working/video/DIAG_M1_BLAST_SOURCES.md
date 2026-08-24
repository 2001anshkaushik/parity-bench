# RR default blast — source-only findings (2026-08-24, no fix proposed, nothing run)

Scope: (a)-(e) as ordered. Pinned sources: `engine/rocketride/*` (SDK 1.3.0 both
venvs, operator-verified), `engine/ai/*` (server), `working/video/driver_video.py`,
`working/video/probe/probe_m1_concurrency.py`.

## (a) The error string and every path to it
`ConnectionError('Could not send request')` has exactly ONE mint site:
`dap_client.py:229`, inside `except Exception:` around `await self._send(message)`
(request() body, 224-229). `_send` (dap_client.py:90) is a pass-through to
`TransportWebSocket.send` (transport_websocket.py:536). So the string means: THE
TRANSPORT-LEVEL SEND RAISED, cause discarded, unchained. Paths that reach it
BEFORE any payload byte hits the socket:
  * transport send guard 1: `not self.is_connected()` -> ConnectionError
    ('WebSocket not connected...') — fires with zero bytes sent.
  * transport send guard 2: `not self._websocket` -> 'WebSocket connection lost
    before send' — zero bytes.
  * `bytes(arguments['data'])` / header concat MemoryError — zero bytes.
  * any exception during the buffered write — bytes may be QUEUED, not on wire.
So YES: it can fire with nothing on the socket, and once the shared connection
is dead, every subsequent send mints this string at guard 1 instantly.

The SECOND string, `ConnectionError('Connection closed')` ("Future exception was
never retrieved"): `dap_client.on_disconnected` (120-142) — on transport
disconnect it fails ALL pending request futures with `ConnectionError(reason)`.
One connection death therefore produces BOTH signatures at the same instant:
in-flight requests (awaiting their future) get 'Connection closed'; anything
still trying to send gets 'Could not send request'. The 16 done_ns within ~10ms
is the on_disconnected loop sweeping the pending map — ONE event, not 16.

## (b) The two send paths, diffed
SAME in both: one RocketRideClient == ONE DAPClient == ONE TransportWebSocket ==
one websocket shared by all 16 concurrent sends (per-seq future multiplexing;
no lock anywhere in the path); pure asyncio on one event loop, no thread pool
for sends; `use(filepath=<fresh uuid5 pipe>, ttl=0)`; no threads kwarg (default
posture / probe alike); send() = pipe/open/write/close per video
(mixins/data.py:405); pipe.write sends the WHOLE buffer as ONE DAP request
(data.py:208-245 — no chunking; one ~248MB binary websocket message per video).
DIFFERENT:
  1. BLOB ACQUISITION — the decisive one. Driver `one(row)`
     (driver_video.py:1197-1201): `blob = read_bytes()` runs SYNCHRONOUSLY ON
     THE EVENT LOOP, BEFORE the semaphore, and gather launches ALL 168 row
     tasks (1254) — so rows 17..168 each execute their 248MB read while the
     first 16 sends are in flight. The probe reads ONE file ONCE before any
     send; during its 16 sends the loop never touches the disk.
  2. Driver also computes `sha256_bytes(blob)` per admitted send (1208) —
     another ~0.5-1s of synchronous loop time per send.
  3. Driver: 16 DISTINCT files (~150-250MB each) held by 16 tasks + every
     pre-read row behind them; probe: one 248MB bytes object reused.
  4. Driver's client already served warm-up on the same connection (see d);
     probe's client is fresh per point.
  5. Probe wraps _send/transport.send with truth taps (logging only).

## (c) Deadlines and limits, named
  * `CONST_SOCKET_TIMEOUT = 180` (rocketride/core/constants.py:75) — used for
    connect/close and the transport send's TimeoutError branch text; nothing in
    the send path I can find wraps the actual `websocket.send` in wait_for.
  * `CONST_WS_PING_INTERVAL = 15`, `CONST_WS_PING_TIMEOUT = 300`
    (constants.py:79,84) — used by BOTH sides: client at websockets.connect
    (transport_websocket.py:378) and the SERVER's uvicorn at
    ai/web/server.py:458-460, which imports the same constants from rocketride
    (server.py:68). Port 5565 IS this uvicorn server (ai/constants.py:72).
  * `CONST_WEB_WS_MAX_SIZE = 250MB` (ai/constants.py:74) server-side;
    `max_size=250MB` client-side (transport_websocket.py:385). 248MB messages
    fit — sequential warm-up proves it end to end.
  * `request_timeout`: DEFAULT NONE (client.py:151) — no per-request deadline.
  * **No constant equals ~220s.** Neither 180, 15+300=315, nor 250MB explains
    219.63s. What DOES: the arithmetic of (b)(1) — 16 staggered reads = 22.6s
    (measured, 1.41s/read), then rows 17..168 = 152 further synchronous reads;
    219.63 - 22.6 = 197.0s; 197.0/152 = 1.30s/read, page-cache-plausibly the
    same disk. Under that reading the loop is near-continuously blocked from
    t≈23s to t≈220s: no pongs answered, no drain progress, no receive
    processing; the connection's death is DISCOVERED (or caused) at the moment
    the loop unblocks, and on_disconnected sweeps all 16 futures at once —
    matching the ~10ms spread and the banner-only engine log (the writes never
    left the client's buffer, so the server had nothing to log).
  * `CONST_DATA_PIPE_TIMEOUT = 60.0` (ai/constants.py:79, "seconds of
    inactivity before pipe is considered zombie") — engine-side pipe reaper.
    This is the near-certain source of the PROBE's failure mode
    (`PipeException('Write pipe with id N not found')`, uniform ~92.66s): 16
    pipes open quickly, writes serialize behind ~248MB transfers on the one
    connection, the pipes whose write could not start within the zombie window
    are reaped, the late write references a dead id. Consistent with the
    probe's 10/16: app-layer receipt (engine SAW those requests), app-layer
    failure — a different layer entirely from the driver's connection death.

## (d) Warm-up state inherited by the blast
Yes, shared: run_warmup uses the SAME RRArm -> same client, same connection,
same ttl=0 token the blast then uses. Its two sequential 248MB sends completed
(responses received => writes flushed, futures resolved), so at blast start the
connection is nominally clean; no source-visible state survives beyond the
shared connection itself. The probe skips warm-up entirely (fresh client+token
per point, sends immediately) — and the probe's connection SURVIVES, which is
consistent with (b)(1) being the live difference, not warm-up residue.

## (e) Memory/read shape
Yes: 248MB per send, synchronously, in the event-loop thread, stamped by the
1.41s/send enqueue stagger. 16 blobs coexist at minimum (held by the in-flight
tasks); rows 17..168's blobs ALSO accumulate as their tasks pre-read before
parking on the semaphore — worst case the whole remaining corpus (~20-35GB)
resident before the breaker stops it. (The "2/61 used" reading post-mortem is
consistent: the driver process was dead by then and its RSS freed.) Additional
per-send copies: header+payload concatenation in transport (another ~248MB per
active send) and sha256 over each blob inside the semaphore.

## Could NOT be determined from source
  1. WHICH side closed the socket and the true first exception for the failed
     legs — dap_client.py:229 discarded it; only the probe's taps or a packet
     trace can name it (not run: parity blast p1 is live).
  2. Exact attribution of 219.63s beyond the read-loop arithmetic above — the
     1.30 vs 1.41 s/read variance is plausible but unproven; no constant matches.
  3. Whether the engine logs pipe opens at this log level at all — so
     "banner-only log" is consistent with, but not proof of, zero receipt.
  4. The engine-side zombie-reaper cadence (whether 92.66s = open+60 or a sweep
     tick) — CONST_DATA_PIPE_TIMEOUT=60.0 is named, its scheduler is not read.
