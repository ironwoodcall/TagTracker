# "Busiest Ever" — Historic Maximums Enhancement — Design Spec

Status: draft, not yet implemented.

## Goal

Surface two related but distinct "how busy has it ever been" facts that
today live in different, disconnected places:

1. **Per-block peak** — the busiest fixed half-hour `BLOCK` on a day
   (already computed, already in the leaderboard, but tucked behind its own
   `max b` invocation instead of showing up by default).
2. **True busiest window** — the busiest *sliding* window of arrival/
   departure/combined activity (any start minute, not just block-aligned),
   which only exists today as an unwired, offline CLI script
   ([helpers/busiest_days_analysis.py](../helpers/busiest_days_analysis.py))
   that nothing else calls.

Both the CLI `max` command and the web "Historic Maximums" page should end
up showing (1) by default and offer (2) as "busiest ever" content.

## Architectural fact that shapes everything below

The client `max` command is **not** a separate implementation — it's an
HTTP client of the same web CGI script used by the web page:

- Client: `max b` → `tt_process_command.py`
  ([tt_process_command.py:686-696](../tt_process_command.py#L686-L696))
  → [tt_call_leaderboard.py](../tt_call_leaderboard.py) → HTTP GET
  `...?format=plain&category=b`
- Web page: "Historic Maximums" → `web_reports.py` → `leaderboard_report()`
  ([web/leaderboard.py:827-847](../web/leaderboard.py#L827-L847))
- Both paths converge on the exact same CGI entry point,
  [web/leaderboard.py](../web/leaderboard.py) (`_render_category` →
  per-category handler → `render_html=True/False`).

**Consequence: this is a single backend change.** Everything below happens
in `web/leaderboard.py` (plus a small extraction into a shared module); the
client side needs no new logic, only a help-text/alias update.

## Background: what exists today

`web/leaderboard.py` recognizes categories via `_normalize_category()`
([web/leaderboard.py:31-51](../web/leaderboard.py#L31-L51)):

| Letter | Category | Notes |
|---|---|---|
| `a` | all *(default)* | Bundles every category **except busyness** — see `_render_category`'s `"all"` branch, [web/leaderboard.py:127-149](../web/leaderboard.py#L127-L149) |
| `b` | busyness | Per-block peak, see below |
| `f` | fullness | `num_fullest_combined` |
| `p` | precipitation | |
| `r` | registrations | |
| `t` | temperature | |
| `v` | visits | `num_parked_combined` |

`busyness` (today's `max b`) is computed by `_top_busyness()`
([web/leaderboard.py:229-254](../web/leaderboard.py#L229-L254)): for each
day, `MAX(num_incoming_combined + num_outgoing_combined)` across that day's
**fixed, block-aligned** `BLOCK` rows (the same half-hour buckets the
day-detail block report uses). It's bucketed the same way every other
category is — This month / This year / Since last month / Since last
year / Since forever, plus a "so far today" value — via `_busyness_text` /
`_busyness_html` ([web/leaderboard.py:565-660](../web/leaderboard.py#L565-L660)).
It is deliberately excluded from the `"all"` bundle today and only reachable
via `max b` / `?category=b`.

[helpers/busiest_days_analysis.py](../helpers/busiest_days_analysis.py) is
a standalone, offline CLI script — not imported or called by anything else
in the repo. For each day it builds three minute-resolution histograms
(arrivals, departures, combined), then slides a window (default 30 min,
matching the `BLOCK` granularity) across the open hours to find each
category's single busiest window — a *true* sliding window, not
block-aligned, so it can catch e.g. a burst spanning 9:41–10:11 that no
fixed half-hour block would capture. It ranks days across **all** history
in one flat top-`N` list per category (no month/year bucketing) and prints
them interleaved by rank, one row per category
(`print_report`, [helpers/busiest_days_analysis.py:301-340](../helpers/busiest_days_analysis.py#L301-L340)).
It does not filter by `orgsite_id` (fine for its current offline,
single-DB-file usage; not fine to reuse as-is against the shared multi-site
schema — see Implementation notes).

## Proposed changes

### 1. Fold the per-block peak into the default (`"all"`) table

Add busyness's existing rendering into `_render_category`'s `"all"` branch
alongside registrations/fullness/visits/rain/temperature, using the
existing `_busyness_text` / `_busyness_html` functions unchanged — this is
pure wiring, no new computation.

Match the existing (slightly odd but presumably intentional) ordering
symmetry between the two render modes — the html list and the plain-text
list are reverses of each other:

- html: `[registrations, fullest, visits, busyness, rain, temperature]`
- plain: `[temperature, rain, busyness, visits, fullest, registrations]`

Update the client help text, which currently says the default excludes
busyness ([tt_help.py:207](../tt_help.py#L207): `"A or ALL (default) : show
all categories (except 'busyness')"`) — that caveat goes away.

Once folded in, busyness has no reason to remain independently reachable
under its old meaning — see next section.

### 2. Decision: what does the letter `b` mean now?

The prompt's own suggestion of `max a` ("activity") **collides with the
existing `a` = "all"** alias, so it can't be used as-is without also
renaming `all`'s letter — not worth the churn (help text, muscle memory,
any bookmarked `?category=a` links).

**Recommendation: keep letter `b` / word `busyness`, but repoint it at the
new moving-window feature.** It's freed up by step 1 (no longer needed for
the old per-block content, which now lives only inside `"all"`), the
mnemonic ("busy") still fits — arguably fits *better*, since the new
feature is the more rigorous "how busy did it get" answer — and it's the
smallest possible change: no alias table edits, no new letter to document,
`max b` / `?category=b` keeps working, it just gets more honest.

| Letter | Today | Proposed |
|---|---|---|
| `a` | all *(unchanged)* | all — now includes the per-block peak too |
| `b` | per-block peak (bucketed) | **busiest sliding window, all-time** (new) |

The old per-block-peak content and title text (`"Most bikes in + out in a
half-hour block as of {date}"`) don't need to change — they just move from
being their own category to being one section inside `"all"`.

### 3. New `max b` / `?category=b`: busiest sliding window

**Extract, don't duplicate.** Pull the pure computation out of
`busiest_days_analysis.py` — `hhmm_to_minutes`, `minutes_to_hhmm`,
`build_histograms`, `build_prefix_sums`, `window_sum`, `find_best_window`,
and the per-day loop in `analyze()` — into a shared module (e.g.
`database/tt_busiest_window.py`) that both the CLI script and
`web/leaderboard.py` import. Two things need to change on the way in:

- **`orgsite_id` filtering.** `load_days`/`load_visits`
  ([helpers/busiest_days_analysis.py:84-128](../helpers/busiest_days_analysis.py#L84-L128))
  currently pull every `DAY`/`VISIT` row unfiltered. The web/client
  callers need the same `orgsite_id = 1  # FIXME: hardcoded` scoping every
  other query in `web/leaderboard.py` already uses (e.g.
  [web/leaderboard.py:211](../web/leaderboard.py#L211)), or a multi-site DB
  will blend unrelated sites' days together.
- **End-date bound.** Every other category respects the `date` CGI param as
  an "as of" cutoff (`_top_metric`'s `end_date`,
  [web/leaderboard.py:204-226](../web/leaderboard.py#L204-L226)). The
  extracted `analyze()` needs the same `date <= end_date` filter applied
  when loading days, so `?date=2025-06-01` shows history as it stood then,
  matching the other categories' behavior.

**Format: one flat all-time top-N table, not month/year buckets.** This is
the "different overall format" the prompt calls out, and it's the right
call for two reasons: the user's own framing for this feature is "busiest
*ever*", not "busiest this month" — and mechanically, each of the three
categories (Bikes In / Bikes Out / In & Out) needs its own rank column, so
forcing it through the existing bucketed grid would multiply into an
unreadable 3 rows × 5 ranks × 5 buckets. Instead, port
`print_report`'s interleaved-by-rank layout
([helpers/busiest_days_analysis.py:301-340](../helpers/busiest_days_analysis.py#L301-L340))
directly — plain text as-is, html as an analogous table (reuse the
existing `<table class="general_table leaderboard_table">` styling
convention used elsewhere in this file, not the value/date-pair columns
helper, since this table has 6 columns: Category, Date, Window, In, Out,
In & Out). Keep the CLI script's defaults: 30-minute window (matches
`BLOCK` granularity, so the "busiest block" and "busiest window" numbers
stay comparable), top 5 ranks.

**Performance: one pass, not five.** The existing bucketed categories cheaply
re-run a `MAX()`/`ORDER BY ... LIMIT` SQL query once per bucket
(`_top_metric`, `_top_busyness`) because SQL aggregation is basically free.
The sliding-window analysis is not free — it's a per-day histogram + prefix
sum + scan. Since the new format has no buckets, this is naturally a single
pass: run `analyze()` once over all days up to the `date` cutoff, done.
(If a future bucketed variant is wanted, compute the per-day best-window
table once and slice it by date range in Python for each bucket, rather
than re-running `analyze()` per bucket.)

### 4. Web page: make it discoverable

Since the backend is shared, `?category=b` already renders the new content
on the "Historic Maximums" page once step 3 lands — but there's currently
no in-page way to reach any specific category; the page is linked to once,
with no category picker, from `main_web_page()`
([web/web_season_report.py:664-666](../web/web_season_report.py#L664-L666)),
and always opens on `"all"`. Add a small self-referencing link near the top
of `leaderboard_report()`
([web/leaderboard.py:827-832](../web/leaderboard.py#L827-L832)), next to
the existing main/back buttons, e.g. "See busiest-ever windows →" built via
`cc.CGIManager.selfref(what_report=cc.WHAT_LEADERBOARD, category="b")`, so
the feature isn't only reachable by hand-editing the URL.

## Implementation checklist

1. Extract sliding-window core functions from
   [helpers/busiest_days_analysis.py](../helpers/busiest_days_analysis.py)
   into a shared module; add `orgsite_id` and `end_date` filtering.
2. Repoint `busiest_days_analysis.py`'s own loading/analysis calls at the
   shared module (no behavior change for the CLI tool itself).
3. In `web/leaderboard.py`:
   - Add busyness (existing per-block implementation, untouched) into the
     `"all"` branch of `_render_category`.
   - Rewrite `_render_busyness` / `_busyness_text` / `_busyness_html` (or
     add new sibling functions and repoint the `"busyness"` handler) to use
     the shared sliding-window module, flat top-N format.
4. Update [tt_help.py:199-225](../tt_help.py#L199-L225) — drop the "except
   busyness" caveat on `A`/`ALL`; reword the `B`/`BUSYNESS` line to
   describe the sliding-window, all-time ranking instead of "days with
   busiest half hour".
5. Add the "busiest ever" self-link to the web leaderboard page header.

## Open questions

- **Top-N and window size as params?** CLI `busiest_days_analysis.py`
  accepts `window_minutes` and `top_n` as positional args. Worth exposing
  as `?window=` / `?top=` CGI params (and a third `max b` arg) now, or
  ship fixed at 30 min / top 5 and revisit if asked for?
- **Should `"all"` also get a taste of the new busiest-window feature?**
  This spec recommends *no* — keep `"all"` cheap (existing single-value
  categories) and keep the heavier 3-category ranking as an opt-in `max b`
  — but flagging in case the "busiest ever" framing was meant to be
  front-and-center rather than one click away.
