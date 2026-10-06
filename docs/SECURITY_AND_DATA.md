# Security and data — Color Rush Live

## API data versus game data

YouTube API data includes channel IDs, display names, avatar URLs, live chat message IDs, published timestamps, continuation tokens, and OAuth/API credentials. The backend retains the **minimum** needed to identify a player and classify a command.

Application-generated game data includes internal player UUIDs, picks, score ledger rows, period aggregates, archives, champions, round state, presentation plans, and operator audit records. Game points are game points, not YouTube audience or performance metrics.

Separating application scores from API data does **not** automatically grant permission to retain linked YouTube identifiers forever.

## Retention (defaults)

| Data | Default |
| --- | --- |
| Raw/normalized command inbox | 7 days, then purge job |
| Profile/avatar cache | refresh in bounded batches; follow current YouTube 30-day limits where applicable |
| Scores, streaks, archives | retained as game records until a data-deletion request |
| Google tokens | until disconnect/revocation |
| Overlay tickets | TTL plus explicit revoke |
| Backups | expiry is a restore/ops policy; deletion is not instant from old backups |

Implemented today: command inbox 7-day purge (`command_retention_days` + worker retention tick). `players.profile_refreshed_at` exists, but **no 30-day profile refresh or identifier-unlink job runs**. Display names, avatars, and `provider_channel_id` can therefore remain linked on leaderboards indefinitely until an OWNER delete.

## Deletion

`POST /api/v1/admin/players/{player_id}/delete-data` (OWNER):

- Anonymizes display name and channel id in SQL
- Sets `deleted_at` / `anonymized_at`
- Removes Redis leaderboard members for that player
- Writes an audit row

Old backups may still contain identifiers until those backups expire. Do not claim instant worldwide erasure.

Viewers have **no** self-serve deletion request. Operator-only delete does not meet YouTube's user-facing deletion requirement (Developer Policies III.E.4.g: delete within 7 calendar days of a user request).

## Production API-use review (2026-10-06)

Engineering review against the [YouTube API Services Developer Policies](https://developers.google.com/youtube/terms/developer-policies) as fetched 2026-10-06. This is **not** legal advice, **not** a YouTube compliance audit, and **not** YouTube approval. Re-check the [Terms of Service Revision History](https://developers.google.com/youtube/terms/revision-history) before any public broadcast.

### Explicit answers

| Question | Answer |
| --- | --- |
| May Color Rush Live keep YouTube channel IDs on leaderboards indefinitely? | **No.** Live-chat author channel IDs, display names, and avatar URLs are API Data obtained without each viewer's OAuth to this client (Non-Authorized Data). III.E.4.d: store at most 30 calendar days, then delete or refresh. Indefinite `players.provider_channel_id` and overlay names are **not cleared**. |
| May application scores and internal UUIDs persist? | **Yes, if unlinked from YouTube identifiers.** Game points are application-generated, not YouTube metrics (III.E.4.h). They may remain after channel IDs, names, and avatars are anonymized. Overlay and console copy must keep labeling them as game points, not YouTube audience or performance stats. |
| Is the current deletion path enough for production? | **No (partial).** OWNER `delete-data` exists. III.E.4.g requires a way for a **user** to request deletion, completed within 7 days. There is no viewer-facing request path, privacy policy contact, or automated 7-day SLA. |
| Are required ToS / privacy disclosures present? | **No.** III.A.1–2 require a YouTube Terms of Service link (`https://www.youtube.com/t/terms`), a user-agreed privacy policy that states the client uses YouTube API Services, and a link to the [Google Privacy Policy](http://www.google.com/policies/privacy). This repository has none. A production broadcast is **blocked** on that gap even if ingest works. |
| Is scoring `!red` / `!green` / `!gold` approved? | **Unresolved.** III.F.3.c forbids incentives or rewards for engaging with YouTube Applications, including adding comments. Chat-command scoring can be read as rewarding comments. The product already ignores watch time, subscriptions, Super Chat, memberships, and donations. That does **not** equal YouTube approval of the game use case. A private technical test may proceed. A **public live stream must not** be treated as cleared. |
| Does a 30-day profile refresh job exist? | **No.** Column `profile_refreshed_at` is unused by a scheduled refresh/purge. Command inbox purge is implemented. |

### What this review does and does not clear

- **Cleared:** the documentation placeholder. Production API-use / retention is **recorded**.
- **Not cleared:** production or public broadcast. Missing privacy/ToS surfaces, missing 30-day identifier refresh or unlink, operator-only deletion, and the unresolved comment-incentive reading remain **blocked**.
- Do not implement privacy-policy UI, a 30-day anonymizer, Kafka, or other post-V1 product work as part of this review.

Do not reward watch time, subscriptions, paid messages, or donations. Super Chat and membership events are ignored for scoring.

If a Google API key or OAuth client secret was ever committed (including an older `.env.example`), rotate it in Cloud Console. `.env.example` must contain empty placeholders only.

## Credentials and transport

- Operator JWT access + hashed refresh sessions
- Overlay tickets are read-only and cannot call admin routes
- OBS URL carries the overlay secret in the **fragment**; the overlay strips it and exchanges `POST /api/v1/overlay/ws-ticket` for a short-lived WS JWT (`typ=overlay_ws`)
- Loopback bind by default; CORS/WebSocket origins are configured
- Metrics restricted to trusted/loopback when `TRUSTED_METRICS` is disabled
- Google YouTube secrets (`GOOGLE_API_KEY`, OAuth client id/secret) live only in gitignored `.env`; never in `.env.example`, desktop config, overlay bundles, or chat
- An API key pasted into chat or committed to git is compromised: rotate it in Cloud Console and restrict the replacement to YouTube Data API v3 (`docs/YOUTUBE_SETUP.md`)
- No secrets in overlay assets or TypeScript bundles
- Structured logs must not include tokens, full chat bodies, or profile secrets
