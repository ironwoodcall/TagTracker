# TagTracker by Julias Hocking

This is a simple tag tracking/data gathering system for bike parking operations for use at Victoria, BC's downtown bike parking service.

Some important assumptions the program makes:
* Opening hours don't cross midnight - the program automatically decides whether to start a new .dat based on the computer's date
* Each tag has a unique identifier that starts with at least 1 letter that relates consistently to the tag's colour
* Tag names don't match any of the command keywords listed below
* Each tag separates into two pieces, one for the bike and one for the customer, like a coat check
* Tags are reused day-to-day but not within a single day

The "intended" workflow using the tracker is:
1. bike checks in - bike receives half tag, owner receives half tag
2. log check-in with tracker
3. bike checks out - half tags are reunited
4. log check-out with tracker
5. tag is placed in some kind of return basket and not reused that day

# LICENSING

This program is largely covered by the GNU Affero General Public License v 3,
with this important caveat:
    Notwithstanding the rest of its licensing provisions, this code may not
    be used in a commercial (for-profit, non-profit or government) setting
    without the copyright-holder's written consent.

# SETUP
See [installation instructions](https://github.com/ironwoodcall/TagTracker/wiki/TagTracker-installation) in wiki

# USAGE - basic commands / short versions
Usage is described when you run the `help` command in TagTracker

## Weather updates
To backfill weather data into the `day` table, configure `WX_SITES`, `WX_MIN_AGE_DAYS`, and `DB_FILENAME` in `database/database_local_config.py`, then run `python3 -m database.db_wx_update` from the `bin` directory (suitable for cron). The script walks the configured CSV feeds in order, filling empty precipitation and max-temperature fields for dates older than the configured age. Use `--year YYYY` to override the default current year for feeds that include `{year}` in their URLs.
