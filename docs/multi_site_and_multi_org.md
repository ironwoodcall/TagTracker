# Extending TagTracker to event sites and multiple sites

Status: discussion draft (started 2026-10-27)

This doc covers what it would take to run TagTracker at **additional sites
operated by one organization**. The main focus is **pop-up event sites**:
events of a few days, often with no internet, set up quickly by
non-technical people. It is ordered from the client outward:

- **Section 2:** the client at an event site: configuration, an event mode,
  hardware, and running offline.
- **Section 3:** getting datafiles to the server and loading them.
- **Section 4:** making the web reports work for several sites.
- **Section 5:** suggested order of work.
- **Section 6** (brief): several organizations.

Throughout, each site is assumed to be operated by exactly one organization.

---

## 1. Where things stand today

TagTracker has three parts, and each is at a different stage of
multi-site readiness:

| Part | What it does | Multi-site readiness |
|---|---|---|
| **Client** (`tagtracker.py` and friends) | Attendant data entry, one datafile per day | One install = one site. Already fine for multi-site. |
| **Database loader** (`database/db_from_datafile.py`) | Loads datafiles into SQLite | Mostly ready: picks the site from the datafile. |
| **Web reports** (`web/`, CGI) | All reports, estimator, leaderboard | **Not ready**: hardcoded to site #1. |

### What's already in place

- **Schema.** [create_database.sql](../database/create_database.sql) already has
  `ORG` and `ORGSITE` tables. `DAY` is keyed on `(date, orgsite_id)`, and
  `VISIT`, `BLOCK` and `DATALOADS` hang off `DAY`. So the database can
  already hold several sites side by side without any schema change.
- **Datafiles carry the site.** Each datafile has `site_handle` and
  `site_name` (from `SITE_HANDLE` / `SITE_NAME` in `client_local_config.py`),
  and filenames are prefixed with the handle (`{SITE_HANDLE}_YYYY-MM-DD.dat`).
- **Loader resolves the site.** `db_from_datafile.py` looks up the
  `ORGSITE` row for `(org, site_handle)` and creates it if it doesn't exist.
  The org comes from the `--org` command-line option (default `no_org`).

### What assumes a single site

- **Web reports hardcode `orgsite_id = 1`** in about 30 places, most marked
  `FIXME`. Files affected: `web_common.py`, `web_reports.py`,
  `web_day_detail.py`, `web_block_report.py`, `web_season_report.py`,
  `web_period_summaries.py`, `web_histogram_data.py`, `web_tags_report.py`,
  `web_estimator.py`, `web_predictor_model.py`, `web_predictor_report.py`,
  `leaderboard.py`, and `database/train_predictor_model.py`. Helper scripts
  (`schedule_model_sweep.py`, `forecast_model_backtest.py`) take an
  `--orgsite-id` option but default it to 1.
- **Web config is single-site.** `web_local_config.py` has one `SITE_NAME`,
  one `DATA_OWNER`, one set of estimator settings, one `TRAINED_MODEL_FOLDER`,
  one `EST_CALIBRATION_FILE`, one `CLIMATE_NORMALS`.
- **Weather backfill ignores site.** `db_wx_update.py` updates DAY rows by
  `date` alone, so every site gets the same weather.
- **Client calls to the estimator and leaderboard don't name a site.**
  `tt_call_estimator.py` and `tt_call_leaderboard.py` build URLs with no site
  parameter.
- **Access is by entry point, not by data.** Apache controls who can reach
  each entry point (`/tt`, `/audit`, `/tt_download`, ...) using role groups
  and IP addresses (see 4.5). Once in, a viewer sees all data. The
  application never looks at who the viewer is (nothing reads
  `REMOTE_USER`).

---

## 2. Event (pop-up) sites: the client

Most additional sites are likely to be **event sites**: a festival, race or
market that runs for a few days. These differ from a permanent site in three
ways:

- **Set-up has to be quick and done by non-technical people.** Each event
  gets a new site handle, a new set of tags and its own hours, often arranged
  the day before.
- **There will often be no internet.** Maybe none at all, maybe a few
  minutes every few hours. The client must work fully offline.
- **Data arrives late, all at once.** The datafiles for the whole event may
  reach the server days after the event closes.

This section covers the client at an event. Sections 3 and 4 (data
transfer and the web side) apply to event and permanent sites alike.

**Assumption: permanent sites and events use separate devices.** Each
permanent site has its own dedicated device (or devices). Events use a
separate device, or a small pool of them, that never doubles as a permanent
site's device. So:

- An event device only ever holds event configs; a permanent site's device
  keeps its `client_local_config.py` as today and never needs the event
  set-up.
- No risk of an event config being left active at a permanent site, or the
  reverse.
- Event devices can be set up differently (event mode, network features
  off, backup to USB) without affecting the permanent site.

If two devices are used **at the same event on the same day**, they must
not share a handle: both would write a datafile with the same name, and the
database holds one day per site (`DAY` is keyed on date and site), so one
device's data would replace the other's. Either give each its own handle
(e.g. `folkfest-north`, `folkfest-south`), or add a way to merge the two
files. To be decided if multi-device events happen.

### 2.1 Requirements for any additional site

Little has to change here. Each site runs its own client install with its own
`client_local_config.py`, which already holds everything site-specific:
`SITE_HANDLE`, `SITE_NAME`, tag inventory (`REGULAR_TAGS`, `OVERSIZE_TAGS`,
`RETIRED_TAGS`, `TAG_COLOUR_NAMES`), opening hours (`SEASON_HOURS`,
`SPECIAL_HOURS`), and folders.

Required:

1. **Unique, permanent site handles.** The handle is the site's identity in
   the database. Changing it later starts a new site with no history.
   Choose handles before go-live and document them.
