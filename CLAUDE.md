# CLAUDE.md — project memory for `az-iptv`

> **Maintenance rule (read first).** Any change to a mechanism or a policy in
> this repo must update this file **in the same commit**. If you add a gate,
> move a group between tiers, change a cap, or alter the write rules, edit the
> matching section here before you commit. A stale CLAUDE.md is worse than none.

## 1. What this is

A self-updating IPTV playlist for Azerbaijani/Turkish viewers.
`generate_playlist.py` runs daily on GitHub Actions (`.github/workflows/update.yml`,
cron `0 4 * * *` = 08:00 Baku, plus `workflow_dispatch`): it pulls channel, feed
and stream data from the iptv-org public API, health-checks every candidate URL,
heals broken links, and rewrites `playlist.m3u` plus a report of what is waiting.

Player URL (Televizo etc.):
`https://raw.githubusercontent.com/hesenrustamli/az-iptv/main/playlist.m3u`

## 2. HARD RULES — not preferences

- **Legal, free, official streams only.** Never carry a pirated feed of a pay
  channel. `PAY_TV_BLOCK` enforces this for anything automatic.
- **Static URLs only.** Never write a token-refreshing scraper. A URL carrying a
  per-session token is never adopted — see `looks_tokenized()`.
- **Two sources, ever:** the iptv-org database, and a broadcaster's own domain
  (its official live page). Never add a scraper for an aggregator, restream site,
  IPTV portal, or third-party playlist dump, however convenient. This is written
  as the SOURCE POLICY comment block above `EXCLUDE` and governs `SOURCES` and
  `AUTO_RULES` alike.
- **No Cyrillic in display names**, and the words *russia* / *russian* never
  appear capitalised. Enforced by `RENAME` plus the `re.sub(r"Russia", "russia")`
  in `display_name()`. **tvg-ids are exempt** — EPG matching depends on them and
  they are not user-visible.
- **The group name `· russia` is preserved exactly**, middot and all.

## 3. Architecture map

**`PICKS`** — the hand-curated playlist, group → ordered list of channel ids.
Group order in this dict *is* the order in the file. Streamless ids stay in
`PICKS` on purpose: they are listed in `WAITING.md` and rejoin automatically the
day a stream passes. `CBCSport.az` and `IdmanTV.az` are dual-grouped
(Azərbaycan + İdman) deliberately — this is why entry count exceeds unique
channel count.

**`OVERRIDES`** — hand-verified static URLs, taken from a broadcaster's own
player or from an iptv-org provider file (`<country>_<provider>.m3u`, whose
entries carry no tvg-id and so must be hand-keyed to a channel), merged ahead
of the iptv-org candidates so ranking prefers them. Never
dropped on a failed probe: `best_working()` returns them anyway and records the
failure, because the runner sits outside Azerbaijan and a failure there says
more about vantage than about the stream. An override carrying
`"expected_fail": True` is one verified from Baku and known to fail from the
runner: its failure goes to a quiet line and is counted separately, so that an
*unflagged* override which starts failing still stands out instead of being
lost in known noise. The run prints `overrides: N pinned; E expected
vantage-fail, U unexpected failure(s)`, and says so when a flagged override
starts passing, since the flag is stale at that point. Only `TRTBelgesel.tr`
carries the flag today: it answers from Baku and failed all three candidates on
the runner the same morning, which is the passing-vantage evidence the
provenance rule below demands.

**Override provenance — a hard rule.** An override comment may claim only what
a *recorded probe measured*, never what someone expected or intended to check.
`"expected_fail": True` additionally requires **at least one passing vantage on
record**: a stream that fails everywhere is not vantage-split, it is broken,
and belongs in `WATCHLIST` where its silence is honest. Earth Touch TV was
pinned on an unexecuted manual check, claimed "Baku-verified", and failed nine
header variants from Baku plus the runner — it was demoted for exactly this.
Overrides are also subject to `BAD_HOSTS` and `STREAM_BLOCKLIST`: hand-verified
never outranks measured-unusable, and anything dropped that way is named in the
run summary.

