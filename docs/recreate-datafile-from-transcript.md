# Recreating a datafile from a TagTracker transcript

Status: **design discussion only** — no script written yet. This document
is the place to settle the open questions below before writing
`helpers/transcript_to_playback.py` / `helpers/transcript_to_datafile.py`.

Source material surveyed: all 168 files in `/tmp/tt-transcripts`
(`echo-YYYY-MM-DD.txt`, April–September 2026), plus the current parser,
datafile and undo/redo implementation in this repo (`tt_commands.py`,
`tt_process_command.py`, `common/tt_biketag.py`, `common/tt_trackerday.py`,
`tt_datafile.py`, `tt_undo.py`, `tt_registrations.py`).

## 1. What a transcript actually is

Each file is a captured terminal session (stdin echoed + stdout), one file
per operating day. It's not a log of a single command grammar version —
the files span ~6 months and the program changed under them (e.g. the
on-screen term for a held tag flips from "held" to "suspended" partway
through the set, matching the `HOLD`→`SUSPEND` rename in `tt_commands.py`).
So the design below deliberately leans on the small set of **output**
strings that stayed stable across that whole period, rather than on
parsing every input command line.

Structure: a banner/version block, an hours-confirmation dialogue, then a
long run of "prompt line" + "response lines" turns:

```
  9:39  Bike tag or command >>>   ga7
  Bike GA7 checked in at 9:54              <---in---
```

Note the prompt's displayed time (9:39) and the time actually recorded
(9:54) differ — the recorded time is whatever "now" was when the command
was actually submitted/accepted, which echo-capture doesn't show directly.
**The only trustworthy time for an event is the one in the confirmation
line itself**, never the prompt timestamp.

A "turn" (one prompt → next prompt) can contain 0, 1, or many response
lines: multi-tag commands (`bi7 gc8 gc5 gc9 gc2`) emit one confirmation
line per tag; commands missing a required argument reprompt inline
(`del bn4` → `Enter 'in' or 'out':    i y`); invalid input just errors and
the state doesn't change.

## 2. The confirmation-line catalogue (what we actually key off)

Across the whole corpus, state-changing turns are covered by a short list
of stable templates (counts are occurrences across all 168 files):