2. **Lowercase-only handles.** The client allows uppercase in `SITE_HANDLE`,
   but the loader lowercases the handle when looking up `ORGSITE` and does not
   lowercase it when inserting. With a mixed-case handle, the first load
   creates the row, and the next load can't find it and fails on the
   `UNIQUE (org_id, site_handle)` constraint. Fix: lowercase consistently in
   the loader (or reject uppercase in the client's config check).
3. **Site parameter on estimator/leaderboard calls.** Add
   `site=<SITE_HANDLE>` to the URLs built in `tt_call_estimator.py` and
   `tt_call_leaderboard.py`, so the server answers for the right site.
4. **Separate publish/upload destinations, or site-prefixed filenames.**
   Check that `REPORTS_FOLDER`, `ECHO_FOLDER` and any datafile upload targets
   on the server don't collide between sites. Datafiles are already prefixed by
   handle; published reports and audit files should be too.

Optional:

- **One machine serving more than one site.** Not needed between permanent
  sites and events: each permanent site has its own device, and events use
  separate devices (see the assumption at the start of this section). An event device does serve
  many events over time; section 2.2 covers that with event files and an
  active config.

### 2.2 Quick configuration

#### What has to be set per event

| Item | Today's config name | Notes |
|---|---|---|
| Site name and handle | `SITE_NAME`, `SITE_HANDLE` | Handle must be lowercase and unique (2.1). |
| Tags | `REGULAR_TAGS`, `OVERSIZE_TAGS`, `RETIRED_TAGS` | Today: every tag listed one by one. |
| Colour names | `TAG_COLOUR_NAMES` | One letter per colour, e.g. `p: pink`. |
| Dates and hours | `SPECIAL_HOURS` | One entry per event day. `SEASON_HOURS` not needed. |
| Network features | `ESTIMATOR_URL_BASE`, `LEADERBOARD_URL_BASE`, `INTERNET_MONITORING_FREQUENCY` | Normally off for events (2.5). |
| Data owner notice | `DATA_OWNER` | May differ per event (e.g. the event organizer). |

Everything else (screen, sounds, folders) can be copied from a standard
event template.

#### The tag shorthand (needed whichever option is chosen)

The hard part for a non-technical person is the tag list. Today
`client_local_config.py` lists every tag (`pa0 pa1 ... pa15 pb0 ...`),
hundreds of them. A tag ID is a colour letter, a letter, and a number
(`common/tt_tag.py`), and numbers always start at 0, so an event's tags can be
described by ranges:

```text
regular:   pink a-j up to 15      -> pa0..pa15, pb0..pb15, ... pj15  (160 tags)
oversize:  red k-z up to 9        -> rk0..rk9, ... rz9               (160 tags)
```

Proposed: a small parser that expands this shorthand into the tag lists,
used by the config loader, so `REGULAR_TAGS` can hold either the full list
(as now) or the shorthand. It should:

- Accept a colour name or letter (`pink a-j 15` or `p a-j 15`), a letter
  range or list (`a-j`, `a,c,f`), and a highest number.
- Check for overlaps: the same tag in regular and oversize, or two colours
  given the same letter (pink and purple can't both be `p` at one site).
- Show a summary for the person to confirm, e.g.
  `Pink (p): letters a-j, 0-15 = 160 regular tags`.
- Accept missing tags as a retired list (`retired: pb3 pc11`), so a lost
  tag from last year's set doesn't need a new range.

This parser is useful for permanent sites too.

#### Options for who fills it in

**Option A: helper script run from the WSL prompt.**
`helpers/new_event_site.py` asks a short series of questions (event name,
handle, dates, hours per day, tag ranges, colours), shows the summary, and
writes a complete config for the event.

- Pros: nothing in TagTracker itself changes. Can't be run by accident during
  an event. Can check the handle against a list of handles already used.
- Cons: one more thing to start. Someone has to know where the script is.

**Option B: a QUICK-CONFIG command inside TagTracker.**

- Pros: the person setting up is already in TagTracker.
- Cons: the config is a Python module imported once at start-up
  (`client_base_config.py`), so changes would need a restart, or a new
  config store that TagTracker writes and re-reads. Attendants can type any
  command, so changing the tag set mid-event becomes possible, which is a
  real risk; it would need a guard (e.g. only allowed before the first
  check-in of the day). More code touching the core client.

**Option C: a plain-text event file, edited in Notepad.**
A short, readable file instead of Python:

```text
site name:    Folk Fest 2027
site handle:  folkfest
data owner:   Folk Fest Society
days:         2027-07-16 10:00-23:00
              2027-07-17 10:00-23:00
              2027-07-18 10:00-20:00
colours:      p=pink r=red
regular:      pink a-j up to 15
oversize:     red k-z up to 9
retired:      pb3 pc11
```

- Pros: easy to read, easy to fix by hand, easy to send to someone to check,
  easy to keep as a record of the event. No Python syntax to get wrong.
- Cons: a second config format to parse and maintain alongside the Python
  one.

**Recommendation:** C as the format, with A to create it. The script asks the
questions and writes the text file; anyone can then read or tweak the file
directly. At start-up TagTracker loads the event file, validates it, and
shows the tag summary and hours before going to the prompt. Reject a bad
file with a plain message ("line 9: 'red k-z up to 9' overlaps with pink
letter k"), never a Python traceback.

A QUICK-CONFIG command (B) can come later, limited to **showing** the event
setup (tag summary, hours, handle) rather than changing it.

If the event-mode client in 2.3 is built, the set-up app can be the same
program started in a set-up mode (`tagtracker --setup`, on its own
shortcut) rather than a separate script. Either way, set-up stays separate
from the normal start, so attendants starting TagTracker aren't taken into
it.

#### Several configs on one device

An event device will build up configs over time: past events, recurring
events, maybe a template or two. People won't delete them, so plan for a list.

- **Where they live.** One event file per config in an `events/` folder,
  plus a `template.txt`. Datafile names are prefixed with the handle, so
  all configs can share one data folder.
- **The set-up app** (script, or `tagtracker --setup`) opens on a
  list: name, handle, dates, and whether it has any data yet. Actions:
  - **New from template.**
  - **Duplicate** an existing one. Ask "same event in a new year, or a
    different event?": same keeps the handle (2.2, handles), different asks
    for a new one.
  - **Edit**: the same questions, with current answers as defaults.
  - **Archive**: move to `events/old/` instead of deleting, so it drops out
    of the list but stays as a record.
  - **Make active**: this is the config TagTracker will use (below).

#### Set-up chooses the active config; TagTracker just uses it

Two ways TagTracker could find its config when started:

1. **TagTracker asks:** at start-up, list the configs and let the
   attendant pick (today's date matches first).
2. **Set-up decides:** the set-up app marks one config as **active**.
   TagTracker always starts with the active one, after a one-screen
   confirmation. To use a different config, re-run set-up.

**Recommendation: 2.**

- **The choice is made by the person setting up the event,** once and
  deliberately, not by an attendant at the start of every day. Picking the
  wrong config files the day's data under the wrong site, so fewer
  decisions at start-up is safer.
- **TagTracker stays simple.** No menu code in the client; one start-up
  path, as today with the single `client_local_config.py`. All config
  handling lives in the set-up app.
- **One shortcut each:** "TagTracker" and "TagTracker set-up".

How it would work:

- The active config is recorded in a small text file (e.g. `events/ACTIVE`
  holding the config's filename), not a symlink, so it works on any
  filesystem.
- At start-up, TagTracker shows the site name and handle prominently and
  asks to confirm. If the answer is no, it says to run set-up and exits.
- **The main gap is a stale active config,** e.g. last month's event still
  active when the device goes out to a new one. Guard against it: if today
  isn't within the active config's dates, warn clearly ("Active config is
  Folk Fest, 16-18 July. Today is 22 July.") and require an explicit yes,
  or run set-up.
- If the active file is missing, or points to an archived config, TagTracker
  says to run set-up rather than guessing.
- Small fixes to the active config (hours, adding tags) can still be made
  from inside TagTracker with the `event` command (2.3). Switching to a
  different config can't; that's set-up's job.
- `tagtracker --event folkfest.txt` stays available as an override for
  testing and admins, but isn't on the shortcut.
- Once there are check-ins for the day, set-up should warn before changing
  the active config: the rest of the day would go into a different site's
  file.

#### Other set-up checks the script should make

- **Clock.** Offline, the laptop can't correct its clock, and the datafile's
  date and every check-in time come from it. Show the date and time and ask
  the person to confirm it.
- **Folders exist and are writable** (data, echo, backup; see 2.5).
- **Hours past midnight.** Datafile times are `HH:MM` within one day. If an
  event runs past midnight, decide how it's recorded before the event, not
  during it.

#### Choosing handles for events

The handle is permanent (2.1). For an event that recurs at the same place,
reuse one handle every year (`folkfest`, not `folkfest2027`), so year-over-year
reports work. Each datafile carries its own tag list, so changing the tag set
from year to year is fine. Use a new handle only for a different event or
location. Keep a list of handles in use (the helper script can read it).

### 2.3 Option: a stripped-down client for events

An alternative to "the full client with an event config" is a cut-down
client for pop-up sites: it prompts for the key settings at start-up, lets
them be corrected later, and leaves out commands an event doesn't need. This
section weighs it up; it is an option, not a decision.

#### What it would leave out

| Keep | Drop | Open question |
|---|---|---|
| Check in / out / inout, `flip` | `reg` (registrations) | `notes`: useful at events too? |
| `edit`, `delete`, `undo`, `redo` | `sus` (hold) / `unhold` | `chart`, `graph`, `stats`, `overview` |
| `query`, `recent`, `audit`, `tags`, `leftovers` | `retire` / `unretire` | `hours` (or fold into `event`, below) |
| `publish`, `help`, `exit` | `est`, `max` (leaderboard) | |
| `event` (new, below) | `yesterday` | |
| | `dump`, `debug`, `lint`, `dataform`, `monitor`, `uppercase` / `lowercase` | |

Fewer commands means a shorter help screen, less for one-day volunteers to
learn, and fewer ways to do something unexpected. Dropping `est`, `max` and
`yesterday` also removes the network calls and the multi-day lookups that
don't make sense offline or at a 3-day event. A retired tag at an event is
handled through `event` (add it to the retired list) rather than `retire`.

#### Start-up, and fixing settings later

- **Set-up (separate, 2.2):** chooses or creates the config and makes it
  active. For a new event (from template or duplicate) it asks for site
  name, handle, dates and hours, tag ranges and colours.
- **Every start of TagTracker:** use the active config. Show a one-screen
  summary (site and handle, today's hours, tag counts per colour, clock) and
  ask "Correct? (y/n)". "n" says to run set-up, or to use `event` for small
  fixes once started.
- **During the day, an `event` command** shows the setup and allows
  corrections. Changes are written back to the event file so the next day
  starts with them. Not every item is equally safe to change mid-day:

  | Item | Change mid-day? |
  |---|---|
  | Site name, colour names, data owner | Yes. |
  | Today's hours | Yes (as `hours` does now). |
  | Add tags (new range, more numbers) | Yes. |
  | Remove or retire tags | Only tags not used today; refuse otherwise. |
  | Site handle | Only before the first check-in of the day: it names the datafile and identifies the site in the database. After that, refuse and explain. |
  | Event dates | Yes for future days; today's date comes from the clock. |

  Each change asks for confirmation. A simple PIN could keep attendants out
  of it, but is probably more trouble than it's worth.

#### Two ways to build it

**Option 1: a separate program** (`tagtracker_event.py` or similar) with its
own main loop and command set, sharing the data and command code with the
full client.

- Needs the shared parts pulled out of `tagtracker.py`,
  `tt_process_command.py` and `tt_help.py` into modules both programs use:
  the main loop, the dispatcher, start-up and datafile handling.
- Each program is simpler to read on its own.
- Two entry points to keep in step. Fixes to shared behaviour (undo, the
  audit report, datafile handling) land in both only if the split is clean.
  Over time the two tend to drift.

**Option 2: one program with an event mode** (`tagtracker --event
folkfest.txt`).

- Commands are already defined in one table (`COMMANDS` in
  `tt_commands.py`) and dispatched in one place (`process_command()` in
  `tt_process_command.py`). Event mode is mostly an allow-list of command
  keys: anything not on it is treated as an unknown command, and help only
  lists what's allowed. Help is already keyed per command
  (`HELP_MESSAGES` in `tt_help.py`); the general help page needs an event
  version or needs generating from the allow-list.
- Start-up branches to the event prompts instead of reading
  `client_local_config.py`, and turns off estimator, leaderboard and
  internet monitor (2.5) without anyone having to remember.
- One codebase, so every fix applies to both.

**Recommendation: Option 2.** The command structure already supports it,
the refactoring is modest (an allow-list, the start-up branch, help), and
there's no second program to keep in step. Option 1 only pays off if the
event client ends up looking very different, e.g. a tablet or touch
interface. Even then, the event-mode work is the first step, because it
separates "which commands" and "which config" from the core.

Things to watch, whichever option:

- **The datafile must be identical** to a full-client datafile, so the
  loader and reports need no changes. Event mode changes the interface, not
  the data.
- **Tests.** Run the existing command tests (`helpers/test_*.py`) in both
  modes, plus a test that every dropped command is refused in event mode.
- **Commands that call each other.** Check that no kept command quietly
  relies on a dropped one (e.g. the audit report showing held or retired
  tags still works when `sus` and `retire` aren't available).

### 2.4 Dependencies and hardware

#### What the client needs (checked 2026-10-30)

Traced from the imports of `tagtracker.py`. The client is a text-only
program with very few dependencies:

| Dependency | Used for | Needed? |
|---|---|---|
| Python 3.10 or later | Everything | **Required.** `tagtracker.py` refuses older versions. |
| Python standard library | Everything else | Required; comes with Python. |
| `readline` (standard library) | Command-line editing and history | Optional. Missing on some platforms; the client carries on without it. |
| `colorama` (pip) | Coloured text | Optional. Without it, plain text and a one-line notice at start-up. Recommended. |
| `pyfiglet` (pip) | Large-letter start-up banner | Optional. Falls back to a plain banner. |
| `jsonschema` (pip) | Datafile validation | **Not needed by the client.** Only loaded when validation is asked for, which only the database loader does. |
| `mpg321` (or another command-line player, `SOUND_PLAYER`) | Sounds | Optional. If missing, sounds are turned off with a message. |
| `git` | Version line on the start-up screen | Should be optional, but currently **crashes start-up** if git isn't installed and the install has no `.git` folder. Fix before deploying to a fresh device. |
| `ps` | Internet monitor | Not used in event mode (monitor off). |

Event mode changes nothing here: the dropped commands' modules use only the
standard library. The proposed event additions (event-file parser,
`event_pack` zip and MD5 manifest) can be standard library only too, and
should be kept that way.

Minimum install on a new device:

```text
Python 3.10+               (required)
pip install colorama       (recommended)
pip install pyfiglet       (optional)
mpg321 or similar          (optional, for sounds)
```

#### What this means for choosing hardware

Since the client is plain Python in a text terminal, almost anything that
runs Python 3.10 on Linux will do. The software doesn't drive the hardware
choice; the event conditions do. Power draw is dominated by the screen, not
by TagTracker, which is idle between keystrokes.

What matters for an event device:

- **A full day on battery.** Events often have no power at the valet. Allow
  for a long day (e.g. 08:00 to 23:00) plus set-up. A USB-C power bank that
  can charge the device is cheap insurance whatever is chosen.
- **A clock that stays right offline.** The datafile's date and every
  check-in time come from the device clock (2.2). Devices without a
  battery-backed clock, or that only set the time from the internet, can
  start the day with the wrong date.
- **A real keyboard.** Attendants type tag IDs all day.
- **Readable screen outdoors**, and a terminal font large enough to read at a
  glance.
- **A USB port** (or SD slot) for the backup copy (2.5) and for carrying the
  end-of-event bundle (3.1).
- **Sound loud enough** to hear over a crowd, if sounds are used.

| Platform | Notes |
|---|---|
| Windows laptop + WSL (as now) | Known to work; the same set-up as the permanent site. Windows plus the WSL virtual machine uses more power than a plain Linux machine, so battery life depends a lot on the laptop. WSL2 has had clock drift after the laptop sleeps; check the time after waking (the start-up clock check in 2.2 covers this). |
| Linux laptop | Same software as WSL without the Windows overhead, so usually better battery life from the same hardware. An older laptop with a new battery may be enough. |
| Chromebook (Linux development environment, "Crostini") | **Preferred direction to evaluate.** Crostini is a Debian Linux container, so the set-up is the same as on WSL. The code already mentions running on a Chromebook. Long battery life is typical. USB drives must be shared with the Linux environment before it can write to them. |
| Windows, native (no WSL) | Tested 2026-10-30: runs and saves datafiles. Sounds don't work without a code change (`mpg321` is Linux-only), colours need Windows Terminal, and the internet monitor is Linux-only. Workable, but not a direction being pursued. |
| Raspberry Pi + screen + keyboard + power bank | Low power and cheap, but more parts to carry and set up. Most models have **no battery-backed clock**, so the date is wrong when started offline unless an RTC module (or the Pi 5's RTC battery) is fitted. Not recommended without one. |
| Android tablet + Bluetooth keyboard (Termux) | Good battery life and screen, but untested. Python, `colorama` and `pyfiglet` should install; sound and file access to USB storage need checking. A possible later option. |

**Suggested approach:** evaluate a Chromebook with Crostini as the main
event platform: good battery life, and the same Linux set-up as WSL with no
changes to TagTracker. Things to check on the Chromebook:

- the clock is right after starting with no network;
- sounds play from the Linux environment;
- TagTracker carries on correctly after the lid is closed and reopened;
- writing the backup copy to a USB drive.

Until that's done, a Windows laptop with WSL (or a Linux laptop) plus a
power bank is the fallback.

#### Power bank

A power bank is the simplest way to get through a long day with any
device. What to look for:

- **USB-C Power Delivery (PD) output of 45 W or more**, so it can run the
  device and charge it at the same time. Check the device's own charger
  wattage and match it; 65 W covers most laptops and Chromebooks.
- **Capacity about 20,000-27,000 mAh** (roughly 75-100 Wh). That's about one
  full extra charge of a typical Chromebook or laptop battery, enough to
  turn a 6-9 hour outdoor day into a full day.
- **A USB-C to USB-C cable rated for the wattage** (60 W or 100 W). A
  cheap phone cable can limit charging.
- **Recharges overnight** between event days (fast recharge input of 45 W
  or more helps). For a multi-day event with no power at night either, take
  two.

Rough cost (CAD, late 2026): about $50-90 for a 20,000 mAh / 45-65 W unit
from a known brand (Anker, Baseus, UGREEN and similar), $100-150 for
25,000+ mAh / 100 W. Plus about $15-25 for a good cable. Whatever is chosen, do a full-day battery test
with TagTracker running, with the screen at outdoor brightness, before the
first event.

### 2.5 Running without internet

The client already works offline for data entry. Things to switch off or
change so it behaves well at an event:

- **Estimator and leaderboard calls.** `tt_call_estimator.py` and
  `tt_call_leaderboard.py` call `urlopen()` with no timeout. With a weak or
  captive-portal connection, a call could hang the prompt. Event config
  should leave `ESTIMATOR_URL_BASE` and `LEADERBOARD_URL_BASE` empty (there's
  no model for an event site anyway, see 4.6). Separately, add a short timeout
  to both calls.
- **Internet monitor.** With `INTERNET_MONITORING_FREQUENCY` set, an offline
  site gets a warning every few minutes. Turn it off for events, or add a
  quiet mode that just logs.
- **Publishing.** Publishing writes to a local folder, so it works offline.
  Keep it on: it is the hook for backups and for sync.

#### Protecting the data

Offline, the bigger risk is losing data, not delivering it late. A laptop
that dies on day 2 with nothing uploaded loses the event. So:

- **A second copy on removable media.** Publish the datafile to a USB stick
  as well as the local folder, at each publish. This could be a
  `BACKUP_FOLDER` setting, or a second publish destination.
- **Keep `ECHO` on.** The echo transcripts can rebuild a datafile
  (`helpers/transcript_to_datafile.py`), so they are a second, independent
  record.
- **End-of-day check.** At close each day, show where today's datafile and
  its backup copies are, and when each was last written.

---

## 3. Getting data to the server and into the database

### 3.1 Getting the data to the server

#### Two paths, both supported

1. **Opportunistic sync.** Whatever moves datafiles to the server today
   (a sync job or synced folder) keeps retrying. When the laptop gets a few
   minutes of internet, everything published so far goes up. The loader
   already handles repeated copies of the same day: identical files are
   skipped by fingerprint, and `--newest-only` picks the latest of several
   same-named files. Nothing extra needed, but it can't be relied on.
2. **End-of-event bundle.** The definitive close-out. A helper,
   `helpers/event_pack.py`, makes one zip file containing:
   - all of the event's datafiles,
   - the echo transcripts,
   - the event config file,
   - a manifest: file list with MD5s, and for each day the date, number of
     visits, and bikes parked.

   The zip can be uploaded, emailed, or carried on a USB stick, whenever
   that's possible, days later if need be.

On the server, a matching step (`event_unpack`, or an option on
`db_from_datafile.py`) checks the zip against its manifest, loads the
datafiles, and prints the per-day totals from the database next to the totals
in the manifest. Anything that doesn't match (missing day, different
counts) is reported, while the event laptop and its USB backup still
exist.

#### Close-out checklist (for the person running the event)

1. Last day closed in TagTracker.
2. Run `event_pack`; check the per-day totals it prints look right.
3. Copy the zip to the USB stick, and upload it when internet is available.
4. Don't wipe the laptop or USB stick until someone confirms the server
   totals match.

### 3.2 Loading data into the database

Already works per site, since the site comes from each datafile. Remaining
items:

- Fix the handle-case bug above.
- `get_load_fingerprints()` checks fingerprints across all sites. That's fine
  (an MD5 match means the same file), but if fingerprints are ever made
  per-scope, scope them by `orgsite_id`.
- The server-side sync/cron job that pulls datafiles in should handle one
  inbound folder per site, or one shared folder; either works because the
  handle is in each file.

### 3.3 Weather

`db_wx_update.py` writes weather to every DAY row with a matching date. That's
correct only if all sites share one climate station. To support sites in
different areas:

- Make `WX_SITES` (the feed list) per site, e.g. a dict keyed by site handle.
- Add `orgsite_id` to the `UPDATE ... WHERE` clause.

If all sites are in one city, this can wait.

---

## 4. Web reports for several sites

The web reports were written for one site, and are most of the server-side
work. Everything here applies to permanent and event sites alike; 4.4 covers
what's specific to events.

### 4.1 Web reports: choosing the site

**a. Pick the scope (one site, or all sites) from the URL.**

- Add a `site` parameter to `ReportParameters` and `CGIManager` in
  `web_common.py`. Its value is a site handle, or `all` for the whole
  organization. Add an `except` parameter, used only with `site=all`, naming
  one site to leave out (e.g. `site=all&except=folkfest`). These three are
  the only scopes for now (see 4.2).
- Resolve it once, at the top of `web_reports.py`, to a list of
  `orgsite_id`s: one for a single site, all of the org's sites for `all`,
  all but one for `all` with `except`.
  If it's missing, fall back to a configured default (see 4.2) so existing
  bookmarks keep working.
- Every link, button and form the reports generate must carry the `site`
  parameter forward (`back_button`, `main_and_back_buttons`, day-navigation
  links, date-range selectors, and so on).

**b. Thread `orgsite_id` through every query.**

Replace each hardcoded `orgsite_id = 1` with the resolved scope, passed as a
function argument rather than a module-level constant. Every query against
`DAY` (or joining through it) needs to filter on the scope's site IDs. For
day- and block-level numbers, a plain `orgsite_id IN (...)` filter isn't
enough when the scope is "all sites". See 4.2. Grep
for `FROM DAY`, `JOIN DAY` and `day_id` to find them. While touching these,
convert f-string SQL to parameterized queries.

**c. Per-site display settings.**

Move site-specific items out of flat web config, either into extra columns on
`ORGSITE` or into a per-site dict in `web_local_config.py`, e.g.:

```python
SITES = {
    "downtown": {"name": "Downtown Bike Valet",
                 "trained_model_folder": "../data/models/downtown",
                 "est_calibration_file": "../data/cal/downtown.json",
                 "hist_fixed_y_axis_fullness": 300},
    "harbour":  {"name": "Harbour Bike Valet", ...},
}
DEFAULT_SITE_SCOPE = "all"   # or a site handle
```

Candidates: `SITE_NAME`, `HIST_FIXED_Y_AXIS_*`, `EST_BANDS`,
`EST_CONF_THRESHOLDS`, `TRAINED_MODEL_FOLDER`, `EST_CALIBRATION_FILE`,
`CLIMATE_NORMALS`. Page titles (`titleize`) should use the selected site's
name.

**d. Tags are per site.**

Tag IDs are only unique within a site (two sites may both have `bf3`).
The tag history and lost-tags reports (`web_tags_report.py`) and anything
grouping by `VISIT.bike_id` must filter by site.

**e. "Today" reports.**

The web audit report and the estimator's same-day lookups use
`fetch_day_id(date=today, orgsite_id=1)`. These need the selected site.

**f. Site picker / landing page.**

A simple list of the org's sites with today's headline numbers, linking to
each site's summary page.

### 4.2 Whole-organization and single-site reports: the site filter

Most reports should be available for the whole organization and for one
site. For most of them this fits naturally as one more item in the existing
filter form at the top of the page.

#### Scopes

For now, three scopes are enough:

| Scope | Example | URL |
|---|---|---|
| One site | Downtown | `site=downtown` |
| All sites | Everything the org runs | `site=all` |
| All sites except one | Everything but this year's Folk Fest | `site=all&except=folkfest` |

"All except one" covers the common case of leaving out a site that would
distort the numbers, such as a large event or a site that has just opened.
Arbitrary sets of sites (pick any 3 of 7) aren't needed yet. If they are
later, `except` can take a comma-separated list, and the rest of the design
doesn't change, because every scope already resolves to a list of
`orgsite_id`s.

#### The control

- Add a **Site** dropdown to `build_date_dow_filter_widget()` in
  `web_daterange_selector.py`, listing "All sites" followed by each of the
  org's sites. It writes the `site` parameter.
- Next to it, an **Except** dropdown ("none" followed by each site), shown
  only when "All sites" is chosen. It writes the `except` parameter. Two
  short dropdowns are easier to use than one long list with an "All except
  X" entry for every site.
- The form already copies other URL parameters into hidden fields, so the
  site choice carries through when dates or day-of-week are changed. Exclude
  `site` and `except` from those hidden fields when the dropdowns are
  present, the same way the date fields are excluded.
- Only show the dropdown when the org has more than one site. A single-site
  install then looks exactly as it does today.
- Reports without the filter form (day detail, audit, tag history,
  leaderboard, estimator) need the same choice. A small site picker in the
  page header, writing the same `site` parameter, covers them. The filter
  form's dropdown and the header picker should share one rendering function.
- Default when `site` is absent: a configured `DEFAULT_SITE_SCOPE`, either a
  handle or `all`. A sensible default for a multi-site org is `all`.

#### Which reports get which choices

In this table, "All sites" also covers "all sites except one": both
combine several sites, so the same reports support them.

| Report | All sites | One site | Notes |
|---|---|---|---|
| Season / summary (`web_season_report.py`) | Yes | Yes | Filter form already present. |
| Period summaries and detail (`web_period_summaries.py`, `web_period_detail.py`) | Yes | Yes | Filter form already present. |
| Block (time-of-day) report (`web_block_report.py`) | Yes | Yes | Filter form already present. Combine by block (see below). |
| Histograms (`web_histogram*.py`) | Yes | Yes | Duration histograms are visit-level and combine easily. Fullness needs block combining. |
| Compare ranges (`web_compare_ranges.py`) | Yes | Yes | Both ranges should use the same scope. |
| Data download (`web_download_data.py`) | Yes | Yes | Include a site column in the output when the scope is "all". |
| Day detail (`web_day_detail.py`) | Yes | Yes | For "all", show combined totals plus a per-site breakdown table. |
| Leaderboard (`leaderboard.py`) | Yes | Yes | Org-wide records use combined days (see below). |
| Audit (`web_reports.py`) | No | Yes | Operational, for attendants at one site. |
| Tag history / lost tags (`web_tags_report.py`) | No | Yes | Tag IDs are only unique within a site. |
| Estimator / predictions | No | Yes | Models are trained per site. |

For reports marked "No" under all sites, leave "All sites" and the Except
dropdown out of their picker, or have it fall back to an index of the sites with a link to each.

#### Combining sites correctly

Filtering visits with `orgsite_id IN (...)` is correct for anything counted
per visit: bikes parked, durations, visits per hour of arrival. It is wrong
for anything already summarized per day or per block, because there is now
one `DAY` row per site per date, not one per date. Examples:

These rules apply to any scope with more than one site, including "all
sites except one".

| Measure | Combining rule for "all sites" |
|---|---|
| Bikes parked, registrations, bikes remaining | Sum across sites for each date. |
| Number of days in a range, averages per day | Count distinct dates (any site open), not `DAY` rows. Otherwise averages are divided by the number of site-days. |
| Incoming / outgoing per block | Sum across sites by `(date, time_start)`. |
| Peak bikes on hand and time of peak | Sum `BLOCK.num_on_hand_*` across sites by `(date, time_start)`, then take the max. **Don't add the sites' daily peaks**: sites peak at different times. |
| Opening and closing time | Earliest open, latest close. "Per open hour" rates need a deliberate definition. |
| Weather | One value per date if sites share a climate area. Otherwise show per site, not combined. |

To avoid redoing this in every report, build it once: a function in
`web_common.py` (or `tt_dbutil.py`) that returns the SQL for a "combined day"
and "combined block" subquery for a given scope. For a single site it is
just the `DAY` / `BLOCK` rows for that site. For "all sites" it is the rows
grouped by date (and block) using the rules above. Reports then query that
subquery instead of `DAY` and `BLOCK` directly, and keep the same shape
whatever the scope. The day-level summaries in `common/tt_daysummary.py`
and the multi-day totals in `web_common.py` should use the same rules.

#### Titles and labels

Page titles should name the scope ("All sites", "All sites except Folk
Fest", or the site's name), so printed or shared reports are unambiguous.
This matters most for "except": the numbers look like org totals but
aren't.

#### Comparing sites side by side

A cross-site comparison report (sites as columns for one date range) would be
new, but could reuse the patterns in `web_compare_ranges.py`.

### 4.3 Main dashboard page

The main page (`main_web_page()` in `web_season_report.py`) currently shows
one totals table, with columns for the last few days, year-to-date and the
last 12 months, followed by a grid of buttons to the other reports. With
several sites it needs a site filter and, for the whole organization, an
overview of what's happening today.

#### Site filter

The header site picker from 4.2 goes at the top. Everything below it
follows the chosen scope, and every button carries the `site` parameter
to the report it opens.

When the scope is "All sites", buttons for reports that are single-site only
(Bike Tag Inventory, Future Day Prediction) either open a site index or are
shown disabled with a note to pick a site first.

#### Today's overview (all-sites scope)

A new panel above the totals table:

- **Headline numbers:** how many sites are reporting today, out of the org's
  total; how many are open right now; bikes on site right now across all
  sites; bikes parked so far today; combined peak so far today.
- **One row per site:**

  | Site | Status | Hours today | Parked today | On site now | Peak today | Last update |
  |---|---|---|---|---|---|---|
  | Downtown | Open | 07:00–22:00 | 412 | 138 | 171 at 12:30 | 4 min ago |
  | Harbour | Closed | 10:00–18:00 | 96 | 0 | 41 at 14:00 | 2 h ago |
  | Pop-up (stadium) | No data today | | | | | 3 days ago |

  Each site name links to that site's dashboard. "Parked today" links to its
  single-day detail.

The status column needs some care, because the server only knows what has
been loaded into the database:

- **"Reporting today"** means a `DAY` row exists for today for that site,
  i.e. at least one datafile for today has been loaded.
- **"Open now"** can be judged from that row's `time_open` / `time_closed`
  against the current time.
- **"Last update"** comes from `DATALOADS` (`load_timestamp`, or the
  datafile's own `datafile_timestamp`). Flag a site as **stale** when it is
  open but its last update is older than expected (e.g. more than twice
  the upload interval). That catches a site whose laptop is offline or
  whose upload job has stopped, which is useful in its own right.
- **Scheduled to open but no data** can't be detected yet, because opening
  hours live in each site's client config, not on the server. If this is
  wanted, give the server each site's expected hours (a per-site entry in
  web config, or columns on `ORGSITE`). Until then, "No data today" is the
  most the dashboard can say.

How fresh the numbers are depends on how often datafiles reach the server
and get loaded (the client's `PUBLISH_FREQUENCY` plus the server's load
schedule). Show the "as of" time on the panel.

#### Totals table (all-sites scope)

Same layout as today, with the values combined using the rules in 4.2. Two
additions:

- A **"Sites operating"** row: the number of sites with data on each day
  column, and site-days for the YTD and 12-month columns.
- A note when a site was added or dropped within a comparison period.
  Otherwise "this year vs last year" looks like growth when it is really an
  extra site. A later option is a like-for-like toggle limited to sites
  that operated in both periods.

The table's "Bikes on-site (left)" adjustment for today, which subtracts
bikes still on site from current-period totals, has to subtract across all
sites in scope.

#### Single-site scope

The page looks as it does today, for that site. Optionally add a one-line
strip at the top ("3 of 4 sites open, 312 bikes on site org-wide") linking to
the all-sites view, so someone looking at one site still sees the overall
picture. Only show it to viewers who can see the other sites (see 4.5).

### 4.4 Event sites in the web reports

- **Dashboard (4.3).** An event site will look "stale" or "no data today"
  for its whole run. The server needs to know a site is an event or is
  expected to be offline, e.g. a column on `ORGSITE` (`site_type` =
  `permanent` / `event`) or an entry in per-site web config. Event sites
  then show "offline event, data expected after close" instead of a stale
  warning.
- **Reports change after the fact.** Totals for an "all sites" date range
  will go up when event data arrives days later. Worth a note on reports for
  ranges that include an event site with no data loaded yet.
- **Org totals and records.** A big event can swamp year-over-year
  comparisons and the leaderboard. "All sites except the event" (4.2)
  handles the one-event case directly. If several events are running in
  the same period, a single exception isn't enough; the `site_type` column
  above would then allow an "All permanent
  sites" scope and let the leaderboard keep event records separate.
- **Weather.** An event may be in another town. Weather is currently by date
  only (3.3), so an event site gets the home site's weather. Either leave
  weather blank for event sites or do per-site weather.
- **Estimator.** None for event sites (4.6). The single-site "No" entries in
  the 4.2 table apply as usual.

### 4.5 Access control by site

Viewing rights need to be granted **per site**, not per organization.
Example: the bike organization BikingFolks runs a site at City Hall on
behalf of the City, plus several sites of its own. City staff should see
the City Hall site only; BikingFolks staff should see all of them.

The City doesn't operate anything, so it doesn't need to exist in
TagTracker as an organization. It is just a group of viewers. Organizations
describe who *operates* sites; access groups describe who may *see* them.

#### How production is set up today (checked 2026-10-27)

Apache on the production server already does all access control, with one
`ScriptAlias` + `<Location>` block per entry point in
`/etc/httpd/conf.d/40-auth-cgi.conf`:

| Entry point | Runs | Who gets in |
|---|---|---|
| `/tt` | `web.web_reports` | Groups `users`, `power-users`, `admins` |
| `/tt_download` | data downloads | Groups `power-users`, `admins` |
| `/audit` | audit report | Any valid user, **or** the valet site's IP, **or** the server itself (health check) |
| `/tt_estimator` | estimator | Any valid user except `attendant`, **or** the valet IP (and one other IP) |
| `/leaderboard`, `/leaderboard-cli` | leaderboard | Any valid user, **or** the valet IP (and one other IP) |
| `/cgi-bin/heartbeat` | stand-alone heartbeat check | Named users |
| `/cgi-bin/admin/*` | maintenance scripts | Named users |
| everything else under `/cgi-bin/` | | Denied |

Other relevant facts:

- All CGI is HTTPS only (`Require ssl`), with Basic auth against
  `/etc/httpd/auth/tagtracker.htpasswd` and groups in
  `/etc/httpd/auth/tagtracker.groups`.
- The group file is owned `root:apache`, mode 640, and Apache runs CGI as
  user `apache`. So **the report scripts can already read the group file**.
- The existing groups are **roles** (`users`, `power-users`, `admins`):
  they decide *which entry points* someone can use, not *which data*.
- The attendant laptop reaches `/audit`, `/tt_estimator` and the
  leaderboard **by IP address, with no login**. For those requests Apache
  sets no `REMOTE_USER`.
- Static content under `/var/www/html` needs any valid user. No TagTracker
  reports are published there at the moment.
- `/etc/httpd/README-tagtracker.txt` describes the plan but is slightly out
  of date (it describes `/tt` as "any valid user except attendant and cli";
  the config now uses groups).

#### Design: two kinds of group

Keep both dimensions in the one Apache group file:

1. **Role groups** (existing: `users`, `power-users`, `admins`), enforced
   by Apache per entry point, exactly as now. No change.
2. **Site-access groups** (new, e.g. `bikingfolks`, `city`), enforced by
   the application, because the site is a URL query parameter and Apache
   can't sensibly authorize on that.

A user needs both: a role group to get through the door of an entry point,
and a site-access group to see any data once inside.

```text
# /etc/httpd/auth/tagtracker.groups
users:        alice carol dave
power-users:  bob
admins:       erin
bikingfolks:  alice bob erin
city:         carol dave
```

The mapping from site-access groups to sites goes in web config:

```python
# Apache group -> site handles its members may see. "*" means all sites.
SITE_ACCESS = {
    "bikingfolks": "*",
    "city": ["cityhall"],
}
SITE_ACCESS_GROUP_FILE = "/etc/httpd/auth/tagtracker.groups"

# Requests let in by IP (no login) -> the site they may see.
SITE_ACCESS_BY_IP = {
    "203.0.113.10": ["cityhall"],    # City Hall valet laptop
}
```

The application reads the group file itself to find the groups for
`REMOTE_USER`, since Apache doesn't pass group membership to CGI scripts.
Membership stays in one file, maintained as it is today. If the auth backend
later changes (e.g. to LDAP, which can pass groups in environment
variables), only the lookup changes.

An alternative is naming groups after sites (`site_cityhall`) with no
mapping. The explicit mapping is clearer, and it handles "all sites" and
groups that cover several sites without extra rules.

#### Requests let in by IP address

These are the attendant laptop calls to `/audit`, `/tt_estimator` and the
leaderboard. They have no user, so group-based site access can't apply:

- Map each allowed IP to its site(s) with `SITE_ACCESS_BY_IP`, using
  `REMOTE_ADDR`. With more sites, each valet location's IP gets its own
  entry, and its own `Require ip` line in Apache.
- If the request names a different site, answer as for an unknown site.
- The server's own health check (`Require local`) can be given all sites.
- If a site's laptop doesn't have a fixed IP, it needs an account instead:
  a user in that site's access group, with credentials added to
  `client_local_config.py` for `tt_call_estimator.py` and
  `tt_call_leaderboard.py`.

#### Rules in the application

- **Work out the viewer's permitted sites once per request,** next to the
  scope resolution in `web_reports.py` (4.1a): from `REMOTE_USER` and the
  group file, or from `REMOTE_ADDR` for IP-allowed requests. The scope used
  for every query is the requested sites limited to the permitted ones.
- **"All sites" means all sites this viewer may see.** A City user who can
  see one site gets a single-site view: no site picker, no org-wide strip,
  and no org-wide dashboard overview. "All except X" is likewise applied
  to the permitted sites; if X is a site the viewer can't see, treat
  `except` as absent rather than reveal that X exists.
- **A site the viewer may not see is answered as if it doesn't exist,** so
  site handles aren't revealed by guessing URLs.
- **Every query on `DAY`, `VISIT` or `BLOCK` goes through the scope
  helper** from 4.1b / 4.2. That's what makes this enforceable: if every
  query uses one helper, a single check covers all reports. A grep for
  direct `FROM DAY` / `JOIN DAY` outside the helper can be a test.
- **Combined figures only include permitted sites.** This covers the
  dashboard overview and "Sites operating" counts, leaderboard records,
  and comparison reports. A record day at another site must not show up,
  even as a total.
- **Downloads.** `/tt_download` stays limited to `power-users` / `admins`
  by Apache. Inside it, the CSV export is limited to permitted sites. The
  "Full Database Download" hands over the whole SQLite file, so it should
  be offered only to users with `"*"` site access, or replaced by a
  filtered export.
- **A logged-in user in no site-access group sees no data.** That's the
  failure mode when someone is added to `users` but not to a site group;
  show a clear "no sites assigned to your account" message.
- **No user and no recognized IP** should deny by default. A web config
  switch can allow everything for local development.

#### Things served outside the report scripts

- **Static files under `/var/www/html`** need only any valid user. If
  per-site reports or datafile copies are ever published there, put each
  site in its own folder with its own `Require group` line.
- **`/cgi-bin/heartbeat` and `/cgi-bin/admin/*`** are maintainer tools,
  limited to named users. They can stay all-sites. The heartbeat compares
  against known opening and closing times, which overlaps with the
  dashboard's "scheduled but no data" idea (4.3); worth reusing those hours.

#### Rollout

1. Add the site-access groups to the group file, with every current user
   in the all-sites group. Behaviour doesn't change.
2. Deploy the application check, with `SITE_ACCESS_BY_IP` holding the
   current valet IP.
3. Only then create accounts for viewers who should see some sites only,
   and keep `/etc/httpd/README-tagtracker.txt` up to date.

#### Testing

Set up test users in each group and check, for every entry point and
download, that each user sees only their own sites, in both single-site and
"all sites" views, and that URLs for other sites behave like unknown sites.
Repeat for an IP-allowed request with no login.

### 4.6 Estimator and prediction models

- `train_predictor_model.py` and the calibration/backtest scripts should take
  a site argument and write output to per-site folders.
- `web_estimator.py`, `web_predictor_model.py` and `web_predictor_report.py`
  load the selected site's model and calibration files.
- A new site will have little history for a while. The estimator should say
  so plainly (low confidence, or "not enough data yet") rather than borrow
  another site's model.

### 4.7 Migration of existing data

None needed, as long as the current site keeps its existing `SITE_HANDLE`.
Its data is already in `ORGSITE` row 1 under the default org. Check that row
in the production DB. Until a second site exists, `DEFAULT_SITE_SCOPE` can
be its handle.

### 4.8 Testing

- Build a dev DB with two sites' datafiles. A second site's data can be
  made by copying existing datafiles and changing `site_handle` /
  `site_name`; keep the overlapping tag names on purpose.
- For each report, check that each site shows only its own data, that links
  keep the site, and that a missing `site` parameter falls back to the default.
- Check combined views against hand-computed totals, especially peak fullness.

---

## 5. Suggested order of work

### 5.1 Client and data transfer (events)

1. Tag-shorthand parser, usable from the existing Python config.
2. Short timeouts on estimator and leaderboard calls.
3. `--config` / event-file selection, the plain-text event file format, and
   the set-up app's config list (new, duplicate, edit, archive, make
   active), with TagTracker starting from the active config.
4. Set-up app with clock and folder checks: either the
   `new_event_site.py` script, or `tagtracker --setup` if event mode (2.3)
   is chosen, along with the command allow-list and the `event` command.
5. Backup folder for published datafiles.
6. `event_pack.py` and the server-side unpack-and-check step.
   (Before any of this is deployed, fix the git start-up crash in 2.4.)
7. Loader handle-case fix and lowercase-handle check (also step 1 of 5.2).
   Needed before any event's data is loaded.

All of these are client-side, plus the loading step on the server, and can
be done before the web work in 5.2. Data from an event can be loaded and
kept until the web reports are site-aware.

### 5.2 Web reports and server

1. Loader handle-case fix; lowercase-handle rule in client config check.
2. `site` URL parameter and scope threading through all web reports, with
   single-site choices only (a single site keeps working via the default).
3. Per-site web config (names, model/calibration paths).
4. Site parameter on client estimator/leaderboard calls.
5. "All sites" and "all sites except one" scopes: the combined day/block
   subquery, the Site and Except dropdowns in the filter form, and the
   header picker.
6. Main dashboard: today's overview panel, "Sites operating" row, and
   stale-site flag.
7. Site-level access control: site-access groups in the Apache group
   file, `SITE_ACCESS` and `SITE_ACCESS_BY_IP` mappings, and the
   permitted-site check in the scope helper (rollout steps in 4.5).
8. Per-site model training and calibration.
9. Per-site weather (only if sites are in different climate areas).
10. Site comparison report; server-side expected hours per site (for
    "scheduled but no data").
11. `site_type` on `ORGSITE` (permanent / event), and its use on the
    dashboard, site dropdown and leaderboard (4.4).

Steps 1 and 2 are enough to run a second site with correct per-site reports.
Steps 5 and 6 add whole-organization reports and the org dashboard.
Step 7 must be done before anyone who should see only some sites (e.g. the
City) is given an account.

---

## 6. Multiple organizations (brief)

There are two ways to do this.

### Option A: one installation per organization (recommended to start)

Give each organization its own server-side install: its own SQLite DB file,
its own web config, and its own CGI URL. Each install is the single-org,
multi-site setup from sections 2 to 4. Organizations can't see each other's data
because they share nothing. This needs no new code beyond sections 2 to 4, only
deployment work.

### Option B: one shared installation

Needed only if organizations should share one URL or see each other's data
(e.g. a regional comparison). Additional requirements:

- **Know the org of each datafile.** Today the loader assigns whatever
  `--org` it's given, so a file run with the wrong option is filed under the
  wrong org. Add `org_handle` to the datafile schema (version bump in
  `common/tagtracker_schema_v1.0.0.json`, plus `tt_trackerday.py`) and have
  the loader use it, or keep one inbound folder per org with the org fixed
  per folder.
- **Site handles are unique per org, not globally.** All site lookups,
  URLs and model folders must use the `(org, site)` pair.
- **Access control.** The site-level access from 4.5 already covers this:
  access is granted per site, so organizations need no separate permission
  model. Each org's staff get an Apache group mapped to that org's sites,
  and cross-org viewing is just a group mapped to sites from more than one
  org. The `ORG.can_view_orgs` column would be dropped rather than used.
  `SITE_ACCESS` entries then name `(org, site)` pairs, or an org shorthand
  such as `"bikingfolks/*"`. The "Full Database Download" can't be offered
  at all on a shared install. Parameterized SQL (4.1b) is a must
  here, not a nice-to-have.
- **Per-org settings.** `DATA_OWNER` notice, branding, weather feeds, and
  default site per org.
- **Cross-org reports.** Only for orgs that have granted access, using the
  same combining rules as 4.2.

### Licensing

The README restricts commercial, non-profit and government use without the
copyright holders' written consent. Any new organization would need that
consent before deployment, whichever option is chosen.
