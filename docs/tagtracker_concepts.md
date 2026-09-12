# TagTracker Concepts (for valet attendants)

A plain-language guide to the ideas behind what you see on screen. This
isn't a command reference — type `help` (or `help <command>`) for exact
syntax. This is about *what things are* and *why they work the way they
do*.

---

## Cheat sheet

**Tag** — one claim-check, two halves (bike + owner), one bike at a time.

**Visit** — one stay: a check-in, and (once the bike leaves) a
check-out. A tag can rack up several visits in a day as different bikes
use it in turn.

**Tag states**

| Shows as | Means |
|---|---|
| `-` / blank | Available — unused today |
| `In` | Checked in — a bike is here right now |
| `Ou` | Checked out — free to reuse today |
| `Rt` | Retired — out of service permanently |
| `Su` | Suspended — out of service just for today |

**Suspended vs. retired** — retired is forever (until deliberately
unretired); suspended resets to nothing every single morning, no matter what.

**Every day is a clean slate** — visits, notes, registrations, hours,
and suspended tags all start empty each day. The retired list and the tag
inventory itself carry over day to day. A crash or restart *during* a
day loses nothing already entered — but nothing carries forward past
midnight except what's meant to.

**Notes** — a short comment attached to a tag's current visit (e.g. a
flat tire). **Registrations** — a running daily count, not tied to any
tag.

**Mistakes** — `undo` reverses the single most recent check-in/out/edit/
delete/suspend/unsuspend, for a couple of minutes only; `redo` reverses an
`undo`.

**Quick commands**

| Command | Does |
|---|---|
| `in <tag>` / `out <tag>` | Check a bike in / out |
| `<tag>` alone | Guess in or out |
| `edit` / `delete` | Fix a check-in/out time / remove one |
| `suspend <tag>` / `unsuspend <tag>` | Set aside for today / release |
| `retire <tag>` / `unretire <tag>` | Permanently out / back in |
| `note <text>` | Attach a note to a tag |
| `register [+n]` | Log bike registrations |
| `query <tag>` | What's going on with this tag today |
| `tags` / `audit` | Status board / end-of-day grids |
| `undo` / `redo` | Fix, or replay, the last mistake |

---

## Tags

Each tag is a two-piece claim check, like a coat check: one half goes on
the bike, the other goes to the owner. One tag equals one bike, one
visit at a time. The tracker's whole job is to remember which tags
currently have a bike attached, which are free to hand out, and which
shouldn't be handed out at all right now.

