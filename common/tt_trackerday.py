"""TagTracker by Julias Hocking.

TrackerDay and OldTrackerDay classes for tagtracker.

These hold the entire parking data for one day.

Copyright (C) 2023-2024 Todd Glover & Julias Hocking

    Notwithstanding the licensing information below, this code may not
    be used in a commercial (for-profit, non-profit or government) setting
    without the copyright-holder's written consent.

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU Affero General Public License as published
    by the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU Affero General Public License for more details.

    You should have received a copy of the GNU Affero General Public License
    along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

import re
import json

# import jsonschema
# from jsonschema import validate

import client_base_config as cfg
from common.tt_tag import TagID
from common.tt_time import VTime
import common.tt_util as ut
from common.tt_biketag import BikeTag
from common.tt_constants import REGULAR, OVERSIZE, UNKNOWN, RETIRED
from common.tt_bikevisit import BikeVisit
from tt_registrations import Registrations

# from tt_notes_manager import NotesManager

# Define constants for the string literals
TOKEN_TAGID = "tagid"
TOKEN_BIKE_SIZE = "bike_size"
TOKEN_TIME_IN = "time_in"
TOKEN_TIME_OUT = "time_out"
TOKEN_COMMENT = "comment:"
TOKEN_DATE = "date"
TOKEN_OPENING_TIME = "time_open"
TOKEN_CLOSING_TIME = "time_closed"
TOKEN_REGISTRATIONS = "registrations"
TOKEN_BIKE_VISITS = "bike_visits"
TOKEN_REGULAR_TAGIDS = "regular_tagids"
TOKEN_OVERSIZE_TAGIDS = "oversize_tagids"
TOKEN_RETIRED_TAGIDS = "retired_tagids"
TOKEN_NOTES = "notes"
TOKEN_SITE_NAME = "site_name"
TOKEN_SITE_HANDLE = "site_handle"


class OldTrackerDay:
    """One day's worth of tracker info and its context, OLD version.

    An OldTrackerDay is the trackerday structure from the version of
    TagTracker that assumed that a tag and a visit were the same thing.
    """

    def __init__(self) -> None:
        """Initialize blank."""
        self.date = ""
        self.time_open = VTime("")
        self.time_closed = VTime("")
        self.registrations = 0
        self.bikes_in = {}
        self.bikes_out = {}
        self.regular = frozenset()
        self.oversize = frozenset()
        self.retired = frozenset()
        self.colour_letters = {}
        from tt_notes import NotesManager

        self.notes: NotesManager = []
        self.site_handle = ""
        self.site_name = ""

    def all_usable_tags(self) -> frozenset[TagID]:
        """Return list of all usable tags."""
        return frozenset((self.regular | self.oversize) - self.retired)

    @staticmethod
    def guess_tag_type(tag: TagID) -> str:
        """Guess the type of tag (R=regular or O=oversize)."""
        colour = TagID(tag).colour.lower()
        if colour in ["o", "p", "w", "g"]:
            return "R"
        if colour in ["b"]:
            return "O"
        return ""

    def make_fake_tag_lists(self) -> None:
        """Fake up regular/oversized tag ists based on City Hall use in 2023."""
        regulars = set()
        oversizes = set()
        for tag in set(self.bikes_in.keys()) | set(self.bikes_out.keys()):
            tag_type = self.guess_tag_type(tag)
            if tag_type == "R":
                regulars.add(tag)
            elif tag_type == "O":
                oversizes.add(tag)
        self.regular = frozenset(regulars)
        self.oversize = frozenset(oversizes)

    def fill_colour_dict_gaps(self) -> None:
        """Make up colour names for any tag colours not in the colour dict."""

        # Extend for any missing colours
        tag_colours = set(
            [x.colour for x in list(self.oversize | self.regular | self.retired)]
        )
        for colour in tag_colours:
            if colour not in self.colour_letters:
                self.colour_letters[colour] = f"Colour {colour.upper()}"

    def lint_check(self, strict_datetimes: bool = False) -> list[str]:
        """Generate a list of logic error messages for OldTrackerDay object.

        If no errors found returns []
        If errors, returns list of error message strings.

        Check for:
        - bikes checked out but not in
        - checked out before in
        - multiple check-ins, multiple check-outs
        - unrecognized tag in check-ins & check-outs
        - poorly formed Tag
        - poorly formed Time
        - use of a tag that is retired (to do later)
        If strict_datetimes then checks:
        - valet date, opening and closing are well-formed
        - valet opening time < closing time
        """

        def bad_tags(taglist: list[TagID], listname: str) -> list[str]:
            """Get list of err msgs about poorly formed tags in taglist."""
            msgs = []
            for tag in taglist:
                tag: TagID
                if not isinstance(tag, TagID) or not tag.valid:
                    msgs.append(f"Bad tag '{tag}' in {listname}")
            return msgs

        def bad_times(timesdict: dict[str, VTime], listname: str) -> list[str]:
            """Get list of errors about mal-formed time values in timesdict."""
            msgs = []
            for key, atime in timesdict.items():
                if not isinstance(atime, VTime) or not atime:
                    msgs.append(
                        f"Bad time '{atime}' in " f"{listname} with key '{key}'"
                    )
            return msgs

        errors = []
        # Look for missing or bad times and dates
        if strict_datetimes:
            if not self.date or ut.date_str(self.date) != self.date:
                errors.append(f"Bad or missing date {self.date}")
            if not self.time_open or not isinstance(self.time_open, VTime):
                errors.append(f"Bad or missing opening time {self.time_open}")
            if not self.time_closed or not isinstance(self.time_closed, VTime):
                errors.append(f"Bad or missing closing time {self.time_closed}")
            if (
                self.time_open
                and self.time_closed
                and self.time_open >= self.time_closed
            ):
                errors.append(
                    f"Opening time '{self.time_open}' is not "
                    f"earlier then closing time '{self.time_closed}'"
                )
        # Look for poorly formed times and tags
        errors += bad_tags(self.regular, "regular-tags")
        errors += bad_tags(self.oversize, "oversize-tags")
        errors += bad_tags(self.bikes_in.keys(), "bikes-checked-in")
        errors += bad_tags(self.bikes_out.keys(), "bikes-checked-out")
        errors += bad_times(self.bikes_in, "bikes-checked-in")
        errors += bad_times(self.bikes_out, "bikes-checked-out")
        # Look for duplicates in regular and oversize tags lists
        if len(self.regular | self.oversize) != len(self.regular) + len(self.oversize):
            errors.append("Size mismatch between regular+oversize tags and their union")
        # Look for bike checked out but not in, or check-in later than check-out
        for tag, atime in self.bikes_out.items():
            if tag not in self.bikes_in:
                errors.append(f"Bike {tag} checked in but not out")
            elif atime < self.bikes_in[tag]:
                errors.append(f"Bike {tag} check-out earlier than check-in")
        # Bikes that are not in the list of allowed bikes
        _allowed_tags = self.regular | self.oversize
        _used_tags = self.bikes_in.keys() | self.bikes_out.keys()
        for tag in _used_tags:
            if tag not in _allowed_tags:
                errors.append(f"Tag {tag} not in use (not regular nor oversized)")
            if tag in self.retired:
                errors.append(f"Tag {tag} is marked as retired")

        return errors


class TrackerDayError(Exception):
    """A minimal error class for TrackerDays.

    Frequently a list of error messages may be passed up as self.args.
    """

    pass  # pylint:disable=unnecessary-pass


class TrackerDay:
    """One day's worth of tracker info and its context."""

    REGULAR_BIKE = "regular"
    OVERSIZE_BIKE = "oversize"

    # Minutes to allow checkin/out to exceed operating hours
    OPERATING_HOURS_TOLERANCE = 120

    # from tt_notes_manager import NotesManager

    def __init__(
        self, filepath: str, site_name: str = "", site_handle: str = ""
    ) -> None:
        """Initialize blank."""
        self.date = ut.date_str("today")
        self.time_open = VTime("")
        self.time_closed = VTime("")
        self.registrations = Registrations()
        self.regular_tagids = set()
        self.oversize_tagids = set()
        self.retired_tagids = set()
        self.colour_letters: dict[str, str] = {}
        from tt_notes import NotesManager

        self.biketags: dict[TagID, BikeTag] = {}
        self.notes = NotesManager(biketags=self.biketags)
        self.tagids_conform = None  # Are all tagids letter-letter-digits?
        self.filepath = filepath
        self.site_handle = site_handle or ""
        self.site_name = site_name or ""

    def initialize_biketags(self):
        """Create the biketags list from the tagid lists."""
        # Initialize all the BikeTags
        for t in self.regular_tagids:
            self.biketags[t] = BikeTag(t, REGULAR)
        for t in self.oversize_tagids:
            self.biketags[t] = BikeTag(t, OVERSIZE)
        for t in self.biketags.values():
            t.status = BikeTag.UNUSED
        for t in self.retired_tagids:
            if t not in self.biketags:
                self.biketags[t] = BikeTag(t, UNKNOWN)
            self.biketags[t].status = BikeTag.RETIRED

    def harmonize_biketags(self) -> list[str]:
        """
        Make tagid-types lists match any extant tags with visits.

        Returns a list of strings describing the fixes.

        Changes anything in tagid type lists that doesn't match
        what is already committed (visited) in tag lists to conform
        with what has already taken place in visits.  This handles
        the case in which a configuration file changes partway through
        a day: typically, marking a tag no longer 'retired' when the fob
        has been returned after being lost on a previous day.

        Reminder: a retired tagid will be in both the retired_tagids
        and the regular/oversize_tagids sets.
        """

        fixes = []
        # Look for any biketags marked RETIRED but no longer
        # retired in config
        for biketag in self.biketags.values():
            if (
                biketag.status == BikeTag.RETIRED
                and biketag.tagid not in self.retired_tagids
            ):
                # This bike tag can now be available.
                biketag.status = BikeTag.UNUSED

        # tagids_in_use = sorted({v.tagid for v in self.all_visits()})

        # for tagid in tagids_in_use:
        #     biketag: BikeTag = self.biketags[tagid]

        #     if biketag.bike_type == OVERSIZE:
        #         self.oversize_tagids.add(tagid)
        #         self._remove_tag_from_other_sets(tagid, exclude_set=self.oversize_tagids)
        #     elif biketag.bike_type == REGULAR:
        #         self.regular_tagids.add(tagid)
        #         self._remove_tag_from_other_sets(tagid, exclude_set=self.regular_tagids)

        # Look at the retired tagids (from config).
        # Change any unused usable tags now marked retired to status retired.
        for tagid in list(self.retired_tagids):

            if tagid not in self.biketags:
                fixes += [f"Tag {tagid} ignored (RETIRED in config but not available)."]
                continue

            biketag = self.biketags[tagid]  # Cache the biketag for efficiency
            if biketag.status == BikeTag.UNUSED:
                biketag.status = BikeTag.RETIRED
            elif biketag.status != BikeTag.RETIRED:
                # Retired in config but already in use!
                self.retired_tagids.discard(tagid)
                fixes += [f"Tag {tagid} not set to RETIRED."]

        # In sets of regular/oversize, are there any that don't match
        for tagid in list(self.regular_tagids | self.oversize_tagids):
            biketag = self.biketags[tagid]
            conf_type = self._configured_bike_type(tagid)
            if biketag.bike_type != conf_type:
                # Mismatch between config and biketags list.
                if biketag.status in {BikeTag.IN_USE, BikeTag.DONE}:
                    # biketag is used. Change the sets.
                    self._swap_tagid_between_sets(tagid)
                    fixes += [
                        f"Tag {tagid} remains {biketag.bike_type} " f"not {conf_type}."
                    ]
                else:
                    # The biketag not used yet, can change its type.
                    biketag.bike_type = conf_type
        return fixes

    def _swap_tagid_between_sets(self, tagid):
        """Swap tagid between regular_tagids and oversize_tagids."""
        if tagid in self.regular_tagids:
            self.regular_tagids.discard(tagid)  # Remove from regular
            self.oversize_tagids.add(tagid)  # Add to oversize
        elif tagid in self.oversize_tagids:
            self.oversize_tagids.discard(tagid)  # Remove from oversize
            self.regular_tagids.add(tagid)  # Add to regular
        elif tagid not in self.retired_tagids:
            raise ValueError(
                f"TagID {tagid} not found in retired, regular or oversize sets!"
            )

    def _configured_bike_type(self, tagid):
        if tagid in self.retired_tagids:
            return RETIRED
        if tagid in self.regular_tagids:
            return REGULAR
        if tagid in self.oversize_tagids:
            return OVERSIZE
        return UNKNOWN

    def _remove_tag_from_other_sets(self, tagid, exclude_set):
        """Helper for harmonize_biketags."""
        # Remove tag from all sets except the specified one
        if exclude_set is not self.oversize_tagids:
            self.oversize_tagids.discard(tagid)
        if exclude_set is not self.regular_tagids:
            self.regular_tagids.discard(tagid)
        if exclude_set is not self.retired_tagids:
            self.retired_tagids.discard(tagid)

    def retire_tag(self, tagid: TagID) -> bool:
        """Add tagid to today's retired set and mark BikeTag retired.

        Returns True if a change occurred.
        """
        biketag = self.biketags.get(tagid)
        if not biketag:
            return False
        if biketag.status not in {BikeTag.UNUSED, BikeTag.RETIRED}:
            return False
        changed = False
        if tagid not in self.retired_tagids:
            self.retired_tagids.add(tagid)
            changed = True
        if biketag.status != BikeTag.RETIRED:
            biketag.status = BikeTag.RETIRED
            changed = True
        return changed

    def unretire_tag(self, tagid: TagID) -> bool:
        """Remove tagid from today's retired set and mark BikeTag unused.

        Returns True if a change occurred.
        """
        biketag = self.biketags.get(tagid)
        if not biketag:
            return False
        changed = False
        if tagid in self.retired_tagids:
            self.retired_tagids.discard(tagid)
            changed = True
        if biketag.status == BikeTag.RETIRED:
            biketag.status = BikeTag.UNUSED
            changed = True
        return changed

    def all_usable_tags(self) -> frozenset[TagID]:
        """Return set of all usable tags."""
        return frozenset(
            [
                t.tagid
                for t in self.biketags.values()
                if (t.status and t.status != t.RETIRED)
            ]
        )
        ##return frozenset((self.regular_tagids | self.oversize_tagids) - self.retired_tagids)

    def fix_2400_events(self):
        """Change any 24:00 events to 23:59, warn, return Tags changed."""
        changed = 0
        for visit in self.all_visits():
            visit: BikeVisit
            if visit.time_in == "24:00":
                visit.time_in = VTime("23:59")
                changed += 1
            if visit.time_out == "24:00":
                visit.time_out = VTime("23:59")
                changed += 1
        return changed

    def bike_time_reasonable(self, inout_time: VTime) -> bool:
        """Checks if inout_time is reasonably close to operating hours."""
        if not self.time_open or not self.time_closed:
            return True
        return (
            self.time_open.num - self.OPERATING_HOURS_TOLERANCE
            <= inout_time.num
            <= self.time_closed.num + self.OPERATING_HOURS_TOLERANCE
        )

    # @staticmethod
    # def guess_tag_type(tag: TagID) -> str:
    #     """Guess the type of tag (R=regular or O=oversize)."""
    #     colour = TagID(tag).colour.lower()
    #     if colour in ["o", "p", "w", "g"]:
    #         return "R"
    #     if colour in ["b"]:
    #         return "O"
    #     return ""

    def fill_default_bits(
        self,
        site_handle: str = "",
        site_name: str = "",
    ):
        """Tries to fills certain missing bits of a TrackerDay."""
        self.site_handle = self.site_handle or site_handle
        self.site_name = self.site_name or site_name

    def lint_check(
        self, strict_datetimes: bool = False, allow_quick_checkout: bool = False
    ) -> list[str]:
        """Generate a list of logic error messages for TrackerDay object.

        If allow_quick_checkout, a check-out can be the same time as a check-in.
        """
        errors = []
        errors.extend(self._check_reference_tags())
        errors.extend(self._check_dates_and_times(strict_datetimes))
        errors.extend(self._check_bike_tags(allow_quick_checkout=allow_quick_checkout))
        errors.extend(self._check_allowed_tags())

        return errors

    def _check_reference_tags(self) -> list[str]:
        errors = []
        for tagid in self.regular_tagids | self.oversize_tagids | self.retired_tagids:
            if not isinstance(tagid, TagID):
                errors.append(f"Tag '{tagid}' is not a TagID, is a {type(tagid)}")
            if not tagid:
                errors.append(
                    f"A reference list has a null/non-empty tagid ({tagid.original})."
                )
        return errors

    def _check_dates_and_times(self, strict_datetimes: bool) -> list[str]:
        errors = []
        if strict_datetimes:
            if not self.date or ut.date_str(self.date) != self.date:
                errors.append(f"Bad or missing date {self.date}")
            if not self.time_open or not isinstance(self.time_open, VTime):
                errors.append(f"Bad or missing opening time {self.time_open}")
            if not self.time_closed or not isinstance(self.time_closed, VTime):
                errors.append(f"Bad or missing closing time {self.time_closed}")
            if (
                self.time_open
                and self.time_closed
                and self.time_open >= self.time_closed
            ):
                errors.append(
                    f"Opening time '{self.time_open}' must be earlier "
                    f"than closing time '{self.time_closed}'"
                )
        return errors

    def _check_bike_tags(self, allow_quick_checkout: bool = False) -> list[str]:
        errors = []
        for biketag in self.biketags.values():
            errors.extend(biketag.lint_check(allow_quick_checkout=allow_quick_checkout))
        return errors

    def _check_allowed_tags(self) -> list[str]:
        errors = []
        _allowed_tags = self.all_usable_tags()
        for tag, biketag in self.biketags.items():
            if biketag.status == biketag.RETIRED:
                if tag not in self.retired_tagids:
                    errors.append(f"Tag {tag} is RETIRED but not in retired list.")
            elif tag not in _allowed_tags:
                errors.append(
                    f"Tag {tag} is status available but not so in config'd lists"
                )
        return errors

    def earliest_event(self) -> VTime:
        """Return the earliest event of the day as HH:MM (or "" if none).

        It will for now be a time_in not a time_out until such time as
        bikes are kept past midnight, which is a whole other can of worms.
        """

        return min(
            [visit.time_in for visit in self.all_visits()]
            + [visit.time_out for visit in self.all_visits() if visit.time_out],
            default="",
        )

    def latest_event(self, as_of_when: VTime | int | None = None) -> VTime:
        """Return the latest event of the day at or before as_of_when.

        If no events in the time period, return "".
        If as_of_when is blank or None, then this will use the whole day.
        FIXME: ought as_of_when default to 'now'?
        """
        as_of_when = as_of_when or "now"
        as_of_when = VTime(as_of_when)
        if not as_of_when:
            return ""

        events = {
            visit.time_in for visit in self.all_visits() if visit.time_in <= as_of_when
        } | {
            visit.time_out
            for visit in self.all_visits()
            if visit.time_out and visit.time_out <= as_of_when
        }

        # Find latest event of the day
        latest = max(events, default="")
        return latest

    def num_later_events(self, after_when: VTime | int | None = None) -> int:
        """Get count of events that are later than after_when."""
        after_when = after_when or "now"
        after_when = VTime(after_when)
        if not after_when:
            return ""

        events = {
            visit.time_in
            for bike in self.biketags.values()
            for visit in bike.visits
            if visit.time_in > after_when
        } | {
            visit.time_out
            for bike in self.biketags.values()
            for visit in bike.visits
            if visit.time_out and visit.time_out > after_when
        }
        return len(events)

    def all_visits(self) -> list[BikeVisit]:
        """Create a list of BikeVisit objects from a list of BikeTag objects.

        List will always be sorted by the time_in of the visits.
        """

        # visits = []
        # for biketag in self.biketags.values():
        #     if biketag.visits:
        #         visits += biketag.visits
        # # Sort visits on their time in
        # visits = sorted(visits, key=lambda visit: visit.time_in)

        visits = [
            visit
            for biketag in self.biketags.values()
            if biketag.visits
            for visit in biketag.visits
        ]
        visits.sort(key=lambda visit: visit.time_in)

        return visits

    def _day_to_json_dict(self) -> dict:
        bike_visits = []
        for visit in self.all_visits():
            bike_size = (
                self.REGULAR_BIKE
                if self.biketags[visit.tagid].bike_type == REGULAR
                else self.OVERSIZE_BIKE
            )
            bike_visits.append(
                {
                    TOKEN_TAGID: visit.tagid,
                    TOKEN_BIKE_SIZE: bike_size,
                    TOKEN_TIME_IN: visit.time_in,
                    TOKEN_TIME_OUT: visit.time_out,
                }
            )

        # Sort bike_visits by tagid first, then by time_in
        bike_visits.sort(key=lambda x: (x[TOKEN_TAGID], x[TOKEN_TIME_IN]))

        # A comment message at the top of the file.
        comment = (
            f"This is a TagTracker datafile for {self.site_handle} on {self.date}."
        )

        ut.squawk(f"{self.notes.notes=}", cfg.DEBUG)
        return {
            TOKEN_COMMENT: comment,
            TOKEN_SITE_NAME: self.site_name,
            TOKEN_SITE_HANDLE: self.site_handle,
            TOKEN_DATE: self.date,
            TOKEN_OPENING_TIME: self.time_open,
            TOKEN_CLOSING_TIME: self.time_closed,
            TOKEN_REGISTRATIONS: self.registrations.num_registrations,
            TOKEN_BIKE_VISITS: bike_visits,
            TOKEN_REGULAR_TAGIDS: sorted(list(self.regular_tagids)),
            TOKEN_OVERSIZE_TAGIDS: sorted(list(self.oversize_tagids)),
            TOKEN_RETIRED_TAGIDS: sorted(list(self.retired_tagids)),
            TOKEN_NOTES: self.notes.serialize(),
        }

    @staticmethod
    def _day_from_json_dict(data: dict, filepath: str) -> "TrackerDay":
        day = TrackerDay(filepath)
        try:
            day.date = data[TOKEN_DATE]
            day.time_open = VTime(data[TOKEN_OPENING_TIME])
            day.time_closed = VTime(data[TOKEN_CLOSING_TIME])
            day.site_name = data[TOKEN_SITE_NAME]
            day.site_handle = data[TOKEN_SITE_HANDLE]

            day.regular_tagids = set(
                TagID(tagid) for tagid in data[TOKEN_REGULAR_TAGIDS]
            )
            day.oversize_tagids = set(
                TagID(tagid) for tagid in data[TOKEN_OVERSIZE_TAGIDS]
            )
            day.retired_tagids = set(
                TagID(tagid) for tagid in data[TOKEN_RETIRED_TAGIDS]
            )
            reg = int(data.get(TOKEN_REGISTRATIONS, 0))
            day.registrations = Registrations(reg)

        except (KeyError, ValueError) as e:
            raise TrackerDayError(
                f"Bad key or value in file: '{data[TOKEN_REGISTRATIONS]}'. Error {e}"
            ) from e

        # Initialize the biketags from the tagid lists
        day.initialize_biketags()

        # Add the visits, assuring sorted by ascending time_in
        # FIXME: set the biketag.status fields
        errs = []
        for visit_data in sorted(
            data[TOKEN_BIKE_VISITS],
            key=lambda x: (x[TOKEN_TAGID], TagID(x[TOKEN_TIME_IN])),
        ):
            maybetag = visit_data[TOKEN_TAGID]
            tagid = TagID(maybetag)
            if not tagid:
                errs.append(f"Datafile has bad tagid '{maybetag}'.")
            maybetime = visit_data[TOKEN_TIME_IN]
            time_in = VTime(maybetime)
            if not time_in:
                errs.append(
                    f"Datafile has bad or missing time_in for {tagid}: '{maybetime}.'"
                )
            maybetime = visit_data[TOKEN_TIME_OUT]
            time_out = VTime(maybetime)
            if maybetime and not time_out:
                errs.append(f"Datafile has bad time_out for {tagid}: '{maybetime}.'")
            if errs:
                continue
            day.biketags[tagid].start_visit(time_in)
            if time_out:
                day.biketags[tagid].finish_visit(time_out)
        if errs:
            raise TrackerDayError(*errs)

        # Make sure all the visits are sorted by check_in time

        # Notes have to get loaded last because they rely on scanning for
        # valid tags in today's usable list.
        try:
            day.notes.load(data[TOKEN_NOTES])
        except (KeyError, ValueError) as e:
            raise TrackerDayError(
                f"Bad key or value for Notes in file: "
                f"'{data[TOKEN_REGISTRATIONS]}'. Error {e}"
            ) from e

        return day

    def save_to_file(self, custom_filepath: str = "") -> None:
        """Save to the file.

        With default filepath, any errors in writing are considered catastrophic.
        For others, report the error and return False.
        """
        what_filepath = custom_filepath or self.filepath
        data = self._day_to_json_dict()
        # schema = self.load_schema()
        # self.validate_data(data, schema)

        # Any failure to write is a critical error
        try:
            with open(what_filepath, "w", encoding="utf-8") as file:
                json.dump(data, file, indent=4)
        except Exception:  # pylint:disable=broad-exception-caught
            if custom_filepath:
                print(f"PROBLEM: Unable to save data file file {what_filepath}")
                return False
            else:
                print(
                    f"\n\nCRITICAL PROBLEM: Unable to save data to file {what_filepath}\n\n"
                )
                raise
        return True

    @staticmethod
    def load_from_file(filepath) -> "TrackerDay":
        """Load the TrackerDay from file.

        Some error testing is done, but a lint check is still required.
        """
        try:
            with open(filepath, "r", encoding="utf-8") as file:
                data = json.load(file)
            loaded_day = TrackerDay._day_from_json_dict(data, filepath)
        except json.decoder.JSONDecodeError as e:
            raise TrackerDayError(f"JSON error {e}") from e
        loaded_day.determine_tagids_conformity()

        return loaded_day

    def _parse_tag_ids(self, tag_string: str) -> set:
        """Parse tag IDs from a string and return as a set."""
        tag_ids = set()
        for tag_id in re.split(r"[\s,]+", tag_string):
            t = TagID(tag_id)
            if t:
                tag_ids.add(t)
        return tag_ids

    def determine_tagids_conformity(self) -> bool:
        """Check if all tag IDs conform to standard pattern.

        Sets flag in TrackerDay object, returns a courtesy boolean as well.
        """
        pattern = re.compile(r"^[a-zA-Z]{2}(\d{1,5})$")

        for tag_id in self.regular_tagids | self.oversize_tagids | self.retired_tagids:
            match = pattern.match(tag_id)
            if not match:
                self.tagids_conform = False
                return False
            number_part = int(match.group(1))
            if not 0 <= number_part <= 15:
                self.tagids_conform = False
                return False

        self.tagids_conform = True
        return True

    def __repr__(self):

        return "\n".join(self.dump(detailed=False))

    def num_bikes_parked(self, as_of_when: str = "") -> int:
        """Number of bikes parked as of as_of_when.

        Returns (total,regular,oversize).
        """
        as_of_when = VTime(as_of_when or "now")

        regular_in = 0
        oversize_in = 0
        for biketag in self.biketags.values():
            regular_in += len(
                [
                    v
                    for v in biketag.visits
                    if v.time_in <= as_of_when and biketag.bike_type == REGULAR
                ]
            )
            oversize_in += len(
                [
                    v
                    for v in biketag.visits
                    if v.time_in <= as_of_when and biketag.bike_type == OVERSIZE
                ]
            )
        total_in = regular_in + oversize_in
        return total_in, regular_in, oversize_in

    def num_bikes_returned(self, as_of_when: str = "") -> int:
        """Number of bikes returned as of as_of_when.

        Returns (total,regular,oversize).

        A bike has been returned if it has checked out before now.
        """
        as_of_when = VTime(as_of_when or "now")

        regular_out = 0
        oversize_out = 0
        for biketag in self.biketags.values():
            for visit in biketag.visits:
                if visit.time_out and visit.time_out < as_of_when:
                    if biketag.bike_type == REGULAR:
                        regular_out += 1
                    else:
                        oversize_out += 1

        total_out = regular_out + oversize_out
        return total_out, regular_out, oversize_out

    def num_tags_in_use(self, as_of_when: str = "") -> int:
        """Number of bikes present."""
        return len(self.tags_in_use(as_of_when))

    def tags_in_use(self, as_of_when: str = "") -> list[TagID]:
        """List of bikes that are are present as of as_of_when.

        Critical to this working is the constraint that a tagid will
        only be used for one visit at any one time.
        """

        as_of_when = VTime(as_of_when or "now")
        return [
            b.tagid
            for b in self.biketags.values()
            if b.status_as_at(as_of_when) == BikeTag.IN_USE
        ]

    def tags_done(self, as_of_when: str = "") -> list:
        """List of tagids of biketags that are in a 'DONE' state as_of_when."""
        as_of_when = VTime(as_of_when or "now")
        return [
            b.tagid
            for b in self.biketags.values()
            if b.status_as_at(as_of_when) == BikeTag.DONE
        ]

    def max_bikes_up_to_time(self, as_of_when: str = ""):
        """The total bikes parked up to as_of_when."""

        # FIXME: extend this for regular/oversize/total

        as_of_when = VTime(as_of_when or "now")
        # Collect all time_in and time_out events up to as_of_when
        events = []
        for visit in self.all_visits():
            if visit.time_in <= as_of_when:
                events.append((visit.time_in, "in"))
            if visit.time_out and visit.time_out <= as_of_when:
                events.append((visit.time_out, "out"))

        # Sort events by time then 'in' before 'out'if times are the same.
        events.sort(key=lambda x: (x[0], x[1] == "out"))

        max_bikes = 0
        current_bikes = 0
        max_time = ""

        # Iterate through sorted events and track the number of bikes
        for event in events:
            if event[1] == "in":
                current_bikes += 1
                if current_bikes > max_bikes:
                    max_bikes = current_bikes
                    max_time = event[0]
            elif event[1] == "out":
                current_bikes -= 1

        return max_bikes, max_time

    def dump(self, detailed: bool = False) -> list[str]:
        """Return a compact textual summary of this object."""

        from tt_dump import build_dump  # Lazy import to avoid circular dependency

        return build_dump(today=self, detailed=detailed)


