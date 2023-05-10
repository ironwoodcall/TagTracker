"""TagTracker by Julias Hocking."""

import os
import time
import re
import pathlib
from typing import Tuple

import TrackerConfig as cfg

def get_date() -> str:
    """Return current date as string: YYYY-MM-DD."""
    localtime = time.localtime()
    year = str(localtime.tm_year)
    month = str(localtime.tm_mon)
    day = str(localtime.tm_mday)
    month = ('0'+month)[-2:] # ensure leading zeroes
    day = ('0'+day)[-2:]
    date = f"{year}-{month}-{day}"
    return date

def get_time() -> str:
    """Return current time as string: HH:MM."""
    now = time.asctime(time.localtime())[11:16]
    return now

'''
def valid_time(inp:str) -> bool:
    """Check whether inp is a valid HH:MM string."""
    # FIXME: remove all calls to valid_time(), use fix_hhmm() instead.
    return bool(fix_hhmm(inp))
'''

def fix_hhmm(inp:str) -> str:
    """Convert a string that might be a time to HH:MM (or to "").

    Return is either "" (doesn't look like a valid time) or
    will be HH:MM, always length 5 (i.e. 09:00 not 9:00)
    """
    if not (r := re.match(r"^ *([012]*[0-9]):?([0-5][0-9]) *$", inp)):
        return ""
    h = int(r.group(1))
    m = int(r.group(2))
    # Test for a possible time
    if h > 23 or m > 59:
        return ""
    # Return 5-digit time string
    return f"{h:02d}:{m:02d}"

def parse_tag(maybe_tag:str, must_be_available=False) -> list[str]:
    """Test maybe_tag as a tag, return it as tag and bits.

    Tests maybe_tag by breaking it down into its constituent parts.
    If looks like a valid tagname, returns a list of
        [tag_id, colour, tag_letter, tag_number]
    If tag is not valid, then the return list is empty []

    If must_be_available flag is True then will check whether this
    tag is in the list of all available tags (all_tags), and if
    not in the list, will return the empty list.

    Canonical tag id is a concatenation of
        tag_colour: 1+ lc letters representing the tag's colour,
                as defined in cfg.colour_letters
        tag_letter: 1 lc letter, the first character on the tag
        tag_number: a sequence number, without lead zeroes.
    """
    maybe_tag = maybe_tag.lower()
    if not bool(r := cfg.PARSE_TAG_RE.match(maybe_tag)):
        return []

    tag_colour = r.group(1)
    tag_letter = r.group(2)
    tag_number = r.group(3)
    tag_id = f"{tag_colour}{tag_letter}{tag_number}"

    if must_be_available and tag_id not in cfg.all_tags:
        return []

    return [tag_id,tag_colour,tag_letter,tag_number]

def fix_tag(maybe_tag:str, **kwargs) -> str:
    """Turn 'str' into a canonical tag name.

    Keyword must_be_available, if set True, will force
    this to only allow tags that are set as usable in config files.
    """
    bits = parse_tag(maybe_tag,
            must_be_available=kwargs.get("must_be_available"))
    return bits[0] if bits else ""

def iprint(text:str="", num_indents:int=1,**kwargs) -> None:
    """Print the text, indented num_indents times.

    Recognizes the 'end=' keyword for the print() statement.
    """
    print(f"{cfg.INDENT * num_indents}{text}",end=kwargs.get("end"))

def read_tags() -> bool:
    """Fetch tag data from file.

    Read data from a pre-existing log file, if one exists
    check for .txt file for today's date in folder called 'logs'
    e.g. "logs/2023-04-20.txt"
    if exists, read for ins and outs
    if none exists, who cares -- one will get made.
    """
    logfilename = LOG_FILEPATH
    pathlib.Path("logs").mkdir(exist_ok = True) # make logs folder if missing
    if not os.path.exists(logfilename):
        print('No previous log for today found. Starting fresh...')
        return True

    section = None
    with open(logfilename, 'r') as f:
        for line_num, line in enumerate(f, start=1):
            # ignore blank or # comment lines
            line = re.sub(r"\s*#.*","", line)
            line = line.strip()
            if not line:
                continue
            # Look for section headers
            if (re.match(r"^Bikes checked in.*:",line)):
                section = "in"
                continue
            elif (re.match(r"^Bikes checked out.*:", line)):
                section = "out"
                continue
            # Can do nothing unless we know what section we're in
            if section is None:
                print(f"weirdness in line {line_num} of {logfilename}")
                return False
            # Break into putative tag and text, looking for errors
            cells = line.split(',')
            if len(cells) != 2:
                print(f"Bad line in file {logfilename} line {line_num}.")
                return False
            if not (this_tag := fix_tag(cells[0],must_be_available=True)):
                print("Poorly formed or unrecognized tag in file"
                        f" {logfilename} line {line_num}.")
                return False
            if not (this_time := fix_hhmm(cells[1])):
                print("Time value poorly formed in file"
                        f" {logfilename} line {line_num}.")
                return False
            # Maybe add to check_ins or check_outs structures.
            if section == "in":
                # Maybe add to check_in structure
                if this_tag in check_ins:
                    print(f"Duplicate {this_tag} check-in found at "
                            f"line {line_num}")
                    return False
                if this_tag in check_outs and check_outs[this_tag] < this_time:
                    print(f"Tag {this_tag} check out before check-in"
                            f" in file {logfilename}")
                check_ins[this_tag] = this_time
            elif section == "out":
                if this_tag in check_outs:
                    print(f"Duplicate {this_tag} check-out found at "
                            f"line {line_num}")
                    return False
                if this_tag in check_ins and check_ins[this_tag] > this_time:
                    print(f"Tag {this_tag} check out before check-in"
                            f" in file {logfilename}")
                    return False
                check_outs[this_tag] = this_time
            else:
                print("should not reach this code spot 876238746")
    print('Previous log for today successfully loaded')
    return True
