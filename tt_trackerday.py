"""TagTracker by Julias Hocking.

OldTrackerDay class for tagtracker.

OldTrackerDay holds all the state information about a single day at the bike
parking service.

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

import json
import jsonschema
from jsonschema import validate
import re
from typing import List, Dict

from tt_tag import TagID
from tt_time import VTime
import tt_util as ut
from tt_biketag import BikeTag, BikeTagError
from tt_constants import REGULAR, OVERSIZE, UNKNOWN
from tt_bikevisit import BikeVisit
from client_local_config import REGULAR_TAGS, OVERSIZE_TAGS, RETIRED_TAGS


class OldTrackerDay:
    """One day's worth of tracker info and its context."""

    def __init__(self) -> None:
        """Initialize blank."""
        self.date = ""
        self.opening_time = VTime("")
        self.closing_time = VTime("")
        self.registrations = 0
        self.bikes_in = {}
        self.bikes_out = {}
        self.regular = frozenset()
        self.oversize = frozenset()
        self.retired = frozenset()
        self.colour_letters = {}
        self.notes = []

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
            if not self.opening_time or not isinstance(self.opening_time, VTime):
                errors.append(f"Bad or missing opening time {self.opening_time}")
            if not self.closing_time or not isinstance(self.closing_time, VTime):
                errors.append(f"Bad or missing closing time {self.closing_time}")
            if (
                self.opening_time
                and self.closing_time
                and self.opening_time >= self.closing_time
            ):
                errors.append(
                    f"Opening time '{self.opening_time}' is not "
                    f"earlier then closing time '{self.closing_time}'"
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

    def earliest_event(self) -> VTime:
        """Return the earliest event of the day as HH:MM (or "" if none)."""
        all_events = self.bikes_in.keys() | self.bikes_out.keys()
        if not all_events:
            return ""
        return min(all_events)

    def latest_event(self, as_of_when: VTime | int | None = None) -> VTime:
        """Return the latest event of the day at or before as_of_when.

        If no events in the time period, return "".
        If as_of_when is blank or None, then this will use the whole day.
        """
        if not as_of_when:
            as_of_when = VTime("24:00")
        else:
            as_of_when = VTime(as_of_when)
            if not (as_of_when):
                return ""
        events = [
            x
            for x in (set(self.bikes_in.values()) | set(self.bikes_out.values()))
            if x <= as_of_when
        ]
        # Anything?
        if not events:
            return ""
        # Find latest event of the day
        latest = max(events)
        return latest

    def num_later_events(self, after_when: VTime | int | None = None) -> int:
        """Get count of events that are later than after_when."""
        if not after_when:
            after_when = VTime("now")
        else:
            after_when = VTime(after_when)
            if not (after_when):
                return ""

        events = [
            x
            for x in (set(self.bikes_in.values()) | set(self.bikes_out.values()))
            if x > after_when
        ]
        return len(events)


class TrackerDayError(Exception):
    pass


class TrackerDay:
    """One day's worth of tracker info and its context."""

    def __init__(self, filepath: str) -> None:
        """Initialize blank."""
        self.date = ""
        self.opening_time = VTime("")
        self.closing_time = VTime("")
        self.registrations = 0
        self.regular_tagids = frozenset()
        self.oversize_tagids = frozenset()
        self.retired_tagids = frozenset()
        self.colour_letters: dict[str, str] = {}
        self.notes: list[str] = []
        self.biketags: dict[TagID, BikeTag] = {}
        self.tagids_conform = None  # Are all tagids letter-letter-digits?
        self.filepath = filepath
        self.site_name = ""

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
        """Fake up regular/oversized tag lists based on City Hall use in 2023."""
        regulars = set()
        oversizes = set()
        for tag in self.biketags:
            tag_type = self.guess_tag_type(tag)
            if tag_type == "R":
                regulars.add(tag)
            elif tag_type == "O":
                oversizes.add(tag)
        self.regular_tagids = frozenset(regulars)
        self.oversize_tagids = frozenset(oversizes)

    def lint_check(self, strict_datetimes: bool = False) -> list[str]:
        """Generate a list of logic error messages for TrackerDay object.

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

        def bad_times() -> list[str]:
            """Get list of errors about mal-formed time values in visits."""
            msgs = []
            for v in self.all_visits():
                v: BikeVisit
                if not isinstance(v.time_in, VTime) or not v.time_in:
                    msgs.append(f"Bad time_in '{v.time_in}' in a visit of '{v.tagid}'")
                if v.time_out and not isinstance(v.time_out, VTime):
                    msgs.append(
                        f"Bad time_out '{v.time_out}' in a visit of '{v.tagid}'"
                    )
            return msgs

        errors = []
        # Look for missing or bad times and dates
        if strict_datetimes:
            if not self.date or ut.date_str(self.date) != self.date:
                errors.append(f"Bad or missing date {self.date}")
            if not self.opening_time or not isinstance(self.opening_time, VTime):
                errors.append(f"Bad or missing opening time {self.opening_time}")
            if not self.closing_time or not isinstance(self.closing_time, VTime):
                errors.append(f"Bad or missing closing time {self.closing_time}")
            if (
                self.opening_time
                and self.closing_time
                and self.opening_time >= self.closing_time
            ):
                errors.append(
                    f"Opening time '{self.opening_time}' is not "
                    f"earlier than closing time '{self.closing_time}'"
                )
        # Look for poorly formed times and tags
        errors += bad_tags(list(self.regular_tagids), "regular-tags")
        errors += bad_tags(list(self.oversize_tagids), "oversize-tags")
        errors += bad_tags(list(self.biketags.keys()), "biketags")
        errors += bad_times()
        # Look for duplicates in regular and oversize tags lists
        if len(self.regular_tagids | self.oversize_tagids) != len(
            self.regular_tagids
        ) + len(self.oversize_tagids):
            errors.append("Size mismatch between regular+oversize tags and their union")
        # Look for BikeTag inconsistencies:
        #   - DONE biketag with 0 visits or an unfinished visit
        #   - UNUSED or RETIRED biketag with visits
        #   - IN_USE biketag with a non-null last visit
        #   - any visit other than last_visit having a null time_out

        for tagid, biketag in self.biketags.items():
            latest_visit = biketag.latest_visit()

            # DONE biketag with 0 visits or an unfinished visit
            if biketag.status == BikeTag.DONE:
                if len(biketag.visits) == 0:
                    errors.append(f"BikeTag {tagid} is DONE but has 0 visits.")
                elif latest_visit and not latest_visit.time_out:
                    errors.append(
                        f"BikeTag {tagid} is DONE but has an unfinished visit."
                    )

            # UNUSED or RETIRED biketag with visits
            if biketag.status in (BikeTag.UNUSED, BikeTag.RETIRED):
                if len(biketag.visits) > 0:
                    errors.append(
                        f"BikeTag {tagid} is {biketag.status} but has visits."
                    )

            # IN_USE biketag with a non-null last visit
            if biketag.status == BikeTag.IN_USE:
                if latest_visit and latest_visit.time_out:
                    errors.append(
                        f"BikeTag {tagid} is IN_USE but has a non-null last visit."
                    )

            # Any visit other than latest_visit having a null time_out
            for visit in biketag.visits[:-1]:  # Check all visits except the last one
                if not visit.time_out:
                    errors.append(
                        f"BikeTag {tagid} has a visit with time_in {visit.time_in} other than the last visit that has a null time_out."
                    )

        # Bikes that are not in the list of allowed bikes
        _allowed_tags = (
            self.regular_tagids | self.oversize_tagids
        ) - self.retired_tagids
        for tag in self.biketags:
            if tag not in _allowed_tags:
                errors.append(f"Tag {tag} not in use (not regular nor oversized)")
            if tag in self.retired_tagids:
                errors.append(f"Tag {tag} is marked as retired")
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
        """Create a list of BikeVisit objects from a list of BikeTag objects."""

        visits = []
        for biketag in self.biketags.values():
            if biketag.visits:
                visits += biketag.visits
        # Sort visits on their sequence number
        visits = sorted(visits, key=lambda visit: visit.seq)

        return visits

    def _day_to_json_dict(self) -> Dict:
        bike_visits = []
        for visit in self.all_visits():
            bike_visits.append(
                {
                    "sequence_id": visit.seq,
                    "time_in": visit.time_in,
                    "time_out": visit.time_out,
                    "tagid": visit.tagid,
                }
            )
        return {
            "date": self.date,
            "opening_time": self.opening_time,
            "closing_time": self.closing_time,
            "registrations": self.registrations,
            "bike_visits": bike_visits,
            "regular_tagids": sorted(list(self.regular_tagids)),
            "oversize_tagids": sorted(list(self.oversize_tagids)),
            "retired_tagids": sorted(list(self.retired_tagids)),
            "notes": self.notes,
            "site_name": self.site_name,
        }

    @staticmethod
    def _day_from_json_dict(data: Dict, filepath: str) -> "TrackerDay":
        day = TrackerDay(filepath)
        day.date = data["date"]
        day.opening_time = VTime(data["opening_time"])
        day.closing_time = VTime(data["closing_time"])
        day.registrations = int(data["registrations"])
        try:
            day.registrations = int(day.registrations)
        except ValueError as e:
            raise TrackerDayError(
                f"Bad registration value in file: {day.registrations}'. Error {e}"
            ) from e
        day.notes = data["notes"]
        day.site_name = data["site_name"]

        day.regular_tagids = frozenset(data["regular_tagids"])
        day.oversize_tagids = frozenset(data["oversize_tagids"])
        day.retired_tagids = frozenset(data["retired_tagids"])

        # Check the formats of the tagids
        day.check_tagid_formats()

        # Initialize all the BikeTags
        for t in day.regular_tagids:
            day.biketags[t] = BikeTag(t, REGULAR)
        for t in day.oversize_tagids:
            day.biketags[t] = BikeTag(t, OVERSIZE)
        for t in day.biketags.values():
            t.status = BikeTag.UNUSED
        for t in day.retired_tagids:
            if t not in day.biketags:
                day.biketags[t] = BikeTag(t, UNKNOWN)
            day.biketags[t].status = BikeTag.RETIRED

        # Add the visits
        for visit_data in data["bike_visits"]:
            tagid = TagID(visit_data["tagid"])
            time_in = VTime(visit_data["time_in"])
            time_out = VTime(visit_data["time_out"])
            day.biketags[tagid].start_visit(time_in)
            if time_out:
                day.biketags[tagid].finish_visit(time_out)

        return day

    def save_to_file(self) -> None:
        data = self._day_to_json_dict()
        schema = self.load_schema()
        self.validate_data(data, schema)

        with open(self.filepath, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=4)

    @staticmethod
    def load_from_file(filepath) -> "TrackerDay":
        with open(filepath, "r", encoding="utf-8") as file:
            data = json.load(file)

        schema = TrackerDay.load_schema()
        TrackerDay.validate_data(data, schema)

        loaded_day = TrackerDay._day_from_json_dict(data, filepath)
        loaded_day.check_tagid_formats()
        return loaded_day

    @staticmethod
    def load_schema() -> Dict:
        with open("tagtracker_schema_v1.0.0.json", "r", encoding="utf-8") as file:
            return json.load(file)

    @staticmethod
    def validate_data(data: Dict, schema: Dict) -> None:
        try:
            validate(instance=data, schema=schema)
        except jsonschema.exceptions.ValidationError as err:
            raise TrackerDayError(
                f"Invalid data according to the schema: {err.message}"
            ) from err

    def _parse_tag_ids(self, tag_string: str) -> set:
        """Parse tag IDs from a string and return as a set."""
        tag_ids = set()
        for tag_id in re.split(r"[\s,]+", tag_string):
            tag_ids.add(tag_id.strip())
        return tag_ids

    def set_taglists_from_config(self):
        """Assign oversize, regular, and retired tag IDs from config."""
        self.regular_tagids = self._parse_tag_ids(REGULAR_TAGS)
        self.oversize_tagids = self._parse_tag_ids(OVERSIZE_TAGS)
        self.retired_tagids = self._parse_tag_ids(RETIRED_TAGS)
        self.check_tagid_formats()

    def check_tagid_formats(self) -> bool:
        """Check if all tag IDs conform."""
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


def old_to_new(old: OldTrackerDay) -> TrackerDay:
    """Convert an old Trackerday to a new one."""

    new = TrackerDay("")
    new.date = old.date
    new.opening_time = old.opening_time
    new.closing_time = old.closing_time
    new.registrations = old.registrations
    new.notes = old.notes
    # Tag reference lists
    new.regular_tagids = old.regular
    new.oversize_tagids = old.oversize
    new.retired_tagids = old.retired
    # Biketags dict
    for t in new.regular_tagids:
        new.biketags[t] = BikeTag(t, REGULAR)
    for t in new.oversize_tagids:
        new.biketags[t] = BikeTag(t, OVERSIZE)
    for t in new.retired_tagids:
        if t not in new.biketags:
            new.biketags[t] = BikeTag(t, UNKNOWN)
        new.biketags[t].status = BikeTag.RETIRED

    # Add visits to the tags
    for tagid, time_in in old.bikes_in.items():
        new.biketags[tagid].start_visit(time_in)
    for tagid, time_out in old.bikes_out.items():
        new.biketags[tagid].finish_visit(time_out)

    return new