# def new_to_old(new: TrackerDay) -> OldTrackerDay:
#     """Perform a lossy conversion from new to old.

#     Some visits may be lost in th process, as this will
#     use only the most recent visit for any tag.
#     """
#     return None


# def old_to_new(old: OldTrackerDay) -> TrackerDay:
#     """Convert an old Trackerday to a new one."""

#     new = TrackerDay("")
#     new.date = old.date
#     new.time_open = old.time_open
#     new.time_closed = old.time_closed
#     new.registrations = Registrations(old.registrations)
#     from tt_notes import NotesManager
#     new.notes = NotesManager(old.notes)
#     # Tag reference lists
#     new.regular_tagids = old.regular
#     new.oversize_tagids = old.oversize
#     new.retired_tagids = old.retired
#     # Biketags dict
#     for t in new.regular_tagids:
#         new.biketags[t] = BikeTag(t, REGULAR)
#     for t in new.oversize_tagids:
#         new.biketags[t] = BikeTag(t, OVERSIZE)
#     for t in new.retired_tagids:
#         if t not in new.biketags:
#             new.biketags[t] = BikeTag(t, UNKNOWN)
#         new.biketags[t].status = BikeTag.RETIRED

#     # Add visits to the tags
#     for tagid, time_in in old.bikes_in.items():
#         new.biketags[tagid].start_visit(time_in)
#     for tagid, time_out in old.bikes_out.items():
#         new.biketags[tagid].finish_visit(time_out)

#     return new