**`WATCHLIST`** — hand-found static candidates for channels iptv-org has no
working entry for, and last-known-good URLs for bench channels so their
readiness does not depend on iptv-org churn. Probed daily like anything else,
joining the day they start answering; dropped after `PRUNE_AFTER = 60`
consecutive fails. An entry is a bare URL, or `("url", "quality")` when the
resolution is known from iptv-org's label but the probe cannot report it —
quality only affects ranking and the display suffix, and never overrides a
probe result. A URL iptv-org already carries for that channel is skipped
rather than probed twice, and activates by itself the day upstream drops it.
Entries bypass the feed-language filter, which is how a channel whose only
upstream feed is tagged (say) `deu` can still be carried.

**`LOCAL_CHANNELS`** — display names for ids the iptv-org database has no
record of at all. Merged into `channels` with `setdefault`, so real upstream
data always wins the day the channel is added. Without the stub `display_name()`
prints the raw id and `channels.get(cid)` hands `None` to code expecting a
record. The ids are deliberately written in iptv-org's own shape.

**`SOURCES` + portal guard** — broadcaster-owned live pages, scraped daily by
`discover()` for static `.m3u8` URLs, persisted in `discovered.json`. A page
yielding more than `PORTAL_LIMIT = 2` URLs is treated as a portal listing rival
channels, and only URLs whose path matches `names_channel()` are kept. A live
channel is never swapped out from under itself — only a would-be-waiting channel
adopts a discovered URL.

**`AUTO_RULES`** — ordered `(group, predicate)` list evaluated against the whole
iptv-org database; first match wins. Only two rules remain: İdman (sports) and
Azərbaycan (country AZ, monthly). Sənədli had one until the group was locked.
`auto_group_for()` skips any group in `LOCKED_GROUPS`.

**`EXCLUDE`** — ids that must never be auto-added, whatever the rules say. Seeded
with every channel removed by hand, so the rules engine cannot quietly undo
curation. **Deleting a channel means adding its id here**, not just removing it
from `PICKS`.

**`STREAM_BLOCKLIST`** — individual URLs that must never be carried: dead,
geo-blocked from Azerbaijan, **or not a legal free feed**. The last case is not
optional tidying — iptv-org carries pay-DTH origin leaks and pirate aggregator
hosts, and `rank()` can score them above the legitimate feed (an `akamaized`
host reads as official, and a leaked 4K stream outranks a legitimate 1080p
one). Merely leaving such a URL out of `WATCHLIST` does not keep it out.

**`BAD_HOSTS`** — substrings matched against the **whole URL**, so a path slug
counts, not just the hostname. Beyond the two dead CDNs it now carries
`samsung-gb` / `samsunggb`: amagi's Samsung TV Plus UK playouts went three for
three — Curiosity NOW, Earth Touch, NatureTime — passing the US runner and
403ing from Baku, so the slug family is a rule rather than a URL-at-a-time
chase. `samsunguk` is deliberately **not** matched: WaterBear and INWILD ride
it and neither vantage has been measured.

**`PAY_TV_BLOCK`** — subscription broadcasters, matched case-insensitively
against channel name and network. Free-to-air Match! is deliberately absent while
the premium Match! tiers are listed.

**Gates** (all in `auto_eligible_group()`, identical for newcomers and
incumbents): `EXCLUDE` → rule match → `is_pay_tv()` → `notable()` (rejects
closed/NSFW and anything whose `broadcast_area` is only city `ct/` or subdivision
`s/` level) → `NICHE_SKIP` (İdman only) → `latin_only()`. Note that
`broadcast_area`, `languages` and `format` live on the **feed**, not the channel.

**`AUTO_CAP` + `TOTAL_MAX`** — `{"İdman": 40}`, other groups
uncapped; `TOTAL_MAX = 199` is a hard ceiling on the whole playlist. The build
runs in two passes so the ceiling knows how many slots `PICKS` occupies, then
trims auto-adds lowest-rank-first. `PICKS` entries and `OVERRIDES` are never
trimmed or displaced.

**Sticky slots** — an incumbent auto-add holds its seat while it matches its rule
and passes the probe, and holds on last-known-good through a single failure. It
vacates only after `STICKY_FAILS = 2` consecutive failures, on disqualification,
or on a cap/ceiling trim. Newcomers fill open slots only; they never displace.
Incumbency lives in `auto_state.json`.

**`LOCKED_GROUPS`** — a locked group contains exactly these ids in exactly this
order. No `AUTO_RULE` may add to it and nothing is reordered or displaced by
ranking, because the ordering is editorial. Eight groups are frozen this way.
Stream healing, retention and daily `WAITING.md` probing still run for every
member — freezing stops growth, not maintenance.