'''
def read_tags_OLD() -> bool:
    """Fetch tag data from file.

    Read data from a pre-existing log file, if one exists
    check for .txt file for today's date in folder called 'logs'
    e.g. "logs/2023-04-20.txt"
    if exists, read for ins and outs
    if none exists, make one.
    """
    #FIXME: Refactor
    pathlib.Path("logs").mkdir(exist_ok = True) # make logs folder if missing
    try: # read saved stuff into dicts
        filedir = LOG_FILEPATH
        with open(filedir, 'r') as f:
            line = f.readline() # read check ins header
            line = f.readline() # read first tag entry if exists
            line_counter = 2 # track line number

            # FIXME: rather than checking for in all_tags, maybe check
            # the potential with parse_tag(cell[0],must_be_available=True)
            # rather than the first character not being 'B'
            while line[0] != 'B': # if first char isn't the start of the header
                cells = line.rstrip().split(',')
                # if either a tag or time is invalid...
                if not cells[0] in cfg.all_tags or not valid_time(cells[1]):
                    print(f"Problem while reading {filedir} -- check-ins, "
                          f"line {line_counter}.")
                    return False
                elif cells[0] in check_ins:
                    print(f"Duplicate {cells[0]} check-in found at "
                          f"line {line_counter}")
                    return False
                check_ins[cells[0]] = cells[1]
                line = f.readline() # final will load the check outs header
                line_counter += 1 # increment line counter
            line = f.readline()
            line_counter += 1
            while line != '':
                cells = line.rstrip().split(',')
                if not cells[0] in cfg.all_tags or not valid_time(cells[1]):
                    print(f"Problem while reading {filedir} -- check-outs, "
                          f"line {line_counter}.")
                    return False
                elif cells[0] in check_outs:
                    print(f"Duplicate {cells[0]} check-out found at "
                          f"line {line_counter}")
                    return False
                check_outs[cells[0]] = cells[1]
                line = f.readline() # final will load trailing empty line
                line_counter += 1 # increment line counter
        print('Previous log for today successfully loaded')
    except FileNotFoundError: # if no file, don't read it lol
        print('No previous log for today found. Starting fresh...')
    return True
'''

def rotate_log() -> None:
    """Rename the current log to <itself>.bak."""
    backuppath = f"{LOG_FILEPATH}.bak"
    if os.path.exists(backuppath):
        os.unlink(backuppath)
    if os.path.exists(LOG_FILEPATH):
        os.rename(LOG_FILEPATH,backuppath)
    return None

def write_tags() -> None:
    """Write current data to today's log file."""
    lines = []
    lines.append('Bikes checked in / tags out:')
    for tag in check_ins: # for each bike checked in
        lines.append(f'{tag},{check_ins[tag]}') # add a line "tag,time"

    lines.append('Bikes checked out / tags in:')
    for tag in check_outs: # for each  checked
        lines.append(f'{tag},{check_outs[tag]}') # add a line "tag,time"

    with open(LOG_FILEPATH, 'w') as f: # write stored lines to file
        for line in lines:
            f.write(line)
            f.write('\n')

def time_str_to_minutes(HHMM:str) -> int:
    """Convert time string HH:MM to number of minutes."""
    cells = HHMM.split(':')
    hrs = int(cells[0])
    mins = int(cells[1])
    mins += hrs * 60
    return mins

def minutes_to_time_str(time_in_minutes:int) -> str:
    """Convert a time in minutes to a HH:MM string."""
    hours_portion = time_in_minutes // 60
    minutes_portion = time_in_minutes - 60*hours_portion
    time_as_text = f"{hours_portion}:{minutes_portion:02d}"
    return time_as_text

