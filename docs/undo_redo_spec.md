# Undo/Redo for tag-mutating CLI commands — Design Spec

Status: draft, not yet implemented.

## Goal

Let the operator type `undo` (short for `u`) to reverse the single most recent tag-mutating
command, within a 5-minute window, and `redo` to re-apply it. This targets
same-minute typo/mistake recovery — it is a convenience shortcut, not a
replacement for `edit`/`delete`, which remain the general-purpose correction
tools.

## Scope

**In scope:** `in`, `out`, `inout`, `edit`, `delete`, `flip`.

**Explicitly out of scope:** `retire`/`unretire`. Unlike the others, these
mutate `client_local_config.py` on disk (a regex rewrite of the
`RETIRED_TAGS` block in [tt_retire.py](../tt_retire.py)) in addition to
in-memory state. Reversing a source-file edit safely is a different (and
materially riskier) problem than restoring an in-memory tag snapshot, and is
not worth bundling into this feature. Manual `retire`/`unretire` remains the
only way to reverse a retire/unretire.

Also out of scope: everything else (`notes`, `hours`, `registrations`,
reports, etc.). These do **not** invalidate a pending undo/redo — only the
six in-scope commands do. (Notes are safe to leave out: `attached_notes` on
a `BikeVisit` is a derived cache, rebuilt by
`today.rebuild_visit_notes_link()` from `today.notes` by tag+time match
([tt_trackerday.py:267](../common/tt_trackerday.py#L267)), not a stored
reference — so restoring a tag snapshot and letting the normal
harmonize/rebuild pass run afterward reattaches notes correctly on its own.)

## Mental model

Undo reverts the internal data model (and therefore the datafile (but only
the tags-related portions of the datafile)), via the
normal save path) to its state immediately before the single most recent
in-scope command — restricted to only the tag(s) that command actually
changed. Stack depth is exactly one: one pending undo slot, one pending redo
slot, no deeper history.

## Key simplification: normalize "now" before dispatch

`check_in`/`check_out`/`guess_check_inout`/`flip_tags` each resolve an
*optional* time argument to `VTime("now")` **inside** the handler (e.g.
`bike_time = VTime(args[1]) if len(args) > 1 else VTime("now")` at
[tt_process_command.py:273](../tt_process_command.py#L273), similarly at
L321, L354, L411). Hoist that resolution up into `process_command()`, before
the handler is called, so every in-scope handler always receives an already
concrete, resolved time — never a live "now" to re-evaluate later.

Once that's true, undo and redo need no per-command special-casing:

- **Undo** = restore a pre-captured snapshot of the affected tag(s).
- **Redo** = call the exact same handler with the exact same
  (already-resolved) args again.

This also solves `inout` for free: redo just replays `guess_check_inout`
with the same resolved time against tag state that has been restored to be
identical to what it was pre-original-command, so the guess logic
re-derives the same per-tag in/out choice on its own. No separate
"which way did it resolve" bookkeeping is needed.

`edit` (time is a mandatory arg) and `delete` (no time arg) have no "now"
ambiguity to begin with — they just get snapshotted and replayed like
everything else.

## Redo replays the same args, not a "what if this happened now" command

Redo re-invokes the original handler with the identical resolved args
captured at the time the original command ran (e.g. the real check-in time,
`09:06`, not the time `redo` happens to be typed). This is both the
simpler implementation (no new "now" resolution to reason about) and the
correct data-integrity choice: the datafile should record when the bike
actually arrived, not when the operator happened to fix their undo.

## Partial-success batches

`in BG3 PA10` where `PA10` errors (e.g. already checked in): the recorded
undo scope is a **strict diff** — only tags that actually changed are
snapshotted and included. Redo replays the original full command exactly as
typed (`in BG3 PA10`), not just the subset that succeeded. If `PA10` is
still in error, redo raises the same error again, same as the first attempt
would if retried by hand.

## Data structures (new module `tt_undo.py`)

- `UndoRecord`: `cmd_key`, `resolved_args`, `tags` (only the tags that
  actually changed), `snapshot_before: dict[TagID, BikeTag]` (via
  `copy.deepcopy`), `label` (human-readable text for messages),
  `created_at` (real wall-clock time — see below), `expires_at`.
- `RedoRecord`: same `cmd_key`/`resolved_args`/`label`, its own
  `expires_at`.
- A small singleton (mirroring the existing `NoiseMaker` class-queue style)
  holding one `_pending_undo` and one `_pending_redo` slot.

**Wall-clock, not bike-clock.** The 5-minute window is measured in real
elapsed time (`time.monotonic()` / `datetime.now()`), not `VTime`. `VTime`
is the backdatable in-log event time (e.g. `in gb3 9:06` typed at 9:40) and
must never be used for the undo/redo expiry clock.

## Flow

1. In `process_command()`, for the six in-scope commands: normalize time →
   snapshot the tags named in the command → run the handler as today → if
   `data_changed`, build an `UndoRecord` scoped to the tags that actually
   changed, store it as the single pending-undo slot, and clear any pending
   redo.
2. `CMD_UNDO`:
   - No pending record, or expired → polite message ("nothing to undo" /
     "undo window has passed"); clear the slot if expired.
   - Otherwise: restore the snapshot for the affected tag(s), convert the
     consumed `UndoRecord` into a fresh `RedoRecord`, play a new "undo"
     sound cue, print `Undid: <label>`, and return `data_changed=True` so
     the normal save/publish/notes-harmonize pipeline runs exactly as it
     does for any other mutating command.
3. `CMD_REDO`:
   - No pending record, or expired, or invalidated by an intervening
     mutating command → polite "nothing to redo" message (the three causes
     can share one user-facing message; keep them distinguishable
     internally/in logs).
   - Otherwise: print `Redoing "<label>"`, call the stored handler with the
     stored resolved args. This re-enters the normal in-scope path from
     step 1, so it naturally re-arms a fresh undo (undoing the redo) and
     reproduces the original command's own confirmation line/sound for
     free.
4. Any other successful in-scope command already clears the pending redo
   slot as a side effect of step 1 — this is what "redo dies on any
   intervening tag-changing command" reduces to; no separate invalidation
   logic is needed.

## Persistence across process restart: none (v1)

Pending undo/redo state lives only in process memory (the `tt_undo.py`
singleton). It is **not** written to the datafile. A `tagtracker` restart —
deliberate or crash — always clears it.

```
9:06  IN PA5
9:07  (exit tagtracker)
9:08  (start tagtracker)
9:10  UNDO        <-- "nothing to undo": same message as an expired window
```

This is a deliberate v1 scope decision, not an oversight:

- No data is put at risk by this choice. Every mutating command already
  calls `today.save_to_file()` immediately
  ([tagtracker.py:150-154](../tagtracker.py#L150-L154)), and exit performs
  one more full publish on top
  ([tagtracker.py:158](../tagtracker.py#L158)). By the time a restart could
  happen, the command's effect is already durably on disk. What's lost
  across a restart is only the one-keystroke shortcut for reversing it —
  `edit`/`delete` remain fully available as the manual fallback the
  operator already uses today.
- Persisting it would require extending the datafile's JSON schema with a
  "pending undo" section (deep-copied pre-command tag state + resolved
  replay args + a wall-clock timestamp), teaching the loader to tolerate
  its absence in every existing/older datafile, and writing bespoke
  (de)serialization for a snapshot that isn't otherwise part of the day's
  persisted model.
- It would also raise a staleness question this design would rather not
  own: other processes (database loaders, bridging scripts) may read or
  write near this datafile. A persisted undo record has to keep being
  correct against whatever else may have touched the file between the
  original command and the eventual `undo` — an in-memory-only record
  never has to ask that question, since it can only ever refer to state it
  personally just changed, in the same process.

No special-case code is needed to handle "undo requested after a restart" —
it is exactly the same "no pending record" branch already required for
window expiry and for "never mutated anything yet." If restarts-mid-window
turn out to be common enough in practice to be annoying, persisting undo
state is a scoped follow-on, not something to build speculatively now.

## Open items / assumptions to verify during implementation

- `notes`/`hours`/`registrations` do not invalidate a pending undo/redo —
  confirmed decision, worth a regression test once built.
- Confirm `delete`'s existing `y`/`n` confirmation prompt behavior when
  *replayed* by `redo` — it should not require the operator to re-type `y`
  interactively; the stored resolved args already include the confirmation.

## Task list

1. Hoist "now" resolution for `in`/`out`/`inout`/`flip` out of the four
   handlers into `process_command()` so handlers always receive a
   fully-resolved time.
2. Add `tt_undo.py`: `UndoRecord`/`RedoRecord`, singleton pending-slot
   manager, `record()`, `try_undo(today)`, `try_redo(today)`, wall-clock
   expiry logic.
3. Wire snapshot-capture + record-after into `process_command()` for the
   six in-scope commands (one shared code path, not six copies).
4. Add `CmdKeys.CMD_UNDO`/`CMD_REDO` and their `CmdConfig` entries in
   `tt_commands.py` (no-arg commands, `["undo"]` / `["redo"]`).
5. Add the `CMD_UNDO`/`CMD_REDO` branches to `process_command()`'s dispatch
   ladder.
6. New "undo" sound cue in `tt_sounds.py`; confirm redo reuses the replayed
   command's existing cue rather than adding a second new one.
7. Pretty per-command `label` text for messages, reusing existing
   formatting (e.g. `print_tag_inout`) rather than inventing a parallel
   message format.
8. Help text in `tt_help.py` + README/changelog entry, including the
   "not available across a restart" limitation.
9. Tests: snapshot/restore correctness per command (single-tag and
   multi-tag, partial-failure batch), undo-window expiry, redo-window
   expiry, redo killed by intervening mutation, `inout` undo/redo
   re-deriving the correct direction, notes reattachment after restore,
   double-undo politely refused, save/publish still fires
   (`data_changed=True`) on both undo and redo, undo/redo unavailable
   immediately after a fresh process start.
10. Manual smoke test against a live/staged day file, diffing the on-disk
    JSON before/after an undo to confirm it's byte-for-byte the
    pre-command state for the affected tag(s).
