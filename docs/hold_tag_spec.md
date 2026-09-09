# HOLD/UNHOLD: marking tags unavailable for reuse today — Design Spec

Status: implemented on `feat/594/hold-unhold`, verified via
`helpers/test_hold.py`. Not yet committed/merged. Originates from a
GitHub issue asking for a way to mark tags "in a state that reports as
neither in nor out nor retired nor unused," and extended during design
review to cover a second use case (see "Two use cases" below).

## Goal

**Use case 1 — overnight lockup leftovers.** Some bikes are left in the
lockup overnight (not picked up at close) and are still sitting on their
tags the next morning. Those tags are physically unavailable for a new
customer that day, but they are not retired — they'll become normal, usable
tags again once the leftover bike is picked up (same day) or, regardless,
at the start of the next day. Before this feature, there's no way to
represent this: a tag is only ever `UNUSED`, `IN_USE`, `DONE`, or `RETIRED`.

**Use case 2 — mid-day set-aside.** A bike is checked in and later checked
out (`DONE`), but for some physical reason (e.g. no kickstand, so it was
leaned against the enclosure fence rather than racked in sequence) it gets
pulled aside and won't be reused for the rest of the day — placed in a
bucket rather than back into circulation. An operator may want to mark that
tag's status explicitly so that later, scanning the normal tag-status
displays, its absence from the "available for reuse" grouping doesn't read
as a data gap or a mistake.

Both cases want the same thing: a way to mark a tag "not available for use
right now, but not retired either," discovered and applied manually by the
operator on the day, with no automation inferring it from anything else.
Both are handled by one mechanism: a `held` flag plus a pair of commands,
`hold` and `unhold`.

