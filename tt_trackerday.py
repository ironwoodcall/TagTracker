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
import re
import json
import jsonschema
from jsonschema import validate

import client_base_config as cfg
from tt_tag import TagID
from tt_time import VTime
import tt_util as ut
from tt_biketag import BikeTag, BikeTagError
from tt_constants import REGULAR, OVERSIZE, UNKNOWN
from tt_bikevisit import BikeVisit
from client_local_config import REGULAR_TAGS, OVERSIZE_TAGS, RETIRED_TAGS
from tt_registrations import Registrations
from tt_notes import Notes

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
        self.site_label = ""
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

    REGULAR_KEYWORD = "regular"
    OVERSIZE_KEYWORD = "oversize"
    OPERATING_HOURS_TOLERANCE = (
        90  # Minutes to allow checkin/out to exceed operating hours
    )

    def __init__(
        self, filepath: str, site_name: str = "", site_label: str = ""
    ) -> None:
        """Initialize blank."""
        self.date = ut.date_str("today")
        self.opening_time = VTime("")
        self.closing_time = VTime("")
        self.registrations = Registrations()
        self.regular_tagids = frozenset()
        self.oversize_tagids = frozenset()
        self.retired_tagids = frozenset()
        self.colour_letters: dict[str, str] = {}
        self.notes = Notes()
        self.biketags: dict[TagID, BikeTag] = {}
        self.tagids_conform = None  # Are all tagids letter-letter-digits?
        self.filepath = filepath
        self.site_label = site_label or "default"
        self.site_name = site_name or "Default Site"

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
        if not self.opening_time or not self.closing_time:
            return True
        return (
            self.opening_time.num - self.OPERATING_HOURS_TOLERANCE
            <= inout_time.num
            <= self.closing_time.num + self.OPERATING_HOURS_TOLERANCE
        )

    @staticmethod
    def guess_tag_type(tag: TagID) -> str:
        """Guess the type of tag (R=regular or O=oversize)."""
        colour = TagID(tag).colour.lower()
        if colour in ["o", "p", "w", "g"]:
            return "R"
        if colour in ["b"]:
            return "O"
        return ""

    # def make_fake_tag_lists(self) -> None:
    #     """Fake up regular/oversized tag lists based on City Hall use in 2023."""
    #     regulars = set()
    #     oversizes = set()
    #     for tag in self.biketags:
    #         tag_type = self.guess_tag_type(tag)
    #         if tag_type == "R":
    #             regulars.add(tag)
    #         elif tag_type == "O":
    #             oversizes.add(tag)
    #     self.regular_tagids = frozenset(regulars)
    #     self.oversize_tagids = frozenset(oversizes)

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

        # ut.squawk("&&&" + str(self))

        errors = []

        # Empty tagids in reference lists.
        for tagid in self.regular_tagids | self.oversize_tagids | self.retired_tagids:
            if not isinstance(tagid, TagID):
                errors.append(f"Tag '{tagid}' is not a TagID, is a {type(tagid)}")
            if not tagid:
                errors.append(
                    f"A reference list has a null/non-empty tagid ({tagid.original})."
                )

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

        # Missing check-ins or check-ins that are later than check-outs
        for v in self.all_visits():
            if not v.time_in:
                errors.append(f"A visit of tag {v.tagid} is missing a check-in time.")
            if v.time_out and v.time_in > v.time_out:
                errors.append(
                    f"A {v.tagid} visit has time in ({v.time_in}) later than time out ({v.time_out})."
                )

        # Multiple checked in for one biketag which can be detected by
        # Last visit must be the only one that is open
        for b in self.biketags.values():
            last_visit_index = len(b.visits) - 1
            for i, v in enumerate(b.visits, start=0):
                v: BikeVisit
                if not v.time_out and i != last_visit_index:
                    errors.append(
                        f"Tag {v.tagid} has a visit checked in that is not its last visit."
                    )
                    continue

        # Check each tagid's visits for overlaps
        for tagid, biketag in self.biketags.items():
            visits = biketag.visits
            # Compare each visit's time_out with the next visit's time_in
            for i in range(len(visits) - 1):
                current_out = visits[i].time_out
                next_in = visits[i + 1].time_in
                if current_out > next_in:
                    errors.append(f"Tag {tagid} has visits with overlapping times.")

        # This seems to (sadly) repeat what I had previously written furhter below.
        for tagid, biketag in self.biketags.items():
            tagid: TagID
            biketag: BikeTag
            # ut.squawk("&&&" + f"{tagid=},{biketag.status=},{biketag.visits=}")
            if not tagid:
                errors.append("No tagid for a BikeTag")
            if tagid != TagID(tagid) or biketag.tagid != TagID(biketag.tagid):
                errors.append(f"Poorly formed tagid for Biketag '{tagid}'")
            if tagid != biketag.tagid:
                errors.append(
                    f"BikeTag {tagid} key does not match object tagid {biketag.tagid}"
                )
            if biketag.visits and biketag.status == biketag.RETIRED:
                errors.append(f"Biketag {tagid} has visits but status is RETIRED.")
            # Check that visits have good tagids and they match
            for i, v in enumerate(biketag.visits, start=0):
                v: BikeVisit
                if v.tagid != tagid:
                    errors.append(
                        f"BikeTag {tagid} vist {i} tagid {v.tagid} does not match."
                    )
                if v.time_in != VTime(v.time_in) or v.time_out != VTime(v.time_out):
                    errors.append(
                        f"BikeTag {tagid} vist {i} has bad time(s): '{v.time_in}'/'{v.time_out}'."
                    )
                if v.time_in == "24:00" or v.time_out == "24:00":
                    errors.append(f"BikeTag {tagid} visit {i} has a time == '24:00'.")
            if biketag.visits:
                v = biketag.latest_visit()
                if biketag.status == biketag.DONE and not v.time_out:
                    errors.append(f"BikeTag {tagid} is DONE but has no time_out.")
                elif biketag.status == biketag.IN_USE and v.time_out:
                    errors.append(f"BikeTag {tagid} is IN_USE but has a time_out.")
                elif biketag.status == biketag.UNUSED:
                    errors.append(f"BikeTag {tagid} is UNUSED but has visit(s).")

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
                        f"BikeTag {tagid} is IN_USE but has a non-empty last visit check-out."
                    )

            # Any visit other than latest_visit having a null time_out
            for visit in biketag.visits[:-1]:  # Check all visits except the last one
                if not visit.time_out:
                    errors.append(
                        f"BikeTag {tagid} has a checked-in visit that is not its last visit "
                        f"(checked in at {visit.time_in})"
                    )

        # Bikes that are not in the list of allowed bikes
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

        visits = []
        for biketag in self.biketags.values():
            if biketag.visits:
                visits += biketag.visits
        # Sort visits on their time in
        visits = sorted(visits, key=lambda visit: visit.time_in)

        return visits

    def _day_to_json_dict(self) -> dict:
        bike_visits = []
        for visit in self.all_visits():
            bike_size = (
                self.REGULAR_KEYWORD
                if self.biketags[visit.tagid].bike_type == REGULAR
                else self.OVERSIZE_KEYWORD
            )
            bike_visits.append(
                {
                    "tagid": visit.tagid,
                    "bike_size": bike_size,
                    "time_in": visit.time_in,
                    "time_out": visit.time_out,
                }
            )

        # Sort bike_visits by tagid first, then by time_in
        bike_visits.sort(key=lambda x: (x["tagid"], x["time_in"]))

        # A comment message at the top of the file.
        comment = f"This is a TagTracker datafile for {self.site_label} on {self.date}."

        ut.squawk(f"{self.notes.notes=}",cfg.DEBUG)
        return {
            "comment:": comment,
            "date": self.date,
            "opening_time": self.opening_time,
            "closing_time": self.closing_time,
            "registrations": self.registrations.num_registrations,
            "bike_visits": bike_visits,
            "regular_tagids": sorted(list(self.regular_tagids)),
            "oversize_tagids": sorted(list(self.oversize_tagids)),
            "retired_tagids": sorted(list(self.retired_tagids)),
            "notes": self.notes.notes,
            "site_name": self.site_name,
            "site_label": self.site_label,
        }

    @staticmethod
    def _day_from_json_dict(data: dict, filepath: str) -> "TrackerDay":
        day = TrackerDay(filepath)
        day.date = data["date"]
        day.opening_time = VTime(data["opening_time"])
        day.closing_time = VTime(data["closing_time"])
        try:
            reg = int(data.get("registrations", 0))
            day.registrations = Registrations(reg)
        except ValueError as e:
            raise TrackerDayError(
                f"Bad registration value in file: '{data['registrations']}'. Error {e}"
            ) from e
        day.notes.load(data["notes"])
        day.site_name = data["site_name"]
        day.site_label = data["site_label"]

        day.regular_tagids = frozenset(TagID(tagid) for tagid in data["regular_tagids"])
        day.oversize_tagids = frozenset(
            TagID(tagid) for tagid in data["oversize_tagids"]
        )
        day.retired_tagids = frozenset(TagID(tagid) for tagid in data["retired_tagids"])

        # Initialize the biketags from the tagid lists
        day.initialize_biketags()

        # Add the visits, assuring sorted by ascending time_in
        # FIXME: set the biketag.status fields
        for visit_data in sorted(
            data["bike_visits"], key=lambda x: (x["tagid"], x["time_in"])
        ):
            tagid = TagID(visit_data["tagid"])
            time_in = VTime(visit_data["time_in"])
            time_out = VTime(visit_data["time_out"])
            day.biketags[tagid].start_visit(time_in)
            if time_out:
                day.biketags[tagid].finish_visit(time_out)

        # Make sure all the visits are sorted by check_in time

        return day

    def save_to_file(self,custom_filepath:str="") -> None:
        """Save to the file.

        With defulat filepath, any errors in writing are considered catastrophic.
        For others, report the error and return False.
        """
        what_filepath = custom_filepath or self.filepath
        data = self._day_to_json_dict()
        schema = self.load_schema()
        self.validate_data(data, schema)

        # Any failure to write is a critical error
        try:
            with open(what_filepath, "w", encoding="utf-8") as file:
                json.dump(data, file, indent=4)
        except Exception:
            if custom_filepath:
                return False
            else:
                print(
                    f"\n\nCRITICAL ERROR: Unable to save data to file {what_filepath}\n\n"
                )
                raise
        return True

    @staticmethod
    def load_from_file(filepath) -> "TrackerDay":
        with open(filepath, "r", encoding="utf-8") as file:
            data = json.load(file)

        schema = TrackerDay.load_schema()
        TrackerDay.validate_data(data, schema)

        loaded_day = TrackerDay._day_from_json_dict(data, filepath)
        loaded_day.check_tagids_conformity()

        return loaded_day

    @staticmethod
    def load_schema() -> dict:
        with open("tagtracker_schema_v1.0.0.json", "r", encoding="utf-8") as file:
            return json.load(file)

    @staticmethod
    def validate_data(data: dict, schema: dict) -> None:
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
            t = TagID(tag_id)
            if t:
                tag_ids.add(t)
        return tag_ids

    def set_taglists_from_config(self):
        """Assign oversize, regular, and retired tag IDs from config."""
        self.regular_tagids = self._parse_tag_ids(REGULAR_TAGS)
        self.oversize_tagids = self._parse_tag_ids(OVERSIZE_TAGS)
        self.retired_tagids = self._parse_tag_ids(RETIRED_TAGS)
        self.check_tagids_conformity()
        if not self.biketags:
            self.initialize_biketags()

    def check_tagids_conformity(self) -> bool:
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

    def max_bikes_up_to_time(self,as_of_when:str=""):

        # FIXME: extend this for regular/oversize/total

        as_of_when = VTime(as_of_when or "now"
                           )
        # Collect all time_in and time_out events up to as_of_when
        events = []
        for visit in self.all_visits():
            if visit.time_in <= as_of_when:
                events.append((visit.time_in, 'in'))
            if visit.time_out and visit.time_out <= as_of_when:
                events.append((visit.time_out, 'out'))

        # Sort events by time then 'in' before 'out'if times are the same.
        events.sort(key=lambda x: (x[0], x[1] == 'out'))

        max_bikes = 0
        current_bikes = 0
        max_time = ""

        # Iterate through sorted events and track the number of bikes
        for event in events:
            if event[1] == 'in':
                current_bikes += 1
                if current_bikes > max_bikes:
                    max_bikes = current_bikes
                    max_time = event[0]
            elif event[1] == 'out':
                current_bikes -= 1

        return max_bikes, max_time

    def dump(self, detailed: bool = False) -> list[str]:
        """Get info about this object."""

        info = [
            f"TrackerDay for '{self.date}','{self.opening_time}'-'{self.closing_time}'"
        ]
        info.append(f"    BikeVisits: {len(self.all_visits())}")
        info.append(f"    BikeTags: {len(self.biketags)}")

        statuses = [b.status for b in self.biketags.values()]
        status_counts = {}
        for status in (BikeTag.UNUSED, BikeTag.IN_USE, BikeTag.DONE, BikeTag.RETIRED):
            status_counts[status] = len([s for s in statuses if s == status])
        info.append(
            "        Statuses: "
            + ", ".join(
                [f"{count} {status}" for status, count in status_counts.items()]
            )
        )

        types = [b.bike_type for b in self.biketags.values()]
        type_counts = {}
        for t in set(types):
            type_counts[t] = len([k for k in types if k == t])
        info.append(
            "        Bike types: "
            + ", ".join([f"{count} {typ}" for typ, count in type_counts.items()])
        )

        if not detailed:
            return info

        info.append("Detailed info now.... FIXME:")

        return info


def new_to_old(new: TrackerDay) -> OldTrackerDay:
    """Perform a lossy conversion from new to old.

    Some visits may be lost in th process, as this will
    use only the most recent visit for any tag.
    """
    return None


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
