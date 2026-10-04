# OBS overlay setup — Color Rush Live

The overlay is a read-only Browser Source. It never owns rounds, RNG, or scores. Serve it from the backend at `/overlay` after `npm run build` in `overlay/`.

## Build and serve

```powershell
cd overlay
npm ci
npm run build
```

Start the API (and worker) as in the README. `GET http://127.0.0.1:8000/overlay` serves `overlay/dist`. If dist is missing, a placeholder page is returned.

Development (proxies API/WS to port 8000):

```powershell
cd overlay
npm run dev
```

Add `http://127.0.0.1:5173` to `CORS_ORIGINS` (already in `.env.example`).

## Overlay credential

1. Sign in to the PySide6 console (or call `POST /api/v1/admin/overlay-tickets`).
2. Overlay Setup → Create credential. Copy the OBS URL **including the fragment**. The secret is shown once.
3. The fragment is the long-lived overlay secret. The overlay strips it from history and exchanges it at `POST /api/v1/overlay/ws-ticket` for a short-lived WebSocket ticket, then authenticates `/ws/v1/overlay` with a first-message `{ "ticket": "..." }`.
4. Revoke the credential from Overlay Setup when it should stop working.

Do not put owner JWTs or Google secrets in the OBS URL. Overlay tickets cannot call `/api/v1/admin/*`.

## Browser Source (OBS)

| Setting | Value |
| --- | --- |
| URL | `http://127.0.0.1:8000/overlay#<secret>` (local) |
| Width × height | **1920 × 1080** (tested scaled **1280 × 720**) |
| FPS | 30 is enough; 60 is fine |
| Shutdown source when not visible | Off while the round is live |
| Refresh browser when scene becomes active | On is OK; the overlay resnapshots |
| Control audio via OBS | Yes; overlay audio is **off** by default |
| Custom CSS | None required |

Transparency: append `?transparent=1` before the fragment, e.g. `http://127.0.0.1:8000/overlay?transparent=1#<secret>`. Reduced motion: `?reduced-motion=1`.

## Reconnect

The overlay reconnects with backoff if snapshots stop (~2 s) or the socket drops. It requests a full snapshot; it does not invent a result mid-spin. Reload the Browser Source at any phase — OPEN, DRAINING, SPINNING, RESULT, SETTLING.

## Common issues

- **Placeholder page:** run `npm run build` in `overlay/` so `overlay/dist/index.html` exists.
- **Awaiting connection:** missing/revoked fragment, CORS origin not allowed, or API/worker not running. Empty Origin (OBS) is allowed.
- **Stale secret in the URL bar:** expected. The fragment is stripped after load; sessionStorage keeps it for reload.
- **Wrong chances on the strip:** layout v1 is 19 red / 19 green / 2 gold. Labels must stay 47.5 / 47.5 / 5. Landing uses the backend `animation_plan`.
- **Scores look awarded before settlement:** the overlay shows “Updating scores” while `award_status` is `pending`.
- **Query `?ticket=`:** supported as a fallback, but prefer the fragment so proxies do not log the secret.

## OBS validation status

Automated checks in this repository use a browser (Playwright / local preview). **Actual OBS Studio Browser Source validation is external** unless an operator has confirmed it on a machine with OBS installed.
