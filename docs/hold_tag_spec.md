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
  grid, parallel to the existing "Bikes still onsite" and "Tags
  potentially available for re-use" sections:

  ```
  Tags held, marked unavailable for (re-)use today (N tags)
  ```

  Built from `day.tags_held()`, grouped by prefix the same way
  `prefixes_on_hand`/`prefixes_returned_out` already are. Shown only when
  there's at least one held tag, so an ordinary day's audit is unchanged.
  Each grid's *row selection* stays exactly as before (a prefix only gets
  a row if it has a tag of that grid's own category) — a prefix that's
  held-only, say, still won't get a row in the onsite or re-use grids.

  **Revised beyond the original draft, based on a look at real sample
  output:** every *cell* within an already-shown row now displays one of
  five markers — not just retired — via a single shared classification
  (`_draw_tag_grid()`, driven by `BikeTag.status_as_at()`): a tag number
  for that grid's own category, and one of `●`/`○`/`<`/`>`/`-`
  (retired/held/checked-in/checked-out/available) for every other
  category. A cell is truly blank only when there's no tag defined for
  that slot at all — the first pass at this stopped short of that: it
  left `UNUSED` (exists, just not used today) rendering identically to
  "no such tag," which on real output turned out to be most of the grid
  and was genuinely ambiguous; `available_tag_str` (default `" -"`,
  matching the `tags` command's own `TAG_INV_AVAILABLE` symbol) closes
  that gap. A held-`DONE` tag correctly shows the held marker rather than
  the checked-out one in every grid, since `status_as_at()` already
  prioritizes `HELD` over `DONE`. `○` is deliberately drawn from the same
  Unicode block (Geometric Shapes, U+25A0-25FF) as the already-in-production
  `●` (U+25CF) — same East Asian Width category, so whatever
  single-column-width behaviour `●` already gets from a given
  terminal/font, `○` should get identically; still worth an eyeball check
  in the actual deployment terminal. `<`/`>`/`-` need no such reasoning —
  plain ASCII, and `<`/`>` are already this app's own convention for
  in/out (see `print_tag_inout()`'s `"<---in---"`/`"---out--->"`).
  `tt_publish.py`'s non-terminal destination passes ASCII fallbacks for
  the one non-ASCII marker (`retired_tag_str="<>"` already did;
  `held_tag_str="()"` added to match) and richer 2-letter codes for
  in/out (`in_use_tag_str="In"`, `done_tag_str="Ou"` added to match — the
  latter two reusing the `tags` command's own `In`/`Ou` codes for
  consistency); `available_tag_str` needed no override there since its
  default is already plain ASCII.

  **Known limitation, documented not fixed:** `hold`/`unhold` don't record
  a timestamp (there's no "held as of HH:MM" concept — a tag just is or
  isn't held, right now). The rest of `audit` is computed *as of* an
  optional time argument (`as_of_when`), reconstructing historical state;
  the held marker/section can't do that — it always reflects *current*
  held state regardless of what time the audit report is run for.

  **Dimmed non-primary markers.** Every marker cell (everything shown as
  `●`/`○`/`<`/`>`/`-` rather than a number) prints in a new `k.DIM_STYLE`
  (grey — `Fore.LIGHTBLACK_EX` on terminal, deliberately without stacking
  `Style.DIM` on top since that risked becoming unreadable rather than
  just de-emphasized; swappable to dark blue via `Fore.BLUE` if grey
  doesn't read well in practice), so the numbers — what each particular
  grid actually exists to show — visually stand out from everything else
  in the row. This needed a small new primitive,
  `tt_printer.iprint_segments()`, since `iprint()` only ever applies one
  style to an entire line and a grid row now mixes styled and unstyled
  cells; it keeps the same guarantee `iprint()` already gives — a file
  redirect (`tt_publish.py`) or the echo log always gets the plain,
  unstyled text, regardless of what's shown on screen.

  **`AUDIT_GRID_FULL_MARKERS` config flag.** The full-marker grid look is
  new and its reception by operators is untested, so it's behind a
  boolean in `client_base_config.py` (default `False`, matching the look
  from before this feature — overridden to `True` in
  `client_local_config.py` for now to try it out) rather than being
  unconditional. `True` is everything described above (five markers,
  dimmed, shared `Key:` line); `False` collapses `markers` to just
  `{BikeTag.RETIRED: retired_tag_str}` (so held/in-use/done/unused all
  fall through to blank, matching the exact pre-feature behavior),
  prints undimmed (`k.NORMAL_STYLE`, since the retired dot was never
  dimmed before this option existed), and restores the original inline
  `"Bikes still onsite at HH:MM ( ● --> retired tag)"` note instead of
  the shared key line. The flag applies uniformly to all three grids,
  onsite/re-use/held alike — the "Tags held" *section* itself is shown
  either way; only its cell style follows the flag, same as the other
  two grids.
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

## Follow-on idea: pre-marking a hold while still checked in (not yet implemented, discussed only)

**Use case.** A bike comes in and gets tagged, then the operator realizes
it has to be leaned against the fence (or otherwise set aside) rather
than racked normally. Right now `hold` can't be used yet — the tag is
`IN_USE`, and `hold()` only accepts `UNUSED`/`DONE`. The operator wants to
mark it *now*, while it's still checked in, so that the moment it's
checked out it goes straight to `HELD` instead of briefly becoming a
normal, reusable `DONE` tag.

**A second, orthogonal flag: `BikeTag.pending_hold: bool = False`.**
`held` can't be set while `IN_USE` — that's load-bearing (it's what keeps
`status` untouched and truthful). So "mark this for hold" while checked
in needs its own flag, meaningful only while `status == IN_USE`.

**Trigger point: `BikeTag.finish_visit()`.** This is the one place a
visit's status flips `IN_USE → DONE`. Add: if `pending_hold`, clear it
and call `hold()` (equivalently, just set `held = True` directly) in the
same breath that `status` becomes `DONE`. One flag, one check, one
existing choke point — no new call sites needed anywhere check-out
already happens (`check_out`, `edit_out`, `flip`'s checkout leg).

**Same verbs, extended eligibility.** `hold`/`unhold` reused, not new
commands. `hold()`'s eligible-status set grows to
`{UNUSED, DONE, IN_USE}`:
- `UNUSED`/`DONE`: unchanged, holds immediately.
- `IN_USE`: sets `pending_hold = True` instead of `held`; message
  differs ("will be held when checked out", not "is now held").
`unhold()` on a still-`IN_USE`, pending tag just clears `pending_hold`
("hold cancelled" — distinct message, since nothing was ever actually
held).

**Open interaction: `flip`.** `flip` is checkout-then-immediate-checkin
on the same tag. If a pending-hold tag gets flipped, `finish_visit()`
would set `held = True` at the checkout instant, and the very next
`check_in()` call would then refuse it (`_test_time_in()` blocks a held
tag). Two ways to resolve, not decided here:
1. `flip` clears a pending hold rather than honoring it (rationale: a
   flip's whole point is "keep this tag in active service," which is in
   tension with the operator's stated intent to set it aside).
2. `finish_visit()`'s auto-conversion only fires for a "real" checkout,
   with `flip` exempted somehow (messier — `finish_visit()` has no
   inherent notion of "this checkout is part of a flip").

Leaning toward (1), but flagging rather than deciding.

**Visibility, per discussion:**
- `tags` command: invisible. A pending-hold tag shows exactly as any
  other `In` tag; no marker.
- `audit`: invisible in the top ("still onsite") and middle ("available
  for re-use") grids too — it's `IN_USE`, so it shows there as an
  ordinary numbered/marked cell like any other checked-in tag, same as
  today. The **held grid** gets an *additional, redundant* entry for it
  — the tag shows up there too (even though it isn't really `HELD` yet),
  parenthesized to mark it as pending rather than actual.

  This needs two mechanical changes, both scoped to the held grid only
  (not `TrackerDay.tags_held()` itself, which must stay pending-hold-free
  — `all_usable_tags()`, `check_tagid_usable()`, and the retire/unretire
  guards must keep treating a pending tag as a completely normal in-use
  tag until it actually converts):
  - A new `TrackerDay.tags_pending_hold()` (mirrors `tags_held()`,
    filters on `.pending_hold` instead of `.held`), used only by
    `audit_report()` to widen the held grid's *row* selection to
    `tags_held() | tags_pending_hold()` — so a prefix whose only
    "held-adjacent" tag is a pending one still gets a row.
  - `_draw_tag_grid()` needs an escape hatch for the held grid's *cell*
    rendering: a pending tag's `status_as_at()` is `IN_USE`, not `HELD`,
    so today's category-vs-`home_category` logic would render it as the
    ordinary `<` marker. The held-grid call would need to pass the set of
    pending tagids so the loop can override to the parenthesized-number
    form for those specific cells, regardless of category.

  **Open formatting problem, not resolved here:** every grid cell is a
  strict 2-character field (matching two-digit tag numbers 00-15), with
  1 separating space between cells — that's the whole basis for the
  column-alignment work earlier in this doc. A literal `"(03)"` is 4
  characters — doesn't fit. Candidate resolutions, undecided:
  1. Accept a local ripple: render it at its natural width and let the
     rest of that one row shift right of the header index line. Probably
     rare enough (few pending holds at once) to be tolerable, but genuinely
     breaks alignment for anything after it in that row.
  2. Drop the literal parens; convey "pending, not actual" via style
     alone (e.g. the number printed in `k.DIM_STYLE`, plain 2-char width,
     documented in the key) — keeps alignment perfect, doesn't literally
     match "parenthesized."
  3. Widen *every* cell in *every* grid by one character globally, so a
     4-char parenthesized entry always fits — safe, but changes the
     established width/density of the whole grid for what should be a
     rare case.

**Persistence: yes, across restarts** (per discussion — same reasoning
as `held_tagids`: a mid-day crash/restart shouldn't lose the operator's
intent). New JSON key, e.g. `TOKEN_PENDING_HOLD_TAGIDS =
"pending_hold_tagids"`, written from `tags_pending_hold()`. **Load
ordering matters and is subtle**: it must be applied strictly *after*
all of a day's historical visits are reconstructed (`start_visit`/
`finish_visit` calls in `_day_from_json_dict()`), via direct field
assignment (`biketag.pending_hold = True`), never by re-invoking
`finish_visit()` or any hold-related method. Reason: `finish_visit()` is
also what runs during load to reconstruct every already-completed
historical visit; if `pending_hold` were applied *before* that
reconstruction loop, a tag whose historical visit is already closed
would spuriously trigger the auto-hold-on-checkout conversion on every
single reload — converting it to `HELD` every time the file loads, which
is wrong. In a consistent file this shouldn't arise anyway (a tag's
`pending_hold` should only ever coexist with it currently being
`IN_USE`, since the conversion is synchronous at the moment of a live
check-out), but the load order needs to guarantee it regardless. Add a
`harmonize_biketags()`-style reconciliation guard mirroring the existing
`held`-flag one: if a loaded tag has `pending_hold` but its reconstructed
status isn't `IN_USE`, clear it and report a fix message.

**Undo/redo needs to know about the new field too** — same class of bug
already caught and fixed for `held` itself: `tt_undo._clone_biketag()`
and `_state_key()` would need `pending_hold` added alongside `status`/
`held`/`visits`, or marking (or cancelling) a pending hold — which
touches neither `status` nor `held` — would be invisible to undo's
change-detection, exactly the bug `held` had before that fix.

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