**Naming.** Deliberately not "leftover" anywhere in code, comments, or
user-facing text — that word is already taken by the existing
`left`/`l` command (formerly `leftovers`/`leftover`/`left`/`l` — see
`docs/to-do.txt` item C6, a related low-effort cleanup to rename that
command's remaining internal "leftover" vocabulary to "left"/"remaining"),
which reports bikes *currently checked in* (on-site today) — an unrelated
concept. This feature uses `hold`/`held`/`unhold`/`Hd` throughout, and the
two real-world reasons above are never named in the UI (a tag is just
"held," regardless of which of the two situations produced it).

## Model: `held` is an orthogonal flag, not a fifth status value

**This is the key design decision, revised once during review — worth
stating explicitly since it's not the obvious first design.** An earlier
draft of this spec added `BikeTag.HELD` as a fifth exclusive value
alongside `UNUSED`/`IN_USE`/`DONE`/`RETIRED`, mirroring how `RETIRED`
already works. That works fine for `RETIRED`, because retiring only ever
applies to `UNUSED` tags — there's nothing underneath to preserve, so
un-retiring can unconditionally restore to `UNUSED`. It does **not** work
once holding needs to reach `DONE` tags (use case 2): a held `DONE` tag
must remember that it's truthfully `DONE` — has real visit history, is
eligible for reuse — so that releasing the hold later restores it correctly
rather than resetting it to a fresh, never-used `UNUSED` tag.

The fix: add `BikeTag.held: bool = False` as a field alongside `status`,
not a value of it. `status` keeps meaning exactly what it always has
(`UNUSED`/`IN_USE`/`DONE`/`RETIRED`, and all of `lint_check()`'s existing
visit-consistency assumptions about it stay true and **unmodified**); `held`
is a separate, orthogonal marker layered on top. Because `status` is never
overwritten while a tag is held, there is nothing to "restore" on unhold —
no visit-scanning, no extra saved-previous-status field. Releasing a hold
is just `held = False`; whatever `status` truthfully already is (`DONE` or
`UNUSED`) is simply revealed again, because it was never touched.

## Commands — [tt_commands.py](../tt_commands.py) / [tt_process_command.py](../tt_process_command.py)

Two explicit commands, not a toggle — consistent with every other paired
opposite already in the tool (`in`/`out`, `retire`/`unretire`,
`note deactivate`/`reactivate`, `undo`/`redo`). A toggle also becomes
ambiguous in intent once `DONE` tags are in scope (`hold bg3` on an
already-held tag — release it, or a no-op confirming it's held?), which
explicit verbs avoid entirely.

```
CmdKeys.CMD_HOLD: CmdConfig(
    invoke=["hold"],
    arg_configs=[ArgConfig(ARG_TAGS, optional=False, prompt="Hold what tag(s)? ")],
),
CmdKeys.CMD_UNHOLD: CmdConfig(
    invoke=["unhold", "unh"],
    arg_configs=[ArgConfig(ARG_TAGS, optional=False, prompt="Unhold (release) what tag(s)? ")],
),
```

- **No single-letter alias for `hold`, and `help` loses its own.** `hold`
  requires the full word — no `h`. `CMD_HELP` at
  [tt_commands.py:262](../tt_commands.py#L262) (currently
  `invoke=["help", "h"]`) also drops its `h` shortcut, becoming
  `invoke=["help"]`. Decision: `h` is unrecognized as a command entirely,
  for either — `help` typed in full isn't a real burden, and reserving `h`
  for one of the two would just relocate the ambiguity rather than remove
  it.
- **`unhold` or `unh`, not `un`.** `un`- has quietly become a real
  word-forming prefix in this tool (`unretire`, now `unhold`), which
  clashes in spirit with `undo` also owning bare `un` as a short alias
  ([tt_commands.py:328](../tt_commands.py#L328),
  `invoke=["undo", "u", "un"]`) — a user could plausibly guess `un` as
  shorthand for "reverse whatever I'm holding" and get `undo` instead
  (which takes no arguments, so `un a5` doesn't fail cleanly either).
  Resolution: drop `"un"` from `undo`'s `invoke` list, keeping only `u`
  (uncontested — nothing else wants it, so this isn't a new special case,
  just removing an alias nothing actually needed). `undo` becomes
  `invoke=["undo", "u"]`; bare `un` is unrecognized for everyone. This
  matches the precedent `unretire` already set by having no bare
  `un`-family shortcut of its own. `unhold`'s short form is `unh`:
  `invoke=["unhold", "unh"]`.
- **Prompts for tags if omitted, like every other tag-list command.**
  `ArgConfig(ARG_TAGS, optional=False, prompt=...)` above is the same
  mechanism `retire`/`edit`/`delete`/etc. already use
  ([tt_commands.py:230](../tt_commands.py#L230),
  [:242](../tt_commands.py#L242)) — typing bare `hold` or `unhold` with no
  tags prompts for them (`"Hold what tag(s)? "` / `"Unhold (release) what
  tag(s)? "`) rather than erroring or silently doing nothing. No special
  handling needed; this falls out of using the standard `ArgConfig` shape.
- **Batch, per-tag outcome.** `hold bg3 wa7` where `bg3` is eligible and
  `wa7` is `IN_USE`: hold `bg3`, print a one-line refusal for `wa7`, don't
  abort the batch. Same shape as `tt_retire.py`'s per-tag `TagOutcome`
  handling — worth a small parallel module (`tt_hold.py`) with a shared
  per-tag evaluator and two thin entry points, `hold()`/`unhold()`, rather
  than duplicating the loop twice. Notably simpler than `tt_retire.py`,
  since neither direction touches `client_local_config.py` or needs a `YES`
  confirmation step — this is meant to be a quick, low-ceremony action.

## Tag state model — [common/tt_biketag.py](../common/tt_biketag.py)

New field: `self.held: bool = False`, set in `__init__`.

New methods on `BikeTag`, called by the `TrackerDay`-level methods below:

```python
def hold(self) -> bool:
    """Mark this tag held. Only valid from UNUSED or DONE. Returns True if changed."""
    if self.status not in {self.UNUSED, self.DONE} or self.held:
        return False
    self.held = True
    return True

def unhold(self) -> bool:
    """Release a held tag. Returns True if changed."""
    if not self.held:
        return False
    self.held = False
    return True
```

The `status not in {UNUSED, DONE}` guard on `hold()` is the whole rule set
both use cases need:

- An `IN_USE` tag can't be held — must be checked out first.
- A `RETIRED` tag can't be held (and, symmetrically, a held tag can't be
  retired/unretired — see below).
- A `DONE` tag *can* be held (use case 2) — and unlike the discarded
  fifth-status design, this needs no special-casing: `status` stays `DONE`
  the whole time.

Other method changes:

- `_test_time_in()` ([:102](../common/tt_biketag.py#L102)): add an
  early-out **in addition to** the existing status checks (not replacing
  them, since `status` may truthfully be `DONE`, which would otherwise be
  perfectly eligible for reuse):
  `if self.held: return f"Tag {self.tagid} is held."`
- `status_as_at()` ([:234](../common/tt_biketag.py#L234)): add a `held`
  check at the same priority tier as the existing `RETIRED` early-return —
  i.e. checked **before** the visit-derived logic:
  `if self.held: return self.HELD` (a new reportable pseudo-status,
  distinct from the untouched `status` field). Everything downstream that
  already classifies tags via `status_as_at()` — `tags_done()`, the `tags`
  matrix, the audit report, `query` — automatically stops treating a held
  tag as `DONE`/`UNUSED`, with no further per-call-site logic needed.
- `lint_check()` ([:274](../common/tt_biketag.py#L274)): **no change.** It
  inspects `status` directly, which stays truthful and internally
  consistent (visits present iff `IN_USE`/`DONE`) regardless of `held`.

**Stats are unaffected, on purpose.** `num_bikes_parked()`/
`num_bikes_returned()` ([tt_trackerday.py:962](../common/tt_trackerday.py#L962),
[:989](../common/tt_trackerday.py#L989)) scan `visit` records directly, not
`status_as_at()`. A held tag's earlier completed visit still counts
normally in the day's arrival/departure totals — holding doesn't erase that
the bike came and went, it only says "don't hand this tag out again today."

## TrackerDay — [common/tt_trackerday.py](../common/tt_trackerday.py)

New methods, mirroring `retire_tag`/`unretire_tag`
([:495](../common/tt_trackerday.py#L495)) but delegating the eligibility
check to `BikeTag`:

```python
def hold_tag(self, tagid: TagID) -> bool:
    biketag = self.biketags.get(tagid)
    return bool(biketag) and biketag.hold()

def unhold_tag(self, tagid: TagID) -> bool:
    biketag = self.biketags.get(tagid)
    return bool(biketag) and biketag.unhold()

def tags_held(self) -> list[TagID]:
    """List of tagids currently held."""
    return [b.tagid for b in self.biketags.values() if b.held]
```

`all_usable_tags()` ([:531](../common/tt_trackerday.py#L531)) gets
`and not t.held` added to its filter, alongside the existing
`!= RETIRED`. This is the single point that feeds `check_tagid_usable()`
([tt_main_bits.py:254](../tt_main_bits.py#L254)) — the one gate already
shared by `in`/`out`/`inout`/`edit`/`delete`/`flip`. Excluding held tags
there blocks all of those commands on a held tag for free, including
correctly refusing to reuse a held `DONE` tag, with an appropriate message
mirroring the existing retired-tag branch at
[tt_main_bits.py:265](../tt_main_bits.py#L265):

```python
if tagid in [b.tagid for b in today.biketags.values() if b.held]:
    msg = f"Tag {tagid} is held."
```

No other tag-mutating command needs its own guard.

**Load-time reconciliation.** `harmonize_biketags()`
([:358](../common/tt_trackerday.py#L358)) already reconciles `status`
against config on every load; add one small analogous check for `held`: if
a loaded tag has `held=True` but `status` is `IN_USE` or `RETIRED` (should
never happen from normal operation, but a hand-edited or stale datafile
could produce it), clear `held` and record a fix message, the same shape as
the existing retired-tag reconciliation there.

## Interaction with retire/unretire — [tt_retire.py](../tt_retire.py)

Add a guard to `_evaluate_retire()` ([:286](../tt_retire.py#L286)) and
`_evaluate_unretire()` ([:328](../tt_retire.py#L328)): if `biketag.held`,
refuse with a message like `"is held; release it before retiring"` and do
not mark it actionable. A held tag must be released (`unhold`) before it
can be retired or unretired; symmetrically, `hold()`'s own
`status not in {UNUSED, DONE}` check already refuses a `RETIRED` tag.

## Data file — [common/tt_trackerday.py](../common/tt_trackerday.py) JSON I/O

New key `TOKEN_HELD_TAGIDS = "held_tagids"`, written in `_day_to_json_dict()`
([:720](../common/tt_trackerday.py#L720)) next to `TOKEN_RETIRED_TAGIDS`
(sourced from `TrackerDay.tags_held()`), and read in
`_day_from_json_dict()` ([:799](../common/tt_trackerday.py#L799)),
applying `held = True` to each named tag's `BikeTag` after
`initialize_biketags()` builds them.

**Not config-sourced — this is what makes daily reset free.** Unlike
`retired_tagids`, which a new day seeds from `client_local_config.py`'s
`RETIRED_TAGS`, `held_tagids` has no config source at all. A brand-new
day's `TrackerDay` therefore starts with zero held tags with no extra reset
logic needed; a same-day restart re-reads whatever was held from that
day's own already-saved datafile, so the state survives a crash/relaunch
within the day but never carries into tomorrow.

**Read defensively.** Use `data.get(TOKEN_HELD_TAGIDS, [])` rather than
`data[TOKEN_HELD_TAGIDS]`, so datafiles written before this feature existed
(no such key) load without error.

**Schema/DB impact: none required, some optional.**
[common/tagtracker_schema_v1.0.0.json](../common/tagtracker_schema_v1.0.0.json)
has no top-level `"additionalProperties": false`, so an old
reader/validator that doesn't know about `held_tagids` won't reject a
datafile that has it.
[database/db_from_datafile.py:748](../database/db_from_datafile.py#L748)
loads via `TrackerDay.load_from_file(filename)` with schema validation
off by default, and `_day_from_json_dict()` only ever reads by known,
explicit key (`data[TOKEN_DATE]`, etc.) — there's no `for key in data`
anywhere in the load path, so an unrecognized key is never even looked at,
let alone rejected. A datafile with `held_tagids` in it loads through the
current DB loader exactly as if the key weren't there: the held tags
simply don't show up in the database. Nothing needs to change for
*safety*. Still worth adding the key to the schema's `properties` (not
`required`) for documentation completeness. Teaching the DB/season-report
side to actually *know about* held tags (e.g. so reporting doesn't quietly
undercount "available" tags on days with holds) is optional follow-on
work, not required for this feature.

## Reports

- **`tags`** ([tt_tag_inv.py](../tt_tag_inv.py)):
  - New symbol `TAG_INV_HELD = ("Hd", k.WARNING_STYLE)` next to
    `TAG_INV_RETIRED` at [:55](../tt_tag_inv.py#L55).
  - New branch in the status→symbol chain at
    [:129](../tt_tag_inv.py#L129):
    `elif tag_status == this_biketag.HELD: tag_states.append(TAG_INV_HELD)`
    — this falls out of the `status_as_at()` overlay above with no other
    change, and covers both use cases (a held `UNUSED` tag and a held
    `DONE` tag both simply show `Hd` here instead of `-` or `Ou`).
  - Update the key line at [:89](../tt_tag_inv.py#L89) to mention
    `'Hd'=Held`.
- **`audit`** ([tt_audit_report.py](../tt_audit_report.py)): a **third**
  grid, parallel to the existing "Bikes still onsite"
  ([:144](../tt_audit_report.py#L144)) and "Tags potentially available for
  re-use" ([:170](../tt_audit_report.py#L170)) sections — not a marker
  squeezed into either existing grid (an earlier draft of this spec
  proposed overlaying a held-marker into the re-use grid; a dedicated
  section is clearer and needs no such overlay, since held tags are
  already excluded from that grid for free via the `status_as_at()`
  change above — a blank cell there is now simply correct, because the
  tag is enumerated in its own section instead):

  ```
  Tags held, marked unavailable for (re)use today (N tags)
  <prefix grid, same rendering as the existing two: tag number shown if
   held, retired_tag_str if retired, blank otherwise>
  ```

  Built from `day.tags_held()`, grouped by prefix the same way
  `prefixes_on_hand`/`prefixes_returned_out` are built at
  [:131](../tt_audit_report.py#L131)-132. Shown only when there's at least
  one held tag (mirroring `retired_report()`'s empty-list skip in
  [tt_tag_inv.py:159](../tt_tag_inv.py#L159)), so an ordinary day's audit
  is unchanged.

  **Known limitation to document, not fix:** `hold`/`unhold` don't record
  a timestamp (there's no "held as of HH:MM" concept — a tag just is or
  isn't held, right now). The rest of `audit`'s sections are computed
  *as of* an optional time argument (`as_of_when`), reconstructing
  historical state. The held section can't do that — it always reflects
  *current* held state regardless of what time the audit report is run
  for. Worth a one-line caveat in the report/help text so a
  `audit 09:00` run late in the day doesn't look like it's misreporting.
- **`query`** ([tt_process_command.py:466](../tt_process_command.py#L466)): can't be a
  simple additional `elif` in the existing mutually-exclusive
  `UNUSED`/`RETIRED`/"show visits" chain, because a held `DONE` tag needs
  **both** a "this tag is held" note **and** its real visit history (when
  it came in, when it left) — genuinely useful information for an
  operator asking about that specific tag. Restructure: check
  `biketag.held` first and prepend a note if so, then fall through to the
  existing "list visits if any" logic regardless (a held `UNUSED` tag has
  no visits to list, so it naturally only prints the held note).

## Undo/redo — [tt_undo.py](../tt_undo.py)

`retire`/`unretire` are excluded from the generic undo mechanism
specifically because they also rewrite `client_local_config.py`
([tt_undo.py:47](../tt_undo.py#L47)). Neither `hold` nor `unhold` touches
config — each is a pure `biketag.held` flip, exactly the shape
`_state_key()` ([:85](../tt_undo.py#L85)) already snapshots (it snapshots
the whole `BikeTag`, so it needs no change to also capture `held`). Add
**both** `CmdKeys.CMD_HOLD` and `CmdKeys.CMD_UNHOLD` to
`TAG_UNDOABLE_COMMANDS` ([:55](../tt_undo.py#L55)) — unlike
`retire`/`unretire`, which are excluded as a pair, `hold`/`unhold` can be
included individually, same as `in`/`out` are. Give `build_label()`
([:93](../tt_undo.py#L93)) a branch for each (label like `"hold bg3"` /
`"unhold bg3"`).

## Help text — [tt_help.py](../tt_help.py)

- New entries for `hold` (no short alias) and `unhold`/`unh`: what each does, that a
  held tag can't be checked in/out/edited/deleted/retired until released,
  that holding reaches both a never-used tag and an already-`DONE` tag,
  and that held tags reset to none at the start of each new day.
- Update the `help`/`CMD_HELP` entry's shortcut column (now `help` only,
  no `h`).
- Mention `Hd` in the `tags`/`audit` report help/key text, and the
  "reflects current state, not as-of-time" caveat for audit's held
  section.

## Task list

1. `BikeTag.held` field + `hold()`/`unhold()` methods +
   `_test_time_in()`/`status_as_at()` changes in
   [common/tt_biketag.py](../common/tt_biketag.py). Confirm `lint_check()`
   genuinely needs no change.
2. `TrackerDay.hold_tag()`/`unhold_tag()`/`tags_held()`, `HELD` added to
   `all_usable_tags()`'s exclusion, load-time reconciliation in
   `harmonize_biketags()`, in
   [common/tt_trackerday.py](../common/tt_trackerday.py).
3. JSON read/write: `TOKEN_HELD_TAGIDS`, `.get(..., [])` on read, included
   in `_day_to_json_dict()`.
4. Schema: add `held_tagids` to
   [tagtracker_schema_v1.0.0.json](../common/tagtracker_schema_v1.0.0.json)'s
   `properties` (not `required`).
5. `CmdKeys.CMD_HOLD`/`CMD_UNHOLD` + `CmdConfig` entries in
   [tt_commands.py](../tt_commands.py); drop `h` from `CMD_HELP`'s
   `invoke`; drop `un` from `CMD_UNDO`'s `invoke` (becomes
   `["undo", "u"]`).
6. New `tt_hold.py`: shared per-tag evaluator + `hold()`/`unhold()` entry
   points, batch-tolerant like `tt_retire.py` but without its
   confirmation/config-rewrite machinery. Dispatch branches in
   `process_command()` ([tt_process_command.py](../tt_process_command.py)).
7. Guard clauses in `_evaluate_retire()`/`_evaluate_unretire()`
   ([tt_retire.py](../tt_retire.py)) refusing a held tag.
8. `check_tagid_usable()` message branch for held tags
   ([tt_main_bits.py](../tt_main_bits.py)).
9. Report changes: `TAG_INV_HELD` + key line in
   [tt_tag_inv.py](../tt_tag_inv.py); new held-tags grid/section (with the
   as-of-time caveat) in [tt_audit_report.py](../tt_audit_report.py);
   restructured `query_command()` in
   [tt_process_command.py](../tt_process_command.py) (query_command lives
   there, not in tt_reports.py -- corrected during implementation).
10. Undo/redo wiring: add `CMD_HOLD`/`CMD_UNHOLD` to
    `TAG_UNDOABLE_COMMANDS`, label support in `build_label()`
    ([tt_undo.py](../tt_undo.py)).
11. Help text in [tt_help.py](../tt_help.py); changelog entry.
12. Tests (`helpers/test_hold.py`, standalone assertion script in the
    style of `helpers/test_undo_redo.py` — no pytest suite in this repo):
    - Hold from `UNUSED`; hold from `DONE`; refused from `IN_USE`/
      `RETIRED`/already-held.
    - Unhold restores visibility of the true underlying status: a
      held-then-unheld `DONE` tag reports as `DONE` (not `UNUSED`), a
      held-then-unheld `UNUSED` tag reports as `UNUSED`.
    - `status_as_at()` returns `HELD` (not `UNUSED`/`DONE`) for a held
      tag, at an arbitrary `as_of_when` — **the single highest-value test
      in this feature**: if this early-return is missing or misordered, a
      held tag silently reports as available everywhere instead of
      erroring, which is the one regression direction that's actually
      bad (every other miss in this feature fails toward "annoyingly
      blocked" or a visible `!?`/error string).
    - `check_tagid_usable()` blocks `in`/`out`/`inout`/`edit`/`delete`/
      `flip` on a held tag (both held-from-`UNUSED` and held-from-`DONE`)
      via the real dispatcher, with the right message.
    - `retire`/`unretire` refuse a held tag; `hold` refuses a retired tag.
    - `num_bikes_parked()`/`num_bikes_returned()` totals are unaffected by
      holding a `DONE` tag (statistics stay based on real visits).
    - JSON round-trip: save → reload preserves `held_tagids` for both
      held-from-`UNUSED` and held-from-`DONE` tags; loading a
      pre-feature datafile (no `held_tagids` key) doesn't error.
    - `harmonize_biketags()` load-time reconciliation clears an
      inconsistent `held` flag (e.g. loaded alongside `RETIRED` status)
      and reports a fix message.
    - A fresh day starts with zero held tags (confirms no config-seeding
      leak).
    - `tags`/`audit`/`query` report output for both held sub-cases,
      including `query` showing both the held note and real visit history
      for a held `DONE` tag.
    - `undo`/`redo` on both `hold` and `unhold`.

## Open items / assumptions to verify during implementation

- Confirm the exact wording for the audit report's held-section time
  caveat, and where it's placed (inline under the heading vs. in help
  text only).
- Confirm whether `hold`/`unhold` should play a distinct sound cue
  (parallel to how `retire`/`unretire` and `undo`/`redo` each have their
  own), or reuse an existing neutral confirmation sound.
- Decide whether `hold` on an already-held tag (or `unhold` on a
  not-held tag) should be a silent no-op or an explicit "already held"/
  "not held" message per tag in the batch output — recommend the latter,
  matching `tt_retire.py`'s existing per-tag-outcome style.