**`SUBSTITUTES`** — an ordered bench for a locked group. A locked group
publishes exactly its members, so a member with no working stream leaves the
group one shorter; the bench covers that seat without touching membership.
Each run, as many bench channels enter as there are hidden members, taken in
bench order and skipping any bench channel with no working stream of its own.
They render **after** the members, so the editorial order of positions 1..N
never reshuffles, and they step back on the run the cover is no longer needed
— a starter never loses its claim on its position. **Seat gate.** A bench member may take a seat only if **both** hold: its
chosen URL passes the runner's probe this run, **and** `BAKU.json`'s most
recent verdict for that same URL is a pass (at any age — the gate wants
evidence the stream ever worked, not a recent opinion). A recorded fail blocks
the seat until a newer pass replaces it; never-measured does not seat. The
seat falls through to the next rank meeting both. The reason is what a
substitute is *for*: it exists solely to put something watchable in a seat
that would otherwise be empty, so being watchable should be a precondition of
taking the seat rather than a hope. Starters are deliberately exempt —
editorial picks publish best-effort, with `BAKU.json` steering only which of
their URLs is chosen, via ranking. Bench channels are
stream-hunted exactly like waiting members (daily iptv-org refresh plus
`WATCHLIST` probing) and are listed in `WAITING.md` with their rank and
`in play` / `ready` / `gated` / `streamless` status, separately from waiting
starters; the gated line reads `runner-alive, no Baku pass on record`.
Meant for locked groups; a bench on a grown group would race its own auto-adds.
Only Sənədli has one today (15 deep).

**`BAKU.json`** — committed vantage data, `{url: {"ok", "ts"}}`. The runner is
in the US and the viewer is in Baku, so a CI probe answers a different question
than "can this be watched". Every **local** run records what it measured here;
the runner only ever *reads* it. This is the single deliberate exception to the
single-author rule in §5, because only this machine can produce the data — it
is committed from here like code. It does two jobs. **Ranking:** a Baku-ok URL sorts ahead
of its rivals for that channel, a Baku-failed URL sorts behind them, unknown
keeps its existing rank. **The bench seat gate** (see `SUBSTITUTES`): a
substitute needs a recorded pass to take a seat. It still never excludes a
stream from the playlist; `STREAM_BLOCKLIST` and `BAD_HOSTS` stay the only
tools that do, and a gated substitute simply yields its seat to the next rank.

**Last verdict wins, with no expiry.** A verdict stands until a newer probe of
that same URL overwrites it, however old it is; the timestamp is for the
reader, not the logic. This is not laziness about staleness, it is the
consequence of the operating model in §5: there is no scheduled sync, so a
freshness window would not measure "recent truth" but "how long since someone
happened to run a preview", and every reading would decay to *unknown* — which
is exactly the state that lets a geo-blocked URL win a bench seat. The cost is
that a transient failure sticks until re-probed; the benefit is that the system
stays safe under arbitrarily stale data, which is the condition it runs in. Readings older
than `BAKU_FRESH_DAYS = 14` are ignored, so a transient flap ages out instead
of being held against a stream. A `geo` probe result is not a verdict and is
not recorded. This is what breaks the iptv-org-before-`WATCHLIST` tie that used
to publish a geo-blocked feed over a working alternate.

**Monthly AZ sweep** — `AZ_SWEEP_GROUP` is evaluated only when
`AZ_SWEEP_DAYS = 28` have passed since `last_az_discovery` in `auto_state.json`.
On an active run the stamp is set to today, so the next window is today + 28.
Only *new-channel discovery* is monthly; healing, retention, `SOURCES` scraping
and waiting-list probing stay **daily for every group, no exceptions**.

**`looks_tokenized()` substring rule** — exact key matching against
`TOKEN_PARAMS` is not enough: a Pluto stitcher URL carrying an expiring JWT under
`authToken` nearly got pinned as a pick. Any query key *containing* `token`,
`expires`, `signature` or `wmsauthsign` is rejected.

## 4. Group policy