| Template | Meaning |
|---|---|
| `Bike TAG checked in at HH:MM` | a check-in landed (new visit *or* an edit of the open visit's time-in — see §3) |
| `Bike TAG checked out at HH:MM` | a check-out landed (closes a visit *or* edits an already-closed visit's time-out) |
| `Deleted check-in for latest TAG visit.` | the latest visit's time-in was removed (visit dropped if it had no time-out) |
| `Deleted check-out for latest TAG visit.` | the latest visit's time-out was cleared (visit reopened) |
| `There is a total of N bike registration(s) today.` | registrations count is now N (absolute, not a delta) |
| `Undoing:    <label>` | the single pending undo was applied |
| `Redoing:    <label>` | the single pending redo was applied (and, for in/out/edit, is immediately followed by the normal `Bike TAG checked ...` line restating the reapplied effect) |
| `TAG  is now suspended` / `TAG  is no longer suspended` | hold/unhold — doesn't touch visits, but *does* occupy the undo slot (see §3) |
| `Noted.` | a note was created — also occupies the undo slot, doesn't touch visits |

Everything else we see (`a`/audit grids, `stat`, `max`, `tags`, `recent`,
`query`, `chart`, `dataform`, `yesterday`, `help`, retire/unretire,
`Tag X is retired.`, `No tag 'X' available today.`, "already checked
in"/"not checked in" errors, etc.) either never changes tag state or is
explicitly out of scope per your brief (suspend/retire/"most other
things"). We ignore all of it for state purposes — it's not that we can't
parse it, it's that none of it feeds the two outputs you want.

## 3. The hard part: undo/redo, and why it's simpler than it looks

`del`, `edit`, `flip`, and the ambiguous "just type the tag" `inout` form
all reuse the exact same two confirmation lines as plain `in`/`out` — e.g.
`edit wc1 in 1340` prints `Bike WC1 checked in at 13:40`, identical to a
fresh check-in. There is no text-level way to tell "new check-in" from
"edited check-in" apart.

I read `tt_undo.py` to settle this rather than guessing, and it resolves
both problems for us:

- **Resolving the in/edit ambiguity**: `check_in()` only succeeds when the
  tag's current status is UNUSED/DONE (no open visit); `edit_in()` only
  succeeds when it's IN_USE/DONE (there's a visit to edit). They're
  mutually exclusive by construction. So: if our own simulated model shows
  the tag currently has an *open* visit when we see `checked in`, it must
  be an edit of that visit's time-in; otherwise it's a new visit. Same
  logic for `checked out` (edit_out on an IN_USE tag is defined to behave
  identically to a plain check-out, so that case needs no special
  handling at all). **We never need to know which command word produced
  the line — our own state tells us how to interpret it.** This also
  means `flip` needs no special-casing: it's just a `checked out` line
  immediately followed by a `checked in` line, and the state-based rule
  above handles both legs correctly on its own.

- **Resolving undo/redo**: the real undo mechanism (`UndoManager`) is a
  single-slot, generic snapshot/restore — before running any of
  `in/out/inout/edit/delete/flip/hold/unhold/note`, it deep-copies the
  affected tag(s)' full visit list + status into a pending-undo slot; an
  `undo` restores that snapshot wholesale and moves the *replaced* state
  into a pending-redo slot; `redo` restores that. Depth is exactly one in
  each direction — there's no multi-level undo stack to model. Crucially,
  **`retire`/`unretire`/`registrations` never touch this slot**, so an
  intervening retire doesn't invalidate a pending undo of an earlier `in`.
  We mirror this exactly: our simulator keeps its own one-slot
  undo/pending-redo, snapshotting whichever tags a turn actually changed,
  and on `Undoing:`/`Redoing:` lines it restores from *our own* snapshot —
  not by trying to parse the label text, which for `edit` genuinely
  doesn't contain enough information to recover the pre-edit time (the
  `Undoing:` line for an edit has no "restore to this time" value in it;
  only our snapshot has it). The `Redoing:` line conveniently doesn't need
  this trick since it's always immediately followed by the normal
  confirmation line, which we already parse.

  Net effect: **the parser never needs to interpret what `Undoing:`/
  `Redoing:` is undoing** — it just needs to know *that* undo/redo
  happened, and restore/advance its own one-slot snapshot. This also
  cleanly handles multi-tag commands where only some tags succeeded
  (`wb0 wa15` both erroring vs. one succeeding): the snapshot is only
  armed for tags that actually changed in that turn, exactly mirroring
  `UndoManager.record()`'s `if not changed: ... leave slot alone` check.

This means the whole simulator is: a per-tag list of visits
(`time_in`, `time_out|None`), a one-slot undo snapshot, a one-slot redo
snapshot, and a tiny set of rules keyed entirely on the confirmation-line
catalogue in §2 — no command-grammar parser, no abbreviation table, no
need to handle multi-line reprompts, aliases, or version drift in wording
for commands we don't care about.

## 4. Registrations

Simpler than it first looked: `registrations` isn't in the undoable set
at all (confirmed — grepping every `Undoing:`/`Redoing:` line in the whole
corpus, `reg` never appears), so there's no delta/undo bookkeeping needed.
Every `There is a total of N bike registration(s) today.` line is an
**absolute** value. We just take it at face value each time it appears
and remember the latest N (and, if useful, the time it changed, taken
from the *next* prompt line the same way check-in/out times are "now" —
though since the datafile only stores one number for the whole day,
timing only matters for the playback-script output, not for the direct
datafile output).

## 5. Two output modes — recommend building both on one shared core

Your two alternatives aren't really competing designs; they're two thin
renderers over the same simulated end-state, which argues for one shared
parser/simulator module and two small output functions rather than two
separate scripts that each re-parse the transcript:

- `helpers/transcript_sim.py` — parses a transcript into the model above
  (final per-tag visit list, final registrations count, open/close
  hours, any notes).
- `helpers/transcript_to_playback.py` — renders that model as a command
  script: for each distinct `(direction, time)` across all tags, one
  `in <tags...> <time>` or `out <tags...> <time>` line (grouping tags
  that share a time, the way your example suggested), sorted
  chronologically, plus `reg = N` line(s). **Deliberately not a literal
  replay of the transcript** — mistakes, retries, and undone actions are
  already resolved out by the simulator, so what's emitted is the
  *minimal* sequence that reproduces the final state, which is also what
  makes it safe to feed straight into the real `tagtracker.py` prompt.
- `helpers/transcript_to_datafile.py` — renders that model directly as the
  current JSON datafile format (`TrackerDay._day_to_json_dict()` shape:
  `bike_visits`, `registrations`, `time_open`/`time_closed`,
  `regular_tagids`/`oversize_tagids`/`retired_tagids`, optionally
  `notes`), skipping the live program entirely.

Both are useful for different things (playback is good for testing the
live command flow / undo-redo code itself; direct datafile generation is
good for quickly repopulating `data/` for reports/backtesting), and
sharing the core means fixing a parsing edge case fixes both outputs at
once.

## 6. Direct-datafile specifics (mode b)

- `bike_visits`: directly from the model — tagid, time_in, time_out
  (blank if still open — some transcripts probably end with bikes still
  on-site at close; that's a legitimate end state, not an error).
- `bike_size` per tag: the datafile needs `regular`/`oversize` per visit.
  The *transcript* doesn't say this explicitly anywhere I found in the
  confirmation lines. The current `client_local_config.py`
  (`REGULAR_TAGS`/`OVERSIZE_TAGS`) enumerates the full tag universe by
  prefix+number and is the natural source of truth — tags get **added**
  to it over time (the `Changes applied: ... added 1 tag to config file`
  turns we see are exactly this), but a prefix's size classification
  doesn't change retroactively, so classifying by *today's* config should
  correctly classify any tag used in any historical transcript. A tag
  used in a transcript that isn't in either list today would be a real
  anomaly worth surfacing as a warning rather than silently guessing.
- `regular_tagids`/`oversize_tagids`: likewise taken from current config
  (the full configured universe, not just the tags used that day — this
  matches what a live-produced datafile actually contains).
- `retired_tagids`: lower priority per your brief. Best-effort: start from
  tags retired in current config, adjusted by any `retire`/`unretire`
  confirmations seen in the transcript for that specific day. Since
  retire/unretire rewrite `client_local_config.py` permanently, a
  from-scratch, fully-accurate historical reconstruction isn't really
  possible without a config history we don't have — fine to approximate.
- `time_open`/`time_closed`: the opening dialogue is the fiddly part —
  it's a free-text prompt that sometimes gets garbage input
  (`Not a time.`, someone typing a tag by mistake) before landing on a
  value or an empty `<Enter>` (meaning "keep the shown default"). Plan:
  take the *last* successfully-accepted value at each of the two prompts,
  defaulting to the "Currently set at HH:MM - HH:MM" value shown in the
  same dialogue if the final answer was blank.
- `notes`: optional bonus per your message. `NotesManager`/`Note` just
  store plain strings (`note.pack()`/`NOTE_ACTIVE` etc.); the `note`/`n`
  command's argument text is exactly a new note. Capturing these is easy
  and cheap to add, but isn't needed for the core goal and I'd build it
  last.

## 7. Known, deliberate non-goals

- No modeling of hold/suspend windows, retire/unretire's permanent config
  edits, or anything from audit/chart/stat/query/report commands — per
  your brief, and also none of it is needed to get tags-in/out +
  registrations right.
- No attempt to reproduce the *exact original sequence* of mistakes —
  the playback output is the cleaned-up minimal command set, not a
  keystroke-for-keystroke replay. (If literal replay including every
  undo/redo/typo turns out to matter to you, that's a different, much
  bigger tool — flag it if so, but I don't think it's what you're after
  given "very close to the same state" is the stated goal.)
- Graceful degradation, not hard failure, for a truncated/crashed
  transcript (program killed mid-session): emit whatever final state the
  partial parse supports, with a warning, rather than refusing to produce
  output.

## 8. Decisions made, and what got built

Answered: final-only `reg = N` for the playback renderer;
**direct-datafile first**, built on a shared `helpers/transcript_sim.py`
core, with the playback renderer added right after on the same core;
tag-size classification defaults to today's `bin/client_local_config.py`
with a `--config` override; notes included from the start (in the
datafile output -- the playback output stays scoped to tags in/out +
registrations, per the original ask).

Built:

- `helpers/transcript_sim.py` -- the parser/simulator core described in
  sections 2-4 above (no TagTracker import dependency; it's a
  standalone state machine over the stable confirmation-line patterns),
  plus the tag-canonicalization helpers (`canonical_tagid`,
  `parse_tagids_str`) both renderers below share.
- `helpers/transcript_to_datafile.py` -- the direct-datafile renderer.
  Classifies tags via `--config` (exec'd standalone, like
  client_base_config.py's own `from client_local_config import *`, but
  without its import-time side effects); writes the current JSON
  datafile shape; `--dry-run`, `--force`,
  `--date`/`--time-open`/`--time-closed`/`--site-name`/`--site-handle`
  overrides, `--unknown-tag-size`, `--no-notes`, and a best-effort
  `--verify` round-trip load through the real `TrackerDay.load_from_file()`
  after writing.
- `helpers/transcript_to_playback.py` -- the playback-command renderer.
  Groups same-timestamp, same-direction tags onto one `in`/`out` line
  (tiebreaking `out` before `in` at an identical timestamp, so a
  same-minute flip/reuse checks a tag out before checking it back in);
  appends a single final `reg = N` (per the decision above -- no
  per-change reg lines); prints to stdout by default (clean, safe to
  pipe straight into `tagtracker.py`) or `--out FILE`; `--annotate` adds
  `#`-prefixed date/hours/warning context for a human reader instead.

### Validation against real data, and two bugs it caught

Four transcript dates (2026-09-09, -11, -12, -18) happen to have a real
datafile already sitting in `data/`. Those turned out to be **mid-day
snapshots**, not end-of-day finals (e.g. the 2026-09-09 file's newest
timestamp is 14:45 despite the transcript running to 19:46, and its
mtime is mid-afternoon) -- so a straight diff isn't meaningful. Restricting
the comparison to events at-or-before each real file's own latest
timestamp, 2026-09-09 and 2026-09-12 matched **exactly** (226 and 71
visits respectively, down to the minute). The other two had small,
fully-explained diffs: a tag whose check-in time was `edit`-ed, and a tag
whose check-in/check-out were later `delete`-d, both *after* the
snapshot's cutoff -- i.e. the real snapshot correctly predates those
corrections, and the simulator correctly reflects the final, corrected
state, which is what it's for. Registration-count "mismatches" were the
same story (registrations climbed later in the day, after the snapshot).

Running all 168 transcripts end-to-end (zero crashes) surfaced two real
bugs, both fixed:

1. **Suspend confirmation wording**: most of the corpus prints
   `TAG  is suspended (marked as unavailable until tomorrow)`, not the
   `TAG is now suspended` form I'd sampled first -- missing it meant a
   suspend/unsuspend pair didn't occupy the undo slot the way the real
   app does, so a later `Undoing:` in the same file restored the wrong
   thing. Fixed by widening the pattern (and anchoring it to end-of-line,
   so it doesn't also catch the unrelated `TAG is suspended; release it
   (UNSUSPEND) before unretiring` RETIRE-error message).
2. **Mid-transcript restarts**: several transcripts contain more than one
   `exit` followed by a fresh banner/hours-dialogue -- i.e. the operator
   restarted the program mid-day. The undo/redo slot is in-memory only in
   the real app and does not survive a restart, but the simulator was
   carrying it forward across the restart boundary. Fixed by clearing
   both slots whenever the `Editing ... (YYYY-MM-DD).` banner line is
   seen again after the first time.

### Known, accepted limitation

A tag already checked in from a *previous* day (shown in the transcript
as "N tags left suspended/onsite as of close of business ...") and then
checked out partway through the current transcript will log a
"checked out with no prior visit on record" warning and that checkout is
dropped, since the simulator only has visibility into the one transcript
it's given. Cross-day state isn't modelled; this showed up twice in the
168-file corpus. Worth a follow-up (e.g. seeding from the previous day's
datafile, if present) if it turns out to matter in practice.