def find_tag_durations(include_bikes_on_hand=True) -> dict[str,int]:
    """Make dict of tags with their stay duration in minutes.

    If include_bikes_on_hand, this will include checked in
    but not returned out.  If False, only bikes returned out.
    """

    timenow = time_str_to_minutes(get_time())
    tag_durations = {}
    for tag,in_str in check_ins.items():
        in_minutes = time_str_to_minutes(in_str)
        if tag in check_outs:
            out_minutes = time_str_to_minutes(check_outs[tag])
            tag_durations[tag] = out_minutes-in_minutes
        elif include_bikes_on_hand:
            tag_durations[tag] = timenow - in_minutes
    # Any bike stays that are zero minutes, arbitrarily call one minute.
    for tag,duration in tag_durations.items():
        if duration < 1:
            tag_durations[tag] = 1
    return tag_durations

def calc_stays() -> list[int]:
    """Calculate how long each tag has stayed in the bikevalet.

    (Leftovers aren't counted as stays for these purposes)
    """
    #FIXME: Refactor (see issue #11)
    global shortest_stay_tags_str
    global longest_stay_tags_str
    global min_stay
    global max_stay
    stays = []
    tags = []
    for tag in check_ins:
        time_in = time_str_to_minutes(check_ins[tag])
        if tag in check_outs:
            time_out = time_str_to_minutes(check_outs[tag])
        else:
            time_out = time_str_to_minutes(get_time())
        stay = max(time_out - time_in,1)    # If zero just call it one minute.
        stays.append(stay)
        tags.append(tag) # add to list of tags in same order for next step
    min_stay = min(stays)
    max_stay = max(stays)
    shortest_stay_tags = [tags[i] for i in range(len(stays))
            if stays[i] == min_stay]
    longest_stay_tags = [tags[i] for i in range(len(stays))
            if stays[i] == max_stay]
    shortest_stay_tags_str = ', '.join(shortest_stay_tags)
    longest_stay_tags_str = ', '.join(longest_stay_tags)
    return stays