| Group | Tier | The bot may | The bot may not |
| --- | --- | --- | --- |
| Azərbaycan 🇦🇿 | monthly, uncapped | add new AZ channels once per 28 days; heal daily | add anything in `EXCLUDE`; add off the monthly cycle |
| Ukrayna | frozen | heal, retain, probe waiting members | add, reorder, displace |
| Türkiyə – Ümumi | frozen | heal, retain, probe waiting members | add, reorder, displace |
| Xəbər – Türkiyə | frozen | heal, retain, probe waiting members | add, reorder, displace |
| İdman | machine-managed, cap 40 | add/trim/vacate per rules, caps, stickiness | drop a `PICKS` entry or an override |
| Uşaq | frozen | heal, retain, probe waiting members | add, reorder, displace |
| Musiqi | frozen | heal, retain, probe waiting members | add, reorder, displace |
| Sənədli | frozen, order is editorial (1–13), 16-deep bench | heal, retain, probe waiting members; seat a substitute per hidden member | add, reorder, displace, auto-add anything |
| · russia | frozen | heal, retain, probe waiting members | add, reorder, displace, rename the group |
| Beynəlxalq Xəbər | frozen, order is editorial (1–9) | heal, retain, probe waiting members | add, reorder, displace |

## 5. Working conventions

- **Pull `main` first, every session.** The bot commits daily; local state goes
  stale overnight.
- **Single author.** Only the GitHub runner writes `playlist.m3u`, `WAITING.md`,
  `discovered.json` and `auto_state.json` (`IS_CI` via `GITHUB_ACTIONS`). A local
  run computes and reports everything but writes nothing, so it cannot race the
  bot or publish from the wrong vantage. **`BAKU.json` is the one exception**:
  it is written by local runs only, never by the runner, and committed from
  this machine alongside code. `--write` overrides deliberately and
  prints a warning. Local commits should contain code only.
- **Operating model — who does what.** The runner is **fully autonomous**: it
  publishes daily on its own, and nothing here depends on this machine being
  on. Baku data is *not* synced on a schedule; `BAKU.json` refreshes only as a
  side effect of a maintenance preview, so it may be arbitrarily stale, and
  every mechanism that reads it must stay safe when it is (hence no expiry —
  see `BAKU.json` in §3). **The user is the geo sensor**: a channel that is
  dead from Baku is reported by hand, and enters the system as a
  `STREAM_BLOCKLIST` or `BAD_HOSTS` change, which is the one signal CI can
  never produce for itself. Automation picks the best candidate it can measure;
  the viewer's report is what tells it the measurement was from the wrong
  country.
- **Triggering:** `gh workflow run update.yml` (gh lives at
  `C:\Program Files\GitHub CLI\gh.exe`, not on PATH). Not needed for print-only
  changes.
- **Reports must distinguish entries from unique channels.** Dual-grouped ids
  make the two differ; a count keyed by tvg-id silently reads low. Every run
  prints `Entries N = M unique channels + K dual-grouped repeat(s)` for this.
- **Reports must distinguish preview from published.** Local runs print the
  `PREVIEW - local vantage; runner is authoritative` banner and tag the totals
  line. Preview numbers are never quotable as published facts — the runner is in
  the US, the user is in Baku, and the two vantages disagree.
- **Never invent a causal explanation without checking the diff first.** If a
  number moved, run `git diff` and prove what moved before saying why. A
  plausible story about a change that never happened is worse than "I do not
  know yet". A published stream that fails from Baku is the standing criterion
  for `STREAM_BLOCKLIST` — report the channel, group and host.

## 6. Live state

- `WAITING.md` — channels with no working stream, the `SUBSTITUTES` bench with
  rank and status, alternates found, and every channel added by `AUTO_RULES`.
  Regenerated each run. Its first table is parsed back on the next run to spot
  returning channels, so no other table may use a `| Channel ` header, and
  bench names are subtracted from that comparison — a channel moving onto the
  bench leaves the waiting table without having gained a stream, and would
  otherwise be announced as "is back".
- `auto_state.json` — `incumbents` (sticky auto-slots + fail counts) and
  `last_az_discovery`.
- `discovered.json` — `discovered` (per-channel URLs found on official pages,
  with fail counts) and `watchlist` fail counts.
- `BAKU.json` — per-URL Baku probe results, written locally and committed by
  hand; read by the runner to bias ranking. Never written in CI.
- `EXCLUDE`, `STREAM_BLOCKLIST`, `BAD_HOSTS` in `generate_playlist.py` — the
  record of what was removed by hand and why. Each entry carries its reason as a
  comment; keep that up.