Tags are a fixed inventory, set up once (which tags exist, what colour
they are, whether they're the oversize kind) — you don't create or
destroy tags day to day, you just use the ones that exist.

## Visits

A **visit** is one bike's stay: a check-in time, and — once it leaves —
a check-out time. It's the actual event being recorded; a tag's
*status* is really just a summary of where things stand with its latest
visit (or the fact it hasn't had one yet today).

A single tag can have several visits in one day: bike A checks in on
`bg3` in the morning and leaves at noon, then bike B gets `bg3` in the
afternoon — two separate visits, same tag, same day. `query <tag>` lists
every visit a tag has had today, including any that are still open
(no check-out yet).

Because a visit's check-in and check-out have real times attached, most
of what "when did this happen" means in the tracker comes straight from
visits — there's nothing more exotic to it than that. Times are entered
in ordinary 24-hour clock format, and typing `now` always means the
actual current time; that's about as complicated as time gets here.

## Tag states

Every tag is, at any moment, in exactly one of these:

1. **Available** — hasn't been used yet today. Ready to hand out.
2. **Checked in** — a bike is here right now, wearing this tag.
3. **Checked out** — the bike has left. The tag is free again and can be
   handed out to a *different* bike today (`in <tag>` reuses it).
4. **Retired** — permanently out of service.
5. **Suspended** — temporarily out of service, just for today.

A tag cycles freely between available → checked in → checked out → (in
again, with a new bike) all day long. Retired and suspended are the two
states that pull a tag *out* of that cycle — see below.

### Retired: permanently out of service

A retired tag is broken, lost, or otherwise done for good. It doesn't
get handed out, full stop, and it stays retired tomorrow and every day
after — retiring is a standing decision, not a for-today one.
`unretire` reverses it, for when a tag turns out to still be usable
after all (a "lost" fob turns up, say).

### Suspended: temporarily out of service, but not retired

Sometimes a tag needs to be pulled out of use just for today, without
retiring it — it's perfectly fine, it's just not available right now.
Two everyday situations call for this:

- **A bike is still here from a previous day.** It didn't get picked up
  before closing, so it's sitting in the lockup with its tag still on
  it. That tag isn't available for a new customer this morning — but
  it's not broken or lost either, so it shouldn't be retired. Mark it
  suspended at the start of the day.
- **A bike gets set aside mid-day.** Say it has no kickstand, so it ends
  up leaning against the fence instead of racked normally with the
  others. Once it's checked out, its tag is technically free again, but
  handing it out for a new bike would be confusing. Mark that tag suspended
  so it doesn't get reused, and so it doesn't look like a mysterious gap
  later when someone's scanning the board.

Marking a tag suspended is always a judgment call *you* make — the tracker
never guesses at it on its own.

A tag can only be suspended if it's currently available or already checked
out today — not while a bike is actually checked in on it (check it out
first), and not if it's retired.

**Suspended tags reset every day.** Unlike retiring, suspending is a
same-day-only decision — every morning starts with zero suspended tags. If
the same bike is *still* sitting in the lockup the next day, it needs to
be marked suspended again; the tracker won't remember it for you.

## Every day is a clean slate

Each day's check-ins, check-outs, notes, registrations, operating hours,
and suspended tags belong to that day alone — a new day starts every one of
those at zero. You're never looking at a mix of today's and yesterday's
activity.

What *doesn't* reset overnight is the standing setup: which tags exist,
what colour/size they are, and which ones are retired. Those are
decisions made once and used every day until deliberately changed.

**A crash or restart mid-day is not the same as a new day.** Everything
you enter is saved as you go, so if the program (or the computer) has
to restart partway through a day, you pick up exactly where you left
off — nothing already entered is lost. The one small exception is the
short `undo`/`redo` window: that's forgotten on a restart, but only that
— the underlying data itself was already saved and is never at risk.
The clean slate only happens at the actual day boundary, not at a
restart.

## Notes

A note is a short, free-text comment attached to whatever a tag is
doing right now — e.g. "flat tire", "leaning against fence". It rides
along with that tag's current visit and shows up whenever that visit is
displayed. Notes can be deactivated (and reactivated) by hand if they
stop being relevant; the tracker also does some of that automatically
once the bike in question has clearly left. `help note` has the details.

## Registrations

A simple running count for the day — how many bikes have been
registered — not tied to any particular tag or visit. It's a tally, not
a status.

## Fixing mistakes: undo and redo

`undo` reverses the single most recent check-in, check-out, edit,
delete, suspend, or unsuspend, but only for a couple of minutes after you did
it (and only until you do something else that changes tag data). `redo`
puts back what `undo` just took away. Neither of these is your safety
net for data loss — that's the "saved as you go" behaviour described
above. They're just a quick way to back out of a same-minute typo
without having to reconstruct it by hand with `edit`/`delete`.

## Reports: reading the record back

The tracker keeps a running record of everything that's happened today;
several commands let you look at that record different ways.

### The status board (`tags`)

Shows every tag's current state at a glance, using the symbols from the
cheat sheet above (`-`/`In`/`Ou`/`Rt`/`Su`).

### The audit report (`audit`)

Prints up to three grids of tag numbers, one row per colour:

- **Bikes still onsite** — every tag with a bike here right now.
- **Tags potentially available for re-use** — every tag that's been
  checked out and could be handed out again today.
- **Tags suspended** — every tag currently marked suspended (only appears if at
  least one tag is suspended).

Depending on how your site has it set up, each grid may show *only* its
own numbers with retired tags marked as a dot (the default), or it may
show a fuller picture where every cell says something — a small mark for
a tag that's checked in, checked out, suspended, or retired even if
that's not the category the grid is named for, and a dash for a tag that
simply hasn't been used yet.

In the fuller picture, a genuinely blank cell does always mean there's no
such tag at that spot at all. In the default (dot-only) view, though, a
blank cell is ambiguous: it means either that, *or* that the tag exists
but simply isn't in this grid's own category and isn't retired (e.g. a
tag that hasn't been used yet at all shows blank in every grid, not just
the ones it doesn't belong to).

One quirk worth knowing: the suspended grid always reflects the *current*
moment, not the time you asked the audit report for. If you run
`audit 09:00` in the afternoon, the suspended section still shows who's suspended
*right now* — suspend and unsuspend aren't logged with a time the way
check-ins and check-outs are.

### Other views

`query <tag>` answers "what's going on with this one tag today" —
every visit it's had, and whether it's suspended or retired. `recent` shows
recent activity across all tags. `stats` gives an end-of-day summary.
All of these are just different windows onto the same underlying
record — nothing you see in one of them is a separate, independent
source of truth.