def median_stay(stays:list) -> int:
    """Compute the median of a list of stay lengths."""
    stays = sorted(stays) # order by length
    quantity = len(stays)
    if quantity % 2 == 0: # even number of stays
        halfway = int(quantity/2)
        mid_1 = stays[halfway - 1]
        mid_2 = stays[halfway]
        median = (mid_1 + mid_2)/2
    else: # odd number of stays
        median = stays[quantity//2]
    return median

def mode_stay(stays:list) -> Tuple[int,int]:
    """Compute the mode for a list of stay lengths.

    (rounds stays)
    """
    round_stays = []
    for stay in stays:
        remainder = stay % cfg.MODE_ROUND_TO_NEAREST
        mult = stay // cfg.MODE_ROUND_TO_NEAREST
        if remainder > 4:
            mult += 1
        rounded = mult * cfg.MODE_ROUND_TO_NEAREST
        round_stays.append(rounded)
    mode = max(set(round_stays), key=round_stays.count)
    count = stays.count(mode)
    return mode, count

def show_stats():
    """Show # of bikes currently in, and statistics for day end form."""
    norm = 0 # counting bikes by type
    over = 0
    for tag in check_ins:
        if tag in cfg.normal_tags:
            norm += 1
        elif tag in cfg.oversize_tags:
            over += 1
    tot_in = norm + over

    if len(check_outs) > 0: # if any bikes have completed their stay, do stats
        AM_ins = 0
        PM_ins = 0
        for tag in check_ins:
            hour = int(check_ins[tag][:2]) # first 2 characters of time string
            if hour >= 12: # if bike checked in after noon (inclusive)
                PM_ins += 1
            else:
                AM_ins += 1
        # calculate stats
        all_stays = calc_stays()
        mean = round(sum(all_stays)/len(all_stays))
        median = round(median_stay(all_stays))
        mode, count = mode_stay(all_stays)

        # Find num of stays between various time values.
        short_stays = 0
        medium_stays = 0
        long_stays = 0
        for stay in all_stays: # count stays over/under x time
            if stay < cfg.T_UNDER:
                short_stays += 1
            elif stay <= cfg.T_OVER: # middle bracket contains the edge cases
                medium_stays += 1
            else:
                long_stays += 1
        hrs_under = f"{(cfg.T_UNDER / 60):3.1f}" # in hours for print clarity
        hrs_over = f"{(cfg.T_OVER / 60):3.1f}"

        print()
        iprint("Summary statistics "
               f"({len(check_ins)-len(check_outs)} bikes still on hand):\n")
        iprint(f"Total bikes:    {tot_in:3d}")
        iprint(f"AM bikes:       {AM_ins:3d}")
        iprint(f"PM bikes:       {PM_ins:3d}")
        iprint(f"Regular:        {norm:3d}")
        iprint(f"Oversize:       {over:3d}")
        print()
        iprint(f"Stays < {hrs_under}h:   {short_stays:3d}")
        iprint(f"Stays {hrs_under}-{hrs_over}h: {medium_stays:3d}")
        iprint(f"Stays > {hrs_over}h:   {long_stays:3d}")
        print()
        iprint(f"Max stay:     {minutes_to_time_str(max_stay):>5}   "
               f"[tag(s) {longest_stay_tags_str}]")
        iprint(f"Min stay:     {minutes_to_time_str(min_stay):>5}   "
               f"[tag(s) {shortest_stay_tags_str}]")
        iprint(f"Mean stay:    {minutes_to_time_str(mean):>5}")
        iprint(f"Median stay:  {minutes_to_time_str(median):>5}")
        iprint(f"Mode stay:    {minutes_to_time_str(mode):>5} "
               f"by {count} bike(s)  [{cfg.MODE_ROUND_TO_NEAREST} minute "
               "blocks]")

    else: # don't try to calculate stats on nothing
        iprint("No bikes returned out, can't calculate statistics. "
               f"({tot_in} bikes currently checked in.)")

def delete_entry(args:list[str]) -> None:
    """Perform tag entry deletion dialogue."""
    (target,which_to_del,confirm) = (args + [None,None,None])[:3]
    if target:
        target = fix_tag(target,must_be_available=False)
    if not target:
        target = False
    del_syntax_message = ("Syntax: d <tag> <both or check-out only"
            " (b/o)> <optional pre-confirm (y)>")
    if not(target in [False] + cfg.all_tags or which_to_del in [False,'b','o']
           or confirm in [False, 'y']):
        iprint(del_syntax_message) # remind of syntax if invalid input
        return None # interrupt
    if not target: # get target if unspecified
        iprint("Which tag's entry would you like to remove?")
        target = input(f"(tag name) {cfg.CURSOR}").lower()
    checked_in = target in check_ins
    checked_out = target in check_outs
    if not checked_in and not checked_out:
        iprint(f"'{target}' isn't in today's records (Cancelled deletion).")
    elif checked_out: # both events recorded
        time_in_temp = check_ins[target]
        time_out_temp = check_outs[target]
        if not which_to_del: # ask which to del if not specified
            iprint(f"This tag has both a check-in ({time_in_temp}) and "
                   f"a check-out ({time_out_temp}) recorded.")
            iprint("Do you want to delete (b)oth events, "
                   "or just the check-(o)ut?")
            which_to_del = input(f"(b/o) {cfg.CURSOR}").lower()
        if which_to_del == 'b':
            if confirm == 'y': # pre-confirmation
                sure = True
            else:
                iprint("Are you sure you want to delete both events "
                       f"for {target}? (y/N)")
                sure = input(f"(y/N) {cfg.CURSOR}").lower() == 'y'
            if sure:
                check_ins.pop(target)
                check_outs.pop(target)
                iprint(f"Deleted all records today for {target} "
                       f"(in at {time_in_temp}, out at {time_out_temp}).")
            else:
                iprint("Cancelled deletion.")

        elif which_to_del == 'o': # selected to delete
            if confirm == 'y':
                sure = True
            else:
                iprint("Are you sure you want to delete the "
                       f"check-out record for {target}? (y/N)")
                sure = input(f"(y/N) {cfg.CURSOR}").lower() == 'y'

            if sure:
                time_temp = check_outs[target]
                check_outs.pop(target)
                iprint(f"Deleted today's {time_temp} check-out for {target}.")
            else:
                iprint("Cancelled deletion.")
        else:
            iprint("Cancelled deletion.")
    else: # checked in only
        time_in_temp = check_ins[target]
        if which_to_del in ['b', False]:
            if confirm == 'y':
                sure = True
            else: # check
                iprint("This tag has only a check-in recorded. "
                       "Are you sure you want to delete it? (y/N)")
                sure = input(f"(y/N) {cfg.CURSOR}").lower() == 'y'
            if sure:
                time_temp = check_ins[target]
                check_ins.pop(target)
                iprint(f"Deleted today's {time_temp} check-in for {target}.")
            else:
                iprint("Cancelled deletion.")
        else:#  which_to_del == 'o':
            iprint(f"{target} has only a check-in ({time_in_temp}) recorded; "
                   "can't delete a nonexistent check-out.")

def query_tag(args:list[str]) -> None:
    target = (args + [None])[0]

    """Query the check in/out times of a specific tag."""
    if not target: # only do dialog if no target passed
        iprint("Which tag would you like to query?")
        target = input(f"(tag name) {cfg.CURSOR}").lower()
    fixed_target = fix_tag(target,must_be_available=True)
    if not fixed_target:
        iprint(f"Tag {target} is not available (retired, does not exist, etc).")
        return
    elif fixed_target not in check_ins:
        iprint(f"'{fixed_target}' isn't in today's records.")
        return
    iprint(f"{fixed_target} checked IN at {check_ins[fixed_target]}")
    if fixed_target in check_outs:
        iprint(f"{fixed_target} returned OUT at {check_outs[fixed_target]}")
    else:
        iprint(f"{target} not returned out and is still on hand.")

def prompt_for_time(inp = False) -> bool or str:
    """Prompt for a time input if needed.

    Helper for edit_entry(); if no time passed in, get a valid
    24h time input from the user and return an HH:MM string.
    """
    if not inp:
        iprint("What is the correct time for this event?")
        iprint("Use 24-hour format, or 'now' to use "
               f"the current time ({get_time()})")
        inp = input(f"(HH:MM) {cfg.CURSOR}").lower()
    if inp == 'now':
        return get_time()
    HHMM = fix_hhmm(inp)
    if not HHMM:
        return False
    return HHMM

def edit_entry(args:list[str]):
    """Perform Dialog to correct a tag's check in/out time."""
    (target, in_or_out, new_time) = (args + [None,None,None])[:3]

    edit_syntax_message = ("Syntax: e <bike's tag> <in or out (i/o)> "
            "<new time or 'now'>")
    if not target:
        iprint("Which bike's record do you want to edit?")
        target = input(f"(tag ID) {cfg.CURSOR}").lower()
    elif not target in cfg.all_tags:
        iprint(edit_syntax_message)
        return False
    if target in cfg.all_tags:
        if target in check_ins:
            if not in_or_out:
                iprint("Do you want to change this bike's "
                       "check-(i)n or check-(o)ut time?")
                in_or_out = input(f"(i/o) {cfg.CURSOR}").lower()
                if not in_or_out in ['i','o']:
                    iprint(f"'{in_or_out}' needs to be 'i' or 'o' "
                           "(cancelled edit).")
                    return False
            if not in_or_out in ['i','o']:
                iprint(edit_syntax_message)
            else:
                new_time = prompt_for_time(new_time)
                if new_time == False:
                    iprint('Invalid time entered (cancelled edit).')
                elif in_or_out == 'i':
                    if (target in check_outs and
                            (time_str_to_minutes(new_time) >
                            time_str_to_minutes(check_outs[target]))):
                        iprint("Can't set a check-IN later than a check-OUT;")
                        iprint(f"{target} returned OUT at {check_outs[target]}")
                    else:
                        iprint(f"Check-IN time for {target} "
                               f"changed to {new_time}.")
                        check_ins[target] = new_time
                elif in_or_out == 'o':
                    if (time_str_to_minutes(new_time) <
                            time_str_to_minutes(check_ins[target])):
                        # don't check a tag out earlier than it checked in
                        iprint("Can't set a check-OUT earlier than check-IN;")
                        iprint(f"{target} checked IN at {check_ins[target]}")
                    else:
                        iprint(f"Check-OUT time for {target} "
                               f"changed to {new_time}.")
                        check_outs[target] = new_time
        else:
            iprint(f"{target} isn't in today's records (cancelled edit).")
    else:
        iprint(f"'{target}' isn't a valid tag (cancelled edit).")

def count_colours(inv:list[str]) -> str:
    """Return a string describing number of tags by colour.

    Count the number of tags corresponding to each config'd colour abbreviation
    in a given list, and return results as a str. Probably avoid calling
    this on empty lists
    """
    # FIXME: this function no longer required, replaced by audit_report()
    just_colour_abbreviations = []
    for tag in inv: # shorten tags to just their colours
        shortened = ''
        for char in tag: # add every letter character to start
            if not char.isdigit():
                shortened += char
        # cut off last, non-colour letter and add to list of abbrevs
        if shortened in cfg.colour_letters:
            just_colour_abbreviations.append(shortened)
        else:
            for x in range(10):
                cutoff_by_x = shortened[:-x]
                if cutoff_by_x in cfg.colour_letters:
                    just_colour_abbreviations.append(cutoff_by_x)

    colour_count = {} # build the count dictionary
    for abbrev in cfg.colour_letters.keys():
        # for each valid colour, check all tags
        if abbrev in just_colour_abbreviations:
            this_colour_count = 0
            for tag in just_colour_abbreviations:
                if tag == abbrev:
                    this_colour_count += 1
            colour_name = cfg.colour_letters[abbrev]
            colour_count[colour_name] = this_colour_count

    colour_count_str = '' # convert count dict to string
    for colour in colour_count:
        colour_count_str += f",  {colour} x {colour_count[colour]}"
    colour_count_str = colour_count_str[3:] # cut off leading comma

    return colour_count_str

def tags_by_prefix(tags_dict:dict) -> dict:
    """Rtn tag prefixes with list of associated tag numbers."""

    prefixes = {}
    for tag in tags_dict:
        #(prefix,t_number) = cfg.PARSE_TAG_PREFIX_RE.match(tag).groups()
        (t_colour,t_letter,t_number) = parse_tag(tag,must_be_available=False)[1:4]
        prefix = f"{t_colour}{t_letter}"
        if prefix not in prefixes:
            prefixes[prefix] = []
        prefixes[prefix].append(int(t_number))
    for numbers in prefixes.values():
        numbers.sort()
    return prefixes

def audit_report(args:list[str]) -> None:
    """Create & display audit report as at a particular time.

    On entry: as_of_when_args is a list that can optionally
    have a first element that's a time at which to make this for.

    This is smart about any checkouts that are alter than as_of_when.
    If as_of_when is missing, then counts as of current time.
    (This is replacement for existing show_audit function.)
    Reads:
        check_ins
        check_outs
        cfg.colour_letters
        cfg.normal_tags
        cfg.oversize_tags
    """
    # FIXME: this is long and could get broken up with helper functions
    rightnow = get_time()
    as_of_when = (args + [rightnow])[0]

    # What time will this audit report reflect?
    as_of_when = fix_hhmm(as_of_when)
    if not as_of_when:
        iprint( f"Unrecognized time passed to audit ({args[0]})")
        return False

    # Get rid of any check-ins or -outs later than the requested time.
    # (Yes I know there's a slicker way to do this but this is nice and clear.)
    check_ins_to_now = {}
    for (tag,ctime) in check_ins.items():
        if ctime <= as_of_when:
            check_ins_to_now[tag] = ctime
    check_outs_to_now = {}
    for (tag,ctime) in check_outs.items():
        if ctime <= as_of_when:
            check_outs_to_now[tag] = ctime
    bikes_on_hand = {}
    for (tag,ctime) in check_ins_to_now.items():
        if tag not in check_outs_to_now:
            bikes_on_hand[tag] = ctime

    num_bikes_on_hand = len(bikes_on_hand)
    normal_in = 0
    normal_out = 0
    oversize_in = 0
    oversize_out = 0

    # This assumes that any tag not a normal tag is an oversize tag
    for tag in check_ins_to_now:
        if tag in cfg.normal_tags:
            normal_in += 1
            if tag in check_outs_to_now:
                normal_out += 1
        else:
            oversize_in += 1
            if tag in check_outs_to_now:
                oversize_out += 1
    # Sums
    sum_in = normal_in + oversize_in
    sum_out = normal_out + oversize_out
    sum_total = sum_in - sum_out
    # Tags broken down by prefix (for tags matrix)
    prefixes_on_hand = tags_by_prefix(bikes_on_hand)
    prefixes_returned_out = tags_by_prefix(check_outs_to_now)
    returns_by_colour = {}
    for prefix,numbers in prefixes_returned_out.items():
        colour_code = prefix[:-1]   # prefix without the tag_letter
        if colour_code not in returns_by_colour:
            returns_by_colour[colour_code] = len(numbers)
        else:
            returns_by_colour[colour_code] += len(numbers)

    # Audit report header.
    print()
    if as_of_when == rightnow:
        iprint( f"Audit report as at current time ({rightnow})")
    elif as_of_when > rightnow:
        iprint(f"Audit report guessing at future state (as at {as_of_when})")
    else:
        iprint(f"Audit report for past state (as at {as_of_when})")
    print()

    # Audit summary section.
    iprint( "Summary             Regular Oversize Total")
    iprint(f"Bikes checked in:     {normal_in:4d}    {oversize_in:4d}"
           f"    {sum_in:4d}")
    iprint(f"Bikes returned out:   {normal_out:4d}    {oversize_out:4d}"
           f"    {sum_out:4d}")
    iprint(f"Bikes in valet:       {(normal_in-normal_out):4d}"
           f"    {(oversize_in-oversize_out):4d}    {sum_total:4d}")
    if (sum_total != num_bikes_on_hand):
        iprint( "** Totals mismatch, expected total "
               f"{num_bikes_on_hand} != {sum_total} **")

    # Tags matrixes
    no_item_str = "  "  # what to show when there's no tag
    print()
    # Bikes returned out -- tags matrix.
    iprint( "Tags on bikes in valet:")
    for prefix in sorted(prefixes_on_hand.keys()):
        numbers = prefixes_on_hand[prefix]
        line = f"{prefix.upper():3>} "
        for i in range(0,max(numbers)+1):
            s = f"{i:02d}" if i in numbers else no_item_str
            line = f"{line} {s}"
        iprint(line)
    if not prefixes_on_hand:
        iprint( "-no bikes-")
    print()

    # Bikes returned out -- tags matrix.
    bikes_out_title = "Bikes returned out ("
    for colour_code in sorted(returns_by_colour.keys()):
        num = returns_by_colour[colour_code]
        bikes_out_title = (f"{bikes_out_title}{num} "
                f"{cfg.colour_letters[colour_code].title()}, ")
    bikes_out_title = f"{bikes_out_title}{sum_out} Total)"
    iprint(bikes_out_title)
    for prefix in sorted(prefixes_returned_out.keys()):
        numbers = prefixes_returned_out[prefix]
        line = f"{prefix.upper():3>} "
        for i in range(0,max(numbers)+1):
            s = f"{i:02d}" if i in numbers else no_item_str
            line = f"{line} {s}"
        iprint(line)
    if not prefixes_returned_out:
        iprint( "-no bikes-")

    return

def show_audit() -> None:
    """Perform audit function.

    Prints a list of all tags that should be in the corral
    and bikes that should be on hand.  Format to be easy to use
    during mid-day reconciliations.
    """
    # FIXME: can delete this function once happy with new audit
    if len(check_ins) - len(check_outs) > 0: # if bikes are in
        corral = []
        for tag in check_ins:
            if not tag in check_outs: # tags that are still checked in
                corral.append(tag)
        corral = sorted(corral) # alphabetize!
        corral_str = '  '.join(map(str,corral)) # stringify
        iprint('Bikes currently checked in...')
        iprint(f"by colour:     {count_colours(corral)}", 2)
        iprint(f"individually:  {corral_str}\n", 2)
    else:
        iprint('No bikes currently checked in.')

    if len(check_outs) > 0:
        basket = []
        for tag in check_outs: # put checked out tags into list
            basket.append(tag)
        basket = sorted(basket) # alphabetize
        basket_str = '  '.join(map(str,basket)) # stringify
        iprint( "Tags that should be in the return basket:")
        iprint(f"by colour:     {count_colours(basket)}", 2)
        iprint(f"individually:  {basket_str}", 2)
    else:
        iprint('No tags should be in the basket.')

def tag_check(tag:str) -> None:
    """Check a tag in or out.

    This processes a prompt that's just a tag ID.
    """
    if tag in cfg.retired_tags: # if retired print specific retirement message
        iprint(f"{tag} is retired.")
    else: # must not be retired so handle as normal
        if tag in check_ins:
            if tag in check_outs:# if tag has checked in & out
                query_tag(tag)
                iprint(f"Overwrite {check_outs[tag]} check-out with "
                       f"current time ({get_time()})? (y/N)")
                sure = input(f"(y/N) {cfg.CURSOR}") == 'y'
                if sure:
                    edit_entry([tag, 'o', get_time()])
                else:
                    iprint("Cancelled")
            else:# checked in only
                now_mins = time_str_to_minutes(get_time())
                check_in_mins = time_str_to_minutes(check_ins[tag])
                time_diff_mins = now_mins - check_in_mins
                if time_diff_mins < cfg.CHECK_OUT_CONFIRM_TIME: # if < 1/2 hr
                    iprint("This bike checked in at "
                           f"{check_ins[tag]} ({time_diff_mins} mins ago).")
                    iprint("Do you want to check it out? (Y/n)")
                    sure = input(f"(Y/n) {cfg.CURSOR}").lower() in ['', 'y']
                else: # don't check for long stays
                    sure = True
                if sure:
                    check_outs[tag] = get_time()# check it out
                    iprint(f"**{tag} returned OUT**")
                else:
                    iprint("Cancelled return bike out")
        else:# if string is in neither dict
            check_ins[tag] = get_time()# check it in
            iprint(f"{tag} checked IN")

def parse_command( user_input:str ) -> list[str]:
    """Parse user's input into list of [tag] or [command, command args].

    Returns [] if not a recognized tag or command.
    """
    if not (user_input := user_input.lower().strip()):
        return []
    # Special case - if user input starts with '/' or '?' add a space.
    if user_input[0] in ["/","?"]:
        user_input = user_input[0] + " " + user_input[1:]
    # Split to list, test to see if tag.
    input_tokens = user_input.split()
    command = fix_tag( input_tokens[0], must_be_available=True)
    if command:
        return [command]    # A tag
    # See if it is a recognized command.
    # cfg.command_aliases is dict of lists of aliases keyed by
    # canonical command name (e.g. {"edit":["ed","e","edi"], etc})
    command = None
    for c, aliases in cfg.COMMANDS.items():
        if input_tokens[0] in aliases:
            command = c
            break
    # Is this an unrecognized command?
    if not command:
        return [cfg.CMD_UNKNOWN]
    # We have a recognized command, return it with its args.
    input_tokens[0] = command
    return input_tokens

def main():
    """Run main program loop and dispatcher."""
    done = False
    while not done:
        user_str = input(f"\nBike tag or command {cfg.CURSOR}")
        tokens = parse_command(user_str)
        if not tokens:
            continue        # No input, ignore
        (cmd, *args) = tokens
        # Dispatcher
        data_dirty = False
        match cmd:
            case cfg.CMD_EDIT:
                edit_entry(args)
                data_dirty = True
            case cfg.CMD_AUDIT:
                audit_report(args)
            case cfg.CMD_DELETE:
                delete_entry(args)
                data_dirty = True
            case cfg.CMD_EDIT:
                edit_entry(args)
                data_dirty = True
            case cfg.CMD_EXIT:
                done = True
            case cfg.CMD_HELP:
                print(cfg.help_message)
            case cfg.CMD_QUERY:
                query_tag(args)
            case cfg.CMD_STATS:
                show_stats()
            case cfg.CMD_UNKNOWN:
                iprint("Unrecognized tag or command.")
                iprint("Enter 'h' for help.")
            case _:
                # This is a tag
                tag_check(cmd)
                data_dirty = True
        # Save if anything has changed
        if data_dirty:
            rotate_log()
            write_tags()
            data_dirty = False

'''
# This is a model for a potential way to structure do_stuff commands,
# particularly ones that might prompt for missing args
def do_edit( args:list[str] ):
    (target, in_or_out, new_time) = (args + [None,None,None])[:3]

    # Action is identified as 'edit'
    tag = get_token( arg[0],optional=False,prompt="Edit what tag?" )
    if not (tag := fix_tag( tag, must_be_available=True)):
        ...error...
        return
    in_out = get_token( arg[1],optional=False,prompt="Change (i)n or (o)ut time?")
    if not (in_out useful):
        ...error...
        return
    newtime = get_token( arg[2], optional=False, prompt="Change to what time (blank for now):",default="")
    if not (newtime := fix_hhmm(newtime)):
        ...error...
        return
    confirm = get_token( arg[3], optional=False,prompt="Change (Y/n):",default="y')
   (etc)
'''

'''
def process_prompt__OLD(prompt:str) -> None:
    """Process one user-input command.

    This is the logic for main loop
    """
    cells = prompt.strip().split() # break into each phrase -- already .lower()
    if not cells:
        return False

    kwd = cells[0] # take first phrase as fn to call
    if cells[0][0] in ['?', '/'] and len(cells[0])>1:
    # take non-letter query prompts without space
        query_tag(cells[0][1:])
    elif kwd in cfg.statistics_kws:
        show_stats()
    elif kwd in cfg.help_kws:
        print(cfg.help_message)
    elif kwd in cfg.audit_kws:
        # Audit report takes an optional timestamp.
        audit_report( None if len(cells) == 1 else cells[1])
        ## show_audit()
    elif kwd in cfg.edit_kws:
        args = len(cells) - 1 # number of arguments passed
        target, in_or_out, new_time = None, None, None # initialize all
        if args > 0:
            target = cells[1]
        if args > 1:
            in_or_out = cells[2]
        if args > 2:
            new_time = cells[3]
        edit_entry([target, in_or_out, new_time])

    elif kwd in cfg.del_kws:
        args = len(cells) - 1 # number of arguments passed
        target, which_to_del, pre_confirm = False, False, False
        if args > 0:
            target = cells[1]
        if args > 1:
            which_to_del = cells[2]
        if args > 2:
            pre_confirm = cells[3]
        delete_entry([target, which_to_del,pre_confirm])

    elif kwd in cfg.query_kws:
        try:
            query_tag([cells[1]]) # query the tag that follows cmd
        except IndexError:
            query_tag([]) # if no tag passed run the dialog
    elif kwd in cfg.quit_kws:
        exit() # quit program
    elif (a_tag := fix_tag(kwd,must_be_available=True)) and a_tag:
        tag_check(a_tag)
    else: # not anything recognized so...
        iprint(f"'{prompt}' isn't a recognized tag or command "
                "(type 'help' for a list of these).")

def main_OLD() -> None:
    """Run main program loop."""
    while True:
        #show_audit() # show all bikes currently in
        prompt = input(f"\nEnter a tag or command {cfg.CURSOR}").lower()
        process_prompt(prompt)
        rotate_log()
        write_tags() # save before input regardless
'''
# STARTUP
if not cfg.SETUP_PROBLEM: # no issue flagged while reading config
    check_ins = {}
    check_outs = {}

    print(f"TagTracker {cfg.VERSION} by Julias Hocking")
    DATE = get_date()
    LOG_FILEPATH = f"logs/{cfg.LOG_BASENAME}{DATE}.log"

    if read_tags(): # only run main() if tags read successfully
        main()
    else: # if read_tags() problem
        print(f"\n{cfg.INDENT}Closing automatically in 30 seconds...")
        time.sleep(30)
else:
    print(f"\n{cfg.INDENT}Closing automatically in 30 seconds...")
    time.sleep(30)
