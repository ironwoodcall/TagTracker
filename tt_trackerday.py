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
from tt_bikevisit import BikeVisit
from client_local_config import REGULAR_TAGS, OVERSIZE_TAGS, RETIRED_TAGS


class OldTrackerDay:
    """One day's worth of tracker info and its context."""

    def __init__(self) -> None:
        """Initialize blank."""
        self.date = ""
        self.opening_time = VTime("")
        self.closing_time = VTime("")
        self.registrations = 0  # FIXME: better 0 or None?
        self.bikes_in = {}
        self.bikes_out = {}
        self.regular = frozenset()
        self.oversize = frozenset()
        self.retired = frozenset()
        self.colour_letters = {}
        self.notes = []

    def all_tags(self) -> frozenset[TagID]:
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
        self.registrations = 0  # FIXME: better 0 or None?
        self.regular_tagids = frozenset()
        self.oversize_tagids = frozenset()
        self.retired_tagids = frozenset()
        self.colour_letters: dict[str, str] = {}
        self.notes: list[str] = []
        self.biketags: dict[TagID, BikeTag] = {}
        self.tagids_conform = None  # Are all tagids letter-letter-digits?
        self.filepath = filepath

    def all_tags(self) -> frozenset[TagID]:
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

        def bad_times(biketags: dict[TagID, BikeTag], listname: str) -> list[str]:
            """Get list of errors about mal-formed time values in biketags."""
            msgs = []
            for tag, bike in biketags.items():
                latest_visit = bike.latest_visit()
                if (
                    not isinstance(latest_visit.time_in, VTime)
                    or not latest_visit.time_in
                ):
                    msgs.append(
                        f"Bad time '{latest_visit.time_in}' in {listname} with key '{tag}'"
                    )
                if latest_visit.time_out and (
                    not isinstance(latest_visit.time_out, VTime)
                    or not latest_visit.time_out
                ):
                    msgs.append(
                        f"Bad time '{latest_visit.time_out}' in {listname} with key '{tag}'"
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
        errors += bad_times(self.biketags, "biketags")
        # Look for duplicates in regular and oversize tags lists
        if len(self.regular_tagids | self.oversize_tagids) != len(
            self.regular_tagids
        ) + len(self.oversize_tagids):
            errors.append("Size mismatch between regular+oversize tags and their union")
        # Look for bike checked out but not in, or check-in later than check-out
        for tag, bike in self.biketags.items():
            if bike.status == BikeTag.DONE:
                latest_visit = bike.latest_visit()
                if latest_visit.time_out < latest_visit.time_in:
                    errors.append(f"Bike {tag} check-out earlier than check-in")
        # Bikes that are not in the list of allowed bikes
        _allowed_tags = self.regular_tagids | self.oversize_tagids
        _used_tags = self.biketags.keys()
        for tag in _used_tags:
            if tag not in _allowed_tags:
                errors.append(f"Tag {tag} not in use (not regular nor oversized)")
            if tag in self.retired_tagids:
                errors.append(f"Tag {tag} is marked as retired")
        return errors

    def earliest_event(self) -> VTime:
        """Return the earliest event of the day as HH:MM (or "" if none)."""

        earliest = ""
        for b in self.biketags:
            b:BikeTag
            for v in b.visits:
                v:BikeVisit
                if not earliest or v.time_in < earliest:
                    earliest = v.time_in
                if not earliest or (v.time_out and v.time_out < earliest):
                    earliest = v.time_out
        return earliest
        # if
        # all_events = {
        #     visit.time_in for bike in self.biketags.values() for visit in bike.visits
        # }
        # if not all_events:
        #     return ""
        # return min(all_events)

    def latest_event(self, as_of_when: VTime | int | None = None) -> VTime:
        """Return the latest event of the day at or before as_of_when.

        If no events in the time period, return "".
        If as_of_when is blank or None, then this will use the whole day.
        """
        if not as_of_when:
            as_of_when = VTime("24:00")
        else:
            as_of_when = VTime(as_of_when)
            if not as_of_when:
                return ""
        events = {
            visit.time_in
            for bike in self.biketags.values()
            for visit in bike.visits
            if visit.time_in <= as_of_when
        } | {
            visit.time_out
            for bike in self.biketags.values()
            for visit in bike.visits
            if visit.time_out and visit.time_out <= as_of_when
        }
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

    @staticmethod
    def create_biketags_from_visits(visits: list[BikeVisit]) -> list[BikeTag]:
        """Create a list of BikeTag objects from a list of BikeVisit objects.

        This needs better FIXME colour detection (R/O/ret). Right now
        it guesses, which is no good.

        This is something I would need when reading a datafile.
        """
        biketags = {}
        for visit in visits:
            if visit.tagid not in biketags:
                biketags[visit.tagid] = BikeTag(
                    visit.tagid, TrackerDay.guess_tag_type(visit.tagid)
                )
            biketags[visit.tagid].visits.append(visit)
        return list(biketags.values())

    @staticmethod
    def create_visits_from_biketags(biketags: list[BikeTag]) -> list[BikeVisit]:
        """Create a list of BikeVisit objects from a list of BikeTag objects.

        Will need this to write a datafile, which is a list of visits, not tags.
        """

        visits = []
        for biketag in biketags:
            visits.extend(biketag.visits)
        return visits

    def to_dict(self) -> Dict:
        bike_visits = []
        for biketag in self.biketags.values():
            for visit in biketag.visits:
                bike_visits.append(
                    {
                        "time_in": visit.time_in.to_str(),
                        "time_out": visit.time_out.to_str() if visit.time_out else "",
                        "tagid": visit.tagid,
                    }
                )
        return {
            "date": self.date,
            "opening_time": self.opening_time,
            "closing_time": self.closing_time,
            "registrations": self.registrations,
            "bike_visits": bike_visits,
            "regular_tagids": list(self.regular_tagids),
            "oversize_tagids": list(self.oversize_tagids),
            "retired_tagids": list(self.retired_tagids),
            "notes": self.notes,
        }

    @staticmethod
    def from_dict(data: Dict, filepath: str) -> "TrackerDay":
        tracker_day = TrackerDay(filepath)
        tracker_day.date = data["date"]
        tracker_day.opening_time = VTime(data["opening_time"])
        tracker_day.closing_time = VTime(data["closing_time"])
        tracker_day.registrations = data["registrations"]
        tracker_day.regular_tagids = frozenset(data["regular_tagids"])
        tracker_day.oversize_tagids = frozenset(data["oversize_tagids"])
        tracker_day.retired_tagids = frozenset(data["retired_tagids"])
        tracker_day.notes = data["notes"]

        for visit_data in data["bike_visits"]:
            tagid = visit_data["tagid"]
            time_in = VTime(visit_data["time_in"])
            time_out = VTime(visit_data["time_out"]) if visit_data["time_out"] else None
            visit = BikeVisit(tagid, time_in)
            visit.time_out = time_out

            if tagid not in tracker_day.biketags:
                bike_type = "R" if tagid in tracker_day.regular_tagids else "O"
                tracker_day.biketags[tagid] = BikeTag(tagid, bike_type)
            tracker_day.biketags[tagid].visits.append(visit)

        return tracker_day

    def save_to_file(self) -> None:
        data = self.to_dict()
        schema = self.load_schema()
        self.validate_data(data, schema)

        with open(self.filepath, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=4)

    def load_from_file(self) -> "TrackerDay":
        with open(self.filepath, "r", encoding="utf-8") as file:
            data = json.load(file)

        schema = TrackerDay.load_schema()
        TrackerDay.validate_data(data, schema)

        self.check_tagid_formats()
        return TrackerDay.from_dict(data, self.filepath)

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
