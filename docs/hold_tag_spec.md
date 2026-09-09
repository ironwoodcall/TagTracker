# HOLD: marking tags unavailable for lockup leftovers — Design Spec

Status: draft, not yet implemented. Written for review/edit before
implementation begins (on a new branch, off `feat/593/undo`). Originates from
a GitHub issue asking for a way to mark tags "in a state that reports as
neither in nor out nor retired nor unused."

## Goal

Some bikes are left in the lockup overnight (not picked up at close) and are
still sitting on their tags the next morning. Those tags are physically
unavailable for a new customer that day, but they are not retired — they'll
become normal, usable tags again the moment the leftover bike is picked up
(same day) or at the start of the next day regardless. There is currently no
way to represent this: a tag is only ever `UNUSED`, `IN_USE`, `DONE`, or
`RETIRED`.

Add a fifth per-tag status, `HELD`, and a single toggle command, `hold`, that
an operator uses manually at the start of the day (and, less often, mid-day
if a leftover bike gets picked up) to mark/unmark specific tags. There is
deliberately no automation here — nothing infers which tags are held from
anything else; the operator decides, on the day, tag by tag.

**Naming.** Deliberately not "leftover" anywhere in code, comments, or
user-facing text — that word is already taken by the existing
`leftovers`/`left`/`l` command ([tt_commands.py:273](../tt_commands.py#L273)),
which reports bikes *currently checked in* (on-site today), an unrelated
concept. This feature uses `hold`/`HELD`/`Hd` throughout.

## Command

New `CmdKeys.CMD_HOLD` in [tt_commands.py](../tt_commands.py), alongside the
other tag-list commands (`retire` at
[tt_commands.py:309](../tt_commands.py#L309) is the closest existing
pattern):

```
CmdKeys.CMD_HOLD: CmdConfig(
    invoke=["hold", "h"],
    arg_configs=[ArgConfig(ARG_TAGS, optional=False, prompt="Hold/release what tag(s)? ")],
),
```

- **Toggle, not a pair of commands.** One `hold` command flips each named
  tag independently: `UNUSED → HELD` or `HELD → UNUSED`. There is no
  separate `unhold`.
- **Batch, per-tag outcome.** `hold bg3 wa7` where `bg3` is `UNUSED` and
  `wa7` is currently `IN_USE`: hold `bg3`, print a one-line refusal for
  `wa7`, don't abort the batch. Same shape as `tt_retire.py`'s per-tag
  `TagOutcome` handling.
- **No confirmation prompt.** Unlike `retire`/`unretire` (which rewrite
  `client_local_config.py` and warn "Use this command with care!"), `hold`
  only touches in-memory/datafile state for the current day and is meant to
  be a quick, low-ceremony morning task. No `YES` confirmation step.

**Letter reassignment.** Taking `h` for `hold` means `CMD_HELP` at
[tt_commands.py:262](../tt_commands.py#L262) (currently
`invoke=["help", "h"]`) loses its one-letter shortcut. Decision: just drop
it — `help` typed in full is not a real burden, and no other free letter
(`b`, `j`, `k`, `p`, `r`, `w`, `y`, `z`) has an obvious mnemonic tie to
"help." `CMD_HELP` becomes `invoke=["help"]`.

## Tag state model — [common/tt_biketag.py](../common/tt_biketag.py)

Add `BikeTag.HELD` alongside `UNUSED`/`IN_USE`/`DONE`/`RETIRED`
([tt_biketag.py:48](../common/tt_biketag.py#L48)).

- `_test_time_in()` ([:102](../common/tt_biketag.py#L102)): add an early-out
  parallel to the existing `RETIRED` check at
  [:118](../common/tt_biketag.py#L118):
  `if self.status == self.HELD: return f"Tag {self.tagid} is held (not available today)."`
- `status_as_at()` ([:234](../common/tt_biketag.py#L234)): add a `HELD`
  early-return next to the `RETIRED` one — like `RETIRED`, `HELD` is a
  static status, not derived from visits.
- `lint_check()` ([:274](../common/tt_biketag.py#L274)): treat `HELD` like
  `UNUSED`/`RETIRED` in the "must have no visits" branch at
  [:286](../common/tt_biketag.py#L286).

## TrackerDay — [common/tt_trackerday.py](../common/tt_trackerday.py)

New method, mirroring `retire_tag`/`unretire_tag`
([:495](../common/tt_trackerday.py#L495)):

```python
def toggle_held(self, tagid: TagID) -> bool:
    """Toggle tagid between UNUSED and HELD. Returns True if changed."""
    biketag = self.biketags.get(tagid)
    if not biketag or biketag.status not in {BikeTag.UNUSED, BikeTag.HELD}:
        return False
    biketag.status = BikeTag.HELD if biketag.status == BikeTag.UNUSED else BikeTag.UNUSED
    return True
```

The `status not in {UNUSED, HELD}` guard is the whole rule set the issue
asked for, in one place:

- A checked-in (`IN_USE`) tag can't be held — must be checked out first.
- A `DONE` tag can't be held — if it was used today, "leftover from a prior
  day" no longer applies to it.
- A `RETIRED` tag can't be held, and (see below) a `HELD` tag can't be
  retired/unretired — the two states are mutually exclusive.

`all_usable_tags()` ([:531](../common/tt_trackerday.py#L531)) gets `HELD`
added to its exclusion, alongside `RETIRED`. This is the single point that
feeds `check_tagid_usable()`
([tt_main_bits.py:254](../tt_main_bits.py#L254)) — the one gate already
shared by `in`/`out`/`inout`/`edit`/`delete`/`flip`. Excluding `HELD` there
blocks all of those commands on a held tag for free, with an appropriate
message (mirroring the existing retired-tag branch at
[tt_main_bits.py:265](../tt_main_bits.py#L265)):

```python
if tagid in today.held_tagids:
    msg = f"Tag {tagid} is held."
```

No other tag-mutating command needs its own guard.

## Interaction with retire/unretire — [tt_retire.py](../tt_retire.py)

Add a guard to `_evaluate_retire()` ([:286](../tt_retire.py#L286)) and
`_evaluate_unretire()` ([:328](../tt_retire.py#L328)), parallel to their
existing `RETIRED` handling: if `biketag.status == BikeTag.HELD`, refuse
with a message like `"is held; release it from hold before retiring"` and
do not mark it actionable. A held tag must be released (`hold` again) before
it can be retired or unretired.

## Data file — [common/tt_trackerday.py](../common/tt_trackerday.py) JSON I/O

New key `TOKEN_HELD_TAGIDS = "held_tagids"`, written in `_day_to_json_dict()`
([:720](../common/tt_trackerday.py#L720)) next to `TOKEN_RETIRED_TAGIDS`, and
read in `_day_from_json_dict()` ([:799](../common/tt_trackerday.py#L799)).

**Not config-sourced — this is what makes daily reset free.** Unlike
`retired_tagids`, which a new day seeds from `client_local_config.py`'s
`RETIRED_TAGS`, `held_tagids` has no config source at all. A brand-new day's
`TrackerDay` therefore starts with zero held tags with no extra reset logic
needed; a same-day restart re-reads whatever was held from that day's own
already-saved datafile, so the state survives a crash/relaunch within the
day but never carries into tomorrow.

**Read defensively.** Use `data.get(TOKEN_HELD_TAGIDS, [])` rather than
`data[TOKEN_HELD_TAGIDS]`, so datafiles written before this feature existed
(no such key) load without error.

**Schema/DB impact: none required, some optional.**
[common/tagtracker_schema_v1.0.0.json](../common/tagtracker_schema_v1.0.0.json)
has no top-level `"additionalProperties": false`, so an old reader/validator
that doesn't know about `held_tagids` won't reject a datafile that has it.
[database/db_from_datafile.py](../database/db_from_datafile.py) goes through
`TrackerDay.load_from_file()` and only reads specific known keys, so it will
silently ignore `held_tagids` until/unless someone chooses to teach the DB
side about the new status — that's optional follow-on work, not a blocker
for this feature. Still worth adding the key to the schema's `properties`
(not to `required`) for documentation completeness.

## Reports

- **`tags`** ([tt_tag_inv.py](../tt_tag_inv.py)):
  - New symbol `TAG_INV_HELD = ("Hd", k.WARNING_STYLE)` next to
    `TAG_INV_RETIRED` at [:55](../tt_tag_inv.py#L55).
  - New branch in the status→symbol chain at
    [:129](../tt_tag_inv.py#L129):
    `elif tag_status == this_biketag.HELD: tag_states.append(TAG_INV_HELD)`.
  - Update the key line at [:89](../tt_tag_inv.py#L89) to mention `'Hd'=Held`.
  - New `held_report()` alongside `retired_report()`
    ([:157](../tt_tag_inv.py#L157)), same shape (list held tags grouped by
    colour), called from `tags_config_report()`
    ([:174](../tt_tag_inv.py#L174)) right after `retired_report(day)`.
- **`audit`** ([tt_audit_report.py](../tt_audit_report.py)): the on-site
  matrix already overlays a `retired_tag_str` marker (`" ●"`,
  [:35](../tt_audit_report.py#L35)) into cells for retired tags at
  [:160](../tt_audit_report.py#L160) and [:182](../tt_audit_report.py#L182).
  Add a second marker (e.g. `" ○"`) for held tags, checked against a new
  `day.held_tagids` set the same way, and mention both markers in the
  header key at [:146](../tt_audit_report.py#L146). Held tags have no
  visits, so they only ever appear as this static marker — no change needed
  to `inout_summary()`.
- **`query`** ([tt_reports.py:465](../tt_reports.py#L465)): one more branch
  next to the existing `RETIRED` one at
  [:476](../tt_reports.py#L476):
  `elif biketag.status == biketag.HELD: msgs = [f"Tag {tagid} is held (not available today)."]`.

## Undo/redo — [tt_undo.py](../tt_undo.py)

`retire`/`unretire` are excluded from the generic undo mechanism
specifically because they also rewrite `client_local_config.py`
([tt_undo.py:47](../tt_undo.py#L47)). `hold` never touches config — it's a
pure `biketag.status` flip, exactly the shape `_state_key()`
([:85](../tt_undo.py#L85)) already snapshots. Add `CmdKeys.CMD_HOLD` to
`TAG_UNDOABLE_COMMANDS` ([:55](../tt_undo.py#L55)) and give `build_label()`
([:93](../tt_undo.py#L93)) a one-line branch (label like `"hold bg3"`). This
gets `undo`/`redo` on `hold` essentially for free, which is worth doing
since it's the kind of quick manual toggle where a mis-typed tag is likely.

## Help text — [tt_help.py](../tt_help.py)

- New entry documenting `hold`/`h`: what it does, that it's a toggle, that a
  held tag can't be checked in/out/edited/deleted/retired until released,
  and that held tags reset to none at the start of each new day.
- Update the `help`/`CMD_HELP` entry's shortcut column (now `help` only, no
  `h`).
- Mention `Hd` in the `tags`/`audit` report help/key text.

## Task list

1. `BikeTag.HELD` constant + the three method changes in
   [common/tt_biketag.py](../common/tt_biketag.py) (`_test_time_in`,
   `status_as_at`, `lint_check`).
2. `TrackerDay.toggle_held()`, `held_tagids` set/field, `HELD` added to
   `all_usable_tags()`'s exclusion, in
   [common/tt_trackerday.py](../common/tt_trackerday.py).
3. JSON read/write: `TOKEN_HELD_TAGIDS`, `.get(..., [])` on read, included
   in `_day_to_json_dict()`.
4. Schema: add `held_tagids` to
   [tagtracker_schema_v1.0.0.json](../common/tagtracker_schema_v1.0.0.json)'s
   `properties` (not `required`).
5. `CmdKeys.CMD_HOLD` + `CmdConfig` in [tt_commands.py](../tt_commands.py);
   drop `h` from `CMD_HELP`'s `invoke`.
6. Dispatch branch in `process_command()`
   ([tt_process_command.py](../tt_process_command.py)) calling a new
   `hold_command()`/similar, per-tag toggle + per-tag message, batch-tolerant
   like `tt_retire.py`.
7. Guard clauses in `_evaluate_retire()`/`_evaluate_unretire()`
   ([tt_retire.py](../tt_retire.py)) refusing a `HELD` tag.
8. `check_tagid_usable()` message branch for held tags
   ([tt_main_bits.py](../tt_main_bits.py)).
9. Report changes: `TAG_INV_HELD` + key line + `held_report()` in
   [tt_tag_inv.py](../tt_tag_inv.py); marker + key line in
   [tt_audit_report.py](../tt_audit_report.py); `query` branch in
   [tt_reports.py](../tt_reports.py).
10. Undo/redo wiring: add `CMD_HOLD` to `TAG_UNDOABLE_COMMANDS`, label
    support in `build_label()` ([tt_undo.py](../tt_undo.py)).
11. Help text in [tt_help.py](../tt_help.py); changelog entry.
12. Tests: toggle both directions, refusal from `IN_USE`/`DONE`/`RETIRED`,
    `all_usable_tags()` exclusion blocks `in`/`out`/`edit`/`delete`/`flip`,
    retire/unretire refusal on a held tag, datafile round-trip (including
    loading an old datafile with no `held_tagids` key), a new day starting
    with zero held tags, `tags`/`audit`/`query` report output, undo/redo on
    `hold` (including a redo re-deriving the correct toggle direction
    against restored state).

## Open items / assumptions to verify during implementation

- Confirm the exact audit-matrix marker character for held tags (proposed
  `" ○"`, distinct from retired's `" ●"`) doesn't collide visually with any
  existing report symbol.
- Confirm whether `held_tagids` should be a `set[TagID]` field on
  `TrackerDay` (mirroring `retired_tagids`) rather than derived purely from
  `biketag.status` scans — recommend the explicit set, matching the existing
  `retired_tagids` pattern, since several call sites (audit matrix,
  `held_report()`) want the set directly rather than filtering all
  `biketags.values()`.
- Decide whether `hold` should be blocked outright while the operator is
  mid-batch on a tag that has *never* appeared in `today.biketags` (unknown
  tag) — should read the same as any other command's "no tag X available
  today" message, no new behavior needed here, just confirm during testing.
