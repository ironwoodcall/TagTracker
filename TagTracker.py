"""TagTracker by Julias Hocking."""

import os
import time
import re
import pathlib
from typing import Tuple,Union
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

def time_as_int(maybe_time:Union[str,int]) -> Union[int,None]:
    """Return maybe_time (str or int) to number of minutes since midnight or "".

        Input can be int (minutes since midnight) or a string
    that might be a time in HH:MM.

    Return is either None (doesn't look like a valid time) or
    will be an integer between 0 and 1440.

    Warning: edge case: if given "00:00" or 0, this will return 0,
    which can test as False in a boolean argument.  In cases where 0
    might be a legitimate time, test for the type of the return or
    test whether "is None".
    """
    if isinstance(maybe_time,str):
        if not (r := re.match(r"^ *([012]*[0-9]):?([0-5][0-9]) *$", maybe_time)):
            return None
        h = int(r.group(1))
        m = int(r.group(2))
        # Test for an impossible time
        if h > 24 or m > 59 or (h * 60 + m) > 1440:
            return None
        return h * 60 + m
    if isinstance(maybe_time,int):
        # Test for impossible time.
        if not (0 <= maybe_time <= 1440):
            return None
        return maybe_time
    # Not an int, not a str.
    print(text_style(f"PROGRAM ERROR: called time_as_int({maybe_time=})",
            style=cfg.ERROR_STYLE))
    return None

def time_as_str(maybe_time:Union[int,str]) -> str:
    """Return inp (wich is str or int) to HH:MM, or "".

    Input can be int (minutes since midnight) or a string
    that might be a time in HH:MM.

    Return is either "" (doesn't look like a valid time) or
    will be HH:MM, always length 5 (i.e. 09:00 not 9:00)
    """
    if isinstance(maybe_time,str):
        if not (r := re.match(r"^ *([012]*[0-9]):?([0-5][0-9]) *$", maybe_time)):
            return ""
        h = int(r.group(1))
        m = int(r.group(2))
        # Test for an impossible time
        if h > 24 or m > 59 or (h * 60 + m) > 1440:
            return ""
    elif not isinstance(maybe_time,int):
        print(text_style(f"PROGRAM ERROR: called time_as_str({maybe_time=})",
                style=cfg.ERROR_STYLE))
        return ""
    elif isinstance(maybe_time,int):
        # Test for impossible time.
        if not (0 <= maybe_time <= 1440):
            return ""
        h = maybe_time // 60
        m = maybe_time % 60
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

def sort_tags( unsorted:list[str]) -> list[str]:
    """Sorts a list of tags (smart eg about wa12 > wa7)."""
    newlist = []
    for tag in unsorted:
        bits = parse_tag(tag,must_be_available=False)
        newlist.append(f"{bits[1]}{bits[2]}{int(bits[3]):04d}")
    newlist.sort()
    newlist = [fix_tag(t) for t in newlist]
    return newlist

def text_style(text:str, style=None) -> str:
    """Return text with style 'style' applied."""
    if not cfg.USE_COLOUR:
        return text
    if not style:
        style = cfg.NORMAL_STYLE
    if style not in cfg.STYLE:
        iprint(f"*** PROGRAM ERROR: Unknown style '{style}' ***",
               style=cfg.ERROR_STYLE)
        return "!!!???"
    return f"{cfg.STYLE[style]}{text}{cfg.STYLE[cfg.RESET_STYLE]}"

def iprint(text:str="", num_indents:int=1, style=None,end="\n") -> None:
    """Print the text, indented num_indents times.

    Recognizes the 'end=' keyword for the print() statement.
    """
    if style:
        text = text_style(text,style=style)
    print(f"{cfg.INDENT * num_indents}{text}",end=end)

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
        iprint('No existing log for today found. Creating new log.',
               style=cfg.SUBTITLE_STYLE)
        return True
    iprint(f"Loading data from existing log file {logfilename}...",
           style=cfg.SUBTITLE_STYLE)
    errors = 0  # How many errors found reading logfile?
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
                iprint(f"weirdness in line {line_num} of {logfilename}",
                       style=cfg.ERROR_STYLE)
                errors += 1
                continue
            # Break into putative tag and text, looking for errors
            cells = line.split(',')
            if len(cells) != 2:
                iprint(f"Bad line in file {logfilename} line {line_num}",
                       style=cfg.ERROR_STYLE)
                errors += 1
                continue
            if not (this_tag := fix_tag(cells[0],must_be_available=True)):
                iprint("Poorly formed or unrecognized tag in file"
                        f" {logfilename} line {line_num}",
                        style=cfg.ERROR_STYLE)
                errors += 1
                continue
            if not (this_time := time_as_str(cells[1])):
                iprint("Time value poorly formed in file"
                        f" {logfilename} line {line_num}",
                        style=cfg.ERROR_STYLE)
                errors += 1
                continue
            # Maybe add to check_ins or check_outs structures.
            if section == "in":
                # Maybe add to check_in structure
                if this_tag in check_ins:
                    iprint(f"Duplicate {this_tag} check-in found at "
                            f"line {line_num}",
                            style=cfg.ERROR_STYLE)
                    errors += 1
                    continue
                if this_tag in check_outs and check_outs[this_tag] < this_time:
                    iprint(f"Tag {this_tag} check out before check-in"
                            f" in file {logfilename}",
                            style=cfg.ERROR_STYLE)
                    errors += 1
                    continue
                check_ins[this_tag] = this_time
            elif section == "out":
                if this_tag in check_outs:
                    iprint(f"Duplicate {this_tag} check-out found at "
                            f"line {line_num}",
                            style=cfg.ERROR_STYLE)
                    errors += 1
                    continue
                if this_tag in check_ins and check_ins[this_tag] > this_time:
                    iprint(f"Tag {this_tag} check out before check-in"
                            f" in file {logfilename}",
                            style=cfg.ERROR_STYLE)
                    errors += 1
                    continue
                check_outs[this_tag] = this_time
            else:
                iprint("PROGRAM ERROR: should not reach this code spot 876246",
                       style=cfg.ERROR_STYLE)
                errors += 1
                continue

    if errors:
        iprint(f"Found {errors} errors in logfile {logfilename}",
               style=cfg.ERROR_STYLE)
    else:
        iprint('Existing log for today successfully loaded',
               style=cfg.SUBTITLE_STYLE)
    return not bool(errors)

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

def find_tag_durations(include_bikes_on_hand=True) -> dict[str,int]:
    """Make dict of tags with their stay duration in minutes.

    If include_bikes_on_hand, this will include checked in
    but not returned out.  If False, only bikes returned out.
    """
    timenow = time_as_int(get_time())
    tag_durations = {}
    for tag,in_str in check_ins.items():
        in_minutes = time_as_int(in_str)
        if tag in check_outs:
            out_minutes = time_as_int(check_outs[tag])
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
        time_in = time_as_int(check_ins[tag])
        if tag in check_outs:
            time_out = time_as_int(check_outs[tag])
        else:
            time_out = time_as_int(get_time())
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
               f"({len(check_ins)-len(check_outs)} bikes still on hand):",
               style=cfg.TITLE_STYLE)
        print()
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
        iprint(f"Max stay:     {time_as_str(max_stay):>5}   "
               f"[tag(s) {longest_stay_tags_str}]")
        iprint(f"Min stay:     {time_as_str(min_stay):>5}   "
               f"[tag(s) {shortest_stay_tags_str}]")
        iprint(f"Mean stay:    {time_as_str(mean):>5}")
        iprint(f"Median stay:  {time_as_str(median):>5}")
        iprint(f"Mode stay:    {time_as_str(mode):>5} "
               f"by {count} bike(s)  [{cfg.MODE_ROUND_TO_NEAREST} minute "
               "blocks]")

    else: # don't try to calculate stats on nothing
        iprint("No bikes returned out, can't calculate statistics. "
               f"({tot_in} bikes currently checked in.)",
               style=cfg.WARNING_STYLE)

def delete_entry(args:list[str]) -> None:
    """Perform tag entry deletion dialogue."""
    (target,which_to_del,confirm) = (args + [None,None,None])[:3]
    if target:
        target = fix_tag(target,must_be_available=False)
    if not target:
        target = False
    del_syntax_message = text_style("Syntax: d <tag> <both or check-out only"
            " (b/o)> <optional pre-confirm (y)>",style=cfg.SUBPROMPT_STYLE)
    if not(target in [False] + cfg.all_tags or which_to_del in [False,'b','o']
           or confirm in [False, 'y']):
        iprint(del_syntax_message) # remind of syntax if invalid input
        return None # interrupt
    if not target: # get target if unspecified
        iprint("Which tag's entry would you like to remove? "
               f"(tag name) {cfg.CURSOR}",
               style=cfg.SUBPROMPT_STYLE,end="")
        target = input().lower()
    checked_in = target in check_ins
    checked_out = target in check_outs
    if not checked_in and not checked_out:
        iprint(f"'{target}' isn't in today's records (delete cancelled)",
               style=cfg.WARNING_STYLE)
    elif checked_out: # both events recorded
        time_in_temp = check_ins[target]
        time_out_temp = check_outs[target]
        if not which_to_del: # ask which to del if not specified
            iprint(f"This tag has both a check-in ({time_in_temp}) and "
                   f"a check-out ({time_out_temp}) recorded.",
                   style=cfg.SUBPROMPT_STYLE)
            iprint("Do you want to delete (b)oth events, "
                   "for just the check-(o)ut?  (b/o) {cfg.CURSOR}",
                   style=cfg.SUBPROMPT_STYLE,end="")
            which_to_del = input().lower()
        if which_to_del == 'b':
            if confirm == 'y': # pre-confirmation
                sure = True
            else:
                iprint("Are you sure you want to delete both events "
                       f"for {target}? (y/N) {cfg.CURSOR}",
                       style=cfg.SUBPROMPT_STYLE, end="")
                sure = input().lower() == 'y'
            if sure:
                check_ins.pop(target)
                check_outs.pop(target)
                iprint(f"Deleted {target} from today's records "
                       f"(was in at {time_in_temp}, out at {time_out_temp})",
                       style=cfg.ANSWER_STYLE)
            else:
                iprint("Delete cancelled",style=cfg.WARNING_STYLE)

        elif which_to_del == 'o': # selected to delete
            if confirm == 'y':
                sure = True
            else:
                iprint("Are you sure you want to delete the "
                       f"check-out record for {target}? (y/N) {cfg.CURSOR}",
                       style=cfg.SUBPROMPT_STYLE, end="" )
                sure = input().lower() == 'y'

            if sure:
                time_temp = check_outs[target]
                check_outs.pop(target)
                iprint(f"Deleted today's {time_temp} check-out for {target}",
                       style=cfg.ANSWER_STYLE)
            else:
                iprint("Delete cancelled",style=cfg.WARNING_STYLE)
        else:
            iprint("Delete cancelled",style=cfg.WARNING_STYLE)
    else: # checked in only
        time_in_temp = check_ins[target]
        if which_to_del in ['b', False]:
            if confirm == 'y':
                sure = True
            else: # check
                iprint("This tag has only a check-in recorded. "
                       f"Are you sure you want to delete it? (y/N) {cfg.CURSOR}",
                       style=cfg.SUBPROMPT_STYLE, end="")
                sure = input().lower() == 'y'
            if sure:
                time_temp = check_ins[target]
                check_ins.pop(target)
                iprint(f"Deleted {time_temp} check-in for {target}",
                       style=cfg.ANSWER_STYLE)
            else:
                iprint("Delete cancelled",style=cfg.WARNING_STYLE)
        else:#  which_to_del == 'o':
            iprint(f"{target} has only a check-in ({time_in_temp}) recorded; "
                   "can't delete a nonexistent check-out",
                   style=cfg.WARNING_STYLE)

def query_tag(args:list[str]) -> None:
    """Query the check in/out times of a specific tag."""
    target = (args + [None])[0]
    if not target: # only do dialog if no target passed
        iprint(f"Which tag would you like to query? (tag name) {cfg.CURSOR}",
               style=cfg.SUBPROMPT_STYLE, end="")
        target = input().lower()
    fixed_target = fix_tag(target,must_be_available=True)
    print()
    if not fixed_target:
        iprint(f"Tag {target} is not available (retired, does not exist, etc)",
               style=cfg.WARNING_STYLE)
        return
    elif fixed_target not in check_ins:
        iprint(f"Tag '{fixed_target}' not used yet today",
               style=cfg.WARNING_STYLE)
        return
    iprint(f"{check_ins[fixed_target]}  {fixed_target} checked  IN",
           style=cfg.ANSWER_STYLE)
    if fixed_target in check_outs:
        iprint(f"{check_outs[fixed_target]}  {fixed_target} returned OUT",
               style=cfg.ANSWER_STYLE)
    else:
        iprint(f"(now)  {target} still at valet", style=cfg.ANSWER_STYLE)

def prompt_for_time(inp = False) -> bool or str:
    """Prompt for a time input if needed.

    Helper for edit_entry(); if no time passed in, get a valid
    24h time input from the user and return an HH:MM string.
    """
    if not inp:
        iprint("What is the correct time for this event? "
               f"(HHMM or 'now') {cfg.CURSOR}",
               style=cfg.SUBPROMPT_STYLE, end="")
        #iprint("Use 24-hour format, or 'now' to use "
        #       f"the current time ({get_time()}) ",end="")
        inp = input()
    if inp.lower() == 'now':
        return get_time()
    hhmm = time_as_str(inp)
    if not hhmm:
        return False
    return hhmm

def edit_entry(args:list[str]):
    """Perform Dialog to correct a tag's check in/out time."""
    (target, in_or_out, new_time) = (args + [None,None,None])[:3]

    edit_syntax_message = text_style("Syntax: e <bike's tag> <in or out (i/o)> "
            "<new time or 'now'>",cfg.WARNING_STYLE)
    if not target:
        iprint(f"Which bike's record do you want to edit? (tag ID) {cfg.CURSOR}",
               style=cfg.SUBPROMPT_STYLE, end="")
        target = input().lower()
    elif not target in cfg.all_tags:
        iprint(edit_syntax_message)
        return False
    if target in cfg.all_tags:
        if target in check_ins:
            if not in_or_out:
                iprint("Do you want to change this bike's "
                       f"check-(i)n or check-(o)ut time? (i/o) {cfg.CURSOR}",
                       style=cfg.SUBPROMPT_STYLE, end="")
                in_or_out = input().lower()
                if not in_or_out in ['i','o']:
                    iprint(f"'{in_or_out}' needs to be 'i' or 'o' "
                           "(edit cancelled)", style=cfg.WARNING_STYLE)
                    return False
            if not in_or_out in ['i','o']:
                iprint(edit_syntax_message)
            else:
                new_time = prompt_for_time(new_time)
                if not new_time:
                    iprint('Invalid time entered (edit cancelled)',
                           style=cfg.WARNING_STYLE)
                elif in_or_out == 'i':
                    if (target in check_outs and
                            (time_as_int(new_time) >
                            time_as_int(check_outs[target]))):
                        iprint("Can't set a check-IN later than a check-OUT;",
                               style=cfg.WARNING_STYLE)
                        iprint(f"{target} was returned OUT at {check_outs[target]}",
                               style=cfg.WARNING_STYLE)
                    else:
                        iprint(f"Check-IN time for {target} "
                               f"set to {new_time}",style=cfg.ANSWER_STYLE)
                        check_ins[target] = new_time
                elif in_or_out == 'o':
                    if (time_as_int(new_time) <
                            time_as_int(check_ins[target])):
                        # don't check a tag out earlier than it checked in
                        iprint("Can't set a check-OUT earlier than check-IN;",
                               style=cfg.WARNING_STYLE)
                        iprint(f"{target} was checked IN at {check_ins[target]}",
                               style=cfg.WARNING_STYLE)
                    else:
                        iprint(f"Check-OUT time for {target} "
                               f"set to {new_time}",
                               style=cfg.ANSWER_STYLE)
                        check_outs[target] = new_time
        else:
            iprint(f"{target} isn't in today's records (edit cancelled)",
                   style=cfg.WARNING_STYLE)
    else:
        iprint(f"'{target}' isn't a valid tag (edit cancelled)",
               style=cfg.WARNING_STYLE)
'''
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
'''
def tags_by_prefix(tags_dict:dict) -> dict:
    """Return a dict of tag prefixes with lists of associated tag numbers."""
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

class Block():
    """Class to help with reporting.

    Each instance is a timeblock of duration cfg.BLOCK_DURATION.
    """

    def __init__(self, start_time:Union[str,int]) -> None:
        """Initialize. Assumes that start_time is valid."""
        if isinstance(start_time,str):
            self.start = time_as_str(start_time)
        else:
            self.start = time_as_str(start_time)
        self.ins_list = []      # Tags of bikes that came in.
        self.outs_list = []     # Tags of bikes returned out.
        self.num_ins = 0        # Number of bikes that came in.
        self.num_outs = 0       # Number of bikes that went out.
        self.here_list = []     # Tags of bikes in valet at end of block.
        self.num_here = 0       # Number of bikes in valet at end of block.

    @staticmethod
    def block_start(time:Union[int,str], as_number:bool=False) -> Union[str,int]:
        """Return the start time of the block that contains time 'time'.

        'time' can be minutes since midnight or HHMM.
        Returns HHMM unless as_number is True, in which case returns int.
        """
        # Get time in minutes
        time = time_as_int(time) if isinstance(time,str) else time
        # which block of time does it fall in?
        block_start_min = (time // cfg.BLOCK_DURATION) * cfg.BLOCK_DURATION
        if as_number:
            return block_start_min
        return time_as_str(block_start_min)

    @staticmethod
    def block_end(time:Union[int,str], as_number:bool=False) -> Union[str,int]:
        """Return the last minute of the timeblock that contains time 'time'.

        'time' can be minutes since midnight or HHMM.
        Returns HHMM unless as_number is True, in which case returns int.
        """
        # Get block start
        start = Block.block_start(time, as_number=True)
        # Calculate block end
        end = start + cfg.BLOCK_DURATION - 1
        # Return as minutes or HHMM
        if as_number:
            return end
        return time_as_str(end)

    @staticmethod
    def timeblock_list( as_of_when:str=None ) -> list[str]:
        """Build a list of timeblocks from beg of day until as_of_when.

        Latest block of the day will be the latest timeblock that
        had any transactions at or before as_of_when.
        """
        as_of_when = as_of_when if as_of_when else get_time()
        # Make list of transactions <= as_of_when
        transx = [x for x in
                (list(check_ins.values()) + list(check_outs.values()))
                if x <= as_of_when]
        # Anything?
        if not transx:
            return []
        # Find earliest and latest block of the day
        min_block_min = Block.block_start(min(transx), as_number=True)
        max_block_min = Block.block_start(max(transx), as_number=True)
        # Create list of timeblocks for the the whole day.
        timeblocks = []
        for t in range(min_block_min, max_block_min+cfg.BLOCK_DURATION,
                cfg.BLOCK_DURATION):
            timeblocks.append(time_as_str(t))
        return timeblocks

    @staticmethod
    def calc_blocks(as_of_when:str=None) -> dict:
        """Create a dictionary of Blocks {start:Block} for whole day."""
        as_of_when = as_of_when if as_of_when else "18:00"
        # Create dict with all the bloctimes as keys (None as values)
        blocktimes = Block.timeblock_list(as_of_when=as_of_when)
        if not blocktimes:
            return {}
        blocks = {}
        for t in Block.timeblock_list(as_of_when=as_of_when):
            blocks[t] = Block(t)
        latest_time = Block.block_end(t,as_number=False)
        for tag, time in check_ins.items():
            if time > latest_time:
                continue
            bstart = Block.block_start(time)
            blocks[bstart].ins_list += [tag]
        for tag, time in check_outs.items():
            if time > latest_time:
                continue
            bstart = Block.block_start(time)
            blocks[bstart].outs_list += [tag]
        here_set = set()
        for btime,blk in blocks.items():
            blk.num_ins = len(blk.ins_list)
            blk.num_outs = len(blk.outs_list)
            here_set = (here_set | set(blk.ins_list)) - set(blk.outs_list)
            blk.here_list = here_set
            blk.num_here = len(here_set)
        return blocks

def lookback(args:list[str]) -> None:
    """Display a look back at recent activity.

    Args are both optional, start_time and end_time.
    If end_time is missing, runs to current time.
    If start_time is missing, starts one hour before end_time.
    """
    def format_one( time:str, tag:str, check_in:bool) -> str:
        """Format one line of output."""
        in_tag = tag if check_in else ""
        out_tag = "" if check_in else tag
        #inout = "bike IN" if check_in else "returned OUT"
        return f"{time}   {in_tag:<5s} {out_tag:<5s}"

    (start_time, end_time) = (args + [None,None])[:2]
    if not end_time:
        end_time = get_time()
    if not start_time:
        start_time = time_as_str(time_as_int(end_time)-60)
    start_time = time_as_str(start_time)
    end_time = time_as_str(end_time)
    if not start_time or not end_time or start_time > end_time:
        iprint("Can not make sense of the given start/end times",
               style=cfg.WARNING_STYLE)
        return
    # Collect any bike-in/bike-out events that are in the time period.
    events = []
    for tag, time in check_ins.items():
        if start_time <= time <= end_time:
            events.append( format_one(time, tag, True))
    for tag, time in check_outs.items():
        if start_time <= time <= end_time:
            events.append( format_one(time, tag, False))
    # Print
    iprint()
    iprint(f"Log of events from {start_time} to {end_time}:",
            style=cfg.TITLE_STYLE)
    print()
    iprint("Time  BikeIn BikeOut",style=cfg.SUBTITLE_STYLE)
    for line in sorted(events):
        iprint(line)

def dataform_report(args:list[str]) -> None:
    """Print days activity in timeblocks.

    This is to match the (paper/google) data tracking sheets.
    Single args are both optional, end_time.
    If end_time is missing, runs to current time.
    If start_time is missing, starts one hour before end_time.
    """
    end_time = (args + [None])[0]
    if not end_time:
        end_time = get_time()
    if not (end_time := time_as_str(end_time)):
        print()
        iprint(f"Unrecognized time {args[0]}",style=cfg.WARNING_STYLE)
        return

    print()
    iprint(f"Tracking form data from start of day until {end_time}",
           style=cfg.TITLE_STYLE)
    all_blocks = Block.calc_blocks(end_time)
    if not all_blocks:
        earliest = min(list(check_ins.values()) + list(check_outs.values()))
        iprint(f"No bikes came in before {end_time} "
               f"(earliest came in at {earliest})",
               style=cfg.HIGHLIGHT_STYLE)
        return
    for which in [cfg.BIKE_IN,cfg.BIKE_OUT]:
        titlebit = "checked IN" if which == cfg.BIKE_IN else "returned OUT"
        title = f"Bikes {titlebit}:"
        print()
        iprint(title, style=cfg.SUBTITLE_STYLE)
        iprint("-" * len(title), style=cfg.SUBTITLE_STYLE)
        for start,block in all_blocks.items():
            inouts = (block.ins_list if which == cfg.BIKE_IN
                    else block.outs_list)
            endtime = time_as_str(time_as_int(start)+cfg.BLOCK_DURATION)
            iprint(f"{start}-{endtime}  {' '.join(sort_tags(inouts))}")

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
    as_of_when = time_as_str(as_of_when)
    if not as_of_when:
        iprint(f"Unrecognized time passed to audit ({args[0]})",
               style=cfg.WARNING_STYLE)
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
        title = f"Audit report as at current time ({rightnow})"
    elif as_of_when > rightnow:
        title = f"Audit report guessing at future state (as at {as_of_when})"
    else:
        title = f"Audit report for past state (as at {as_of_when})"
    iprint(text_style(title,style=cfg.TITLE_STYLE))
    print()

    # Audit summary section.
    iprint("Summary             Regular Oversize Total",
           style=cfg.SUBTITLE_STYLE)
    iprint(f"Bikes checked in:     {normal_in:4d}    {oversize_in:4d}"
           f"    {sum_in:4d}")
    iprint(f"Bikes returned out:   {normal_out:4d}    {oversize_out:4d}"
           f"    {sum_out:4d}")
    iprint(f"Bikes in valet:       {(normal_in-normal_out):4d}"
           f"    {(oversize_in-oversize_out):4d}    {sum_total:4d}")
    if (sum_total != num_bikes_on_hand):
        iprint("** Totals mismatch, expected total "
               f"{num_bikes_on_hand} != {sum_total} **",
               style=cfg.ERROR_STYLE)

    # Tags matrixes
    no_item_str = "  "  # what to show when there's no tag
    print()
    # Bikes returned out -- tags matrix.
    iprint(f"Bikes in valet at {as_of_when}:",style=cfg.SUBTITLE_STYLE)
    for prefix in sorted(prefixes_on_hand.keys()):
        numbers = prefixes_on_hand[prefix]
        line = f"{prefix.upper():3>} "
        for i in range(0,max(numbers)+1):
            s = f"{i:02d}" if i in numbers else no_item_str
            line = f"{line} {s}"
        iprint(line)
    if not prefixes_on_hand:
        iprint("-no bikes-")
    print()

    # Bikes returned out -- tags matrix.
    bikes_out_title = "Bikes returned out ("
    for colour_code in sorted(returns_by_colour.keys()):
        num = returns_by_colour[colour_code]
        bikes_out_title = (f"{bikes_out_title}{num} "
                f"{cfg.colour_letters[colour_code].title()}, ")
    bikes_out_title = f"{bikes_out_title}{sum_out} Total)"
    iprint(bikes_out_title,style=cfg.SUBTITLE_STYLE)
    for prefix in sorted(prefixes_returned_out.keys()):
        numbers = prefixes_returned_out[prefix]
        line = f"{prefix.upper():3>} "
        for i in range(0,max(numbers)+1):
            s = f"{i:02d}" if i in numbers else no_item_str
            line = f"{line} {s}"
        iprint(line)
    if not prefixes_returned_out:
        iprint("-no bikes-")

    return

def tag_check(tag:str) -> None:
    """Check a tag in or out.

    This processes a prompt that's just a tag ID.
    """
    if tag in cfg.retired_tags: # if retired print specific retirement message
        iprint(f"{tag} is retired", style=cfg.WARNING_STYLE)
    else: # must not be retired so handle as normal
        if tag in check_ins:
            if tag in check_outs:# if tag has checked in & out
                query_tag([tag])
                iprint(f"Overwrite {check_outs[tag]} check-out with "
                       f"current time ({get_time()})? "
                       f"(y/N) {cfg.CURSOR}",
                       style=cfg.SUBPROMPT_STYLE, end="")
                sure = input() == 'y'
                if sure:
                    edit_entry([tag, 'o', get_time()])
                else:
                    iprint("Cancelled",style=cfg.WARNING_STYLE)
            else:# checked in only
                now_mins = time_as_int(get_time())
                check_in_mins = time_as_int(check_ins[tag])
                time_diff_mins = now_mins - check_in_mins
                if time_diff_mins < cfg.CHECK_OUT_CONFIRM_TIME: # if < 1/2 hr
                    iprint("This bike checked in at "
                           f"{check_ins[tag]} ({time_diff_mins} mins ago)",
                           style=cfg.SUBPROMPT_STYLE)
                    iprint("Do you want to check it out? "
                           f"(Y/n) {cfg.CURSOR}",
                           style=cfg.SUBPROMPT_STYLE, end="")
                    sure = input().lower() in ['', 'y']
                else: # don't check for long stays
                    sure = True
                if sure:
                    check_outs[tag] = get_time()# check it out
                    iprint(f"{tag} returned OUT",style=cfg.ANSWER_STYLE)
                else:
                    iprint("Cancelled return bike out",style=cfg.WARNING_STYLE)
        else:# if string is in neither dict
            check_ins[tag] = get_time()# check it in
            iprint(f"{tag} checked IN",style=cfg.ANSWER_STYLE)

def parse_command(user_input:str) -> list[str]:
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
    command = fix_tag(input_tokens[0], must_be_available=True)
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
        user_str = input(text_style(f"\nBike tag or command {cfg.CURSOR}",cfg.PROMPT_STYLE))
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
            case cfg.CMD_BLOCK:
                dataform_report(args)
            case cfg.CMD_HELP:
                print(cfg.help_message)
            case cfg.CMD_LOOKBACK:
                lookback(args)
            case cfg.CMD_QUERY:
                query_tag(args)
            case cfg.CMD_STATS:
                show_stats()
            case cfg.CMD_UNKNOWN:
                print()
                iprint("Unrecognized tag or command, enter 'h' for help",
                       style=cfg.WARNING_STYLE)
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
def do_edit(args:list[str]):
    (target, in_or_out, new_time) = (args + [None,None,None])[:3]

    # Action is identified as 'edit'
    tag = get_token(arg[0],optional=False,prompt="Edit what tag?")
    if not (tag := fix_tag(tag, must_be_available=True)):
        ...error...
        return
    in_out = get_token(arg[1],optional=False,prompt="Change (i)n or (o)ut time?")
    if not (in_out useful):
        ...error...
        return
    newtime = get_token(arg[2], optional=False, prompt="Change to what time (blank for now):",default="")
    if not (newtime := time_as_str(newtime)):
        ...error...
        return
    confirm = get_token(arg[3], optional=False,prompt="Change (Y/n):",default="y')
   (etc)
'''

def error_exit() -> None:
    """If an error has occurred, give a message and shut down.

    Any specific info about the error should already have been printed."""
    print()
    iprint("Closing in 30 seconds",style=cfg.ERROR_STYLE)
    time.sleep(30)
    exit()

# STARTUP
if not cfg.SETUP_PROBLEM: # no issue flagged while reading config

    # These are the master dictionaries for tag status.
    #   key = canonical tag id (e.g. "wf4")
    #   value = ISO8601 event time (e.g. "08:43" as str)
    check_ins = {}
    check_outs = {}

    print()
    print(text_style(f"TagTracker {cfg.VERSION} by Julias Hocking",
            style=cfg.ANSWER_STYLE))
    print()
    DATE = get_date()
    LOG_FILEPATH = f"logs/{cfg.LOG_BASENAME}{DATE}.log"

    if read_tags(): # only run main() if tags read successfully
        main()
    else: # if read_tags() problem
        error_exit()
else:
    error_exit()
#==========================================

# possible data structures for (new) reports

"""Possible data structures for reports.

--------------------------
Queue-like or stack-like.

Want to know all visits with their start time and end time
    dict visits_by_tag{}
        key = tag
        value = dict
            key = "time_in"|"time_out"
            value = event's time - could be hhmm or num
    ** check how compatible this is with calc_stays() structure
    ** could also be a Tag object
"""
X="""
-----------------------
Summary statistics (day-end)





"""
X="""
-----------------------
Time of day with most bikes on hand

fullness{}
dict of event times with num bikes on hand
    key = time
    value = num_bikes

block_fullness{}    # for histogram
    key = block_start
    value = num bikes
"""

X="""
------------------------
Busiest times of day (most events in a time block)

    block_activity{} dict as per data entry report,
    To find maximums, walk the dict looking at things like

        how_busy = {}
        for block, activities in block_activity.items():
            ins = len(activities[cfg.BIKE_IN])
            outs = len(activities[cfg.BIKE_OUT])
            ttl = ins + outs
            if ttl not in how_busy:
                how_busy[ttl] = []
            how_busy[ttl] += [block]

        iprint("Busiest timeblock(s) of the day:")
        most = max(how_busy.keys())
        for block in sorted(how_busy[most]):
            iprint(f"{block}: {most} ins & outs ({block_activity[block][BIKE_IN]} in, {block_activity[block][BIKE_IN]} out)")
"""

X="""
---------------------------------
Data Entry report (events listed by time block)

    block_ins[block_start] = [list of tags]
    block_outs[block_start] = [list of tags]

    block_activity{}
        key = block start HHMM
        value = dict{}
            cfg.BIKE_IN: [list of tags]
            cfg.BIKE_OUT: [list of tags]

"""

class Visit():
    def __init__(self, tag:str) -> None:
        self.tag = tag      # canonical
        self.time_in = ""   # HH:MM
        self.time_out = ""  # HH:MM
        self.duration = 0   # minutes
        self.type = None    # cfg.REGULAR, cfg.OVERSIZE
        self.still_here = None  # True or False

    @staticmethod
    def count_visits( as_of_when:Union[int,str]=None ) -> dict:
        """Create a dict of visits keyed by tag as of as_of_when.

        If as_of_when is not given, then this will choose the latest
        check-out time of the day as its time.

        As a special case, this will also accept the word "now" to
        mean the current time.
        """
        if isinstance(as_of_when,str) and as_of_when.lower() == "now":
            as_of_when = get_time()
        elif as_of_when is None:
            # Set as_of_when to be the time of the latest checkout of the day.
            if check_ins:
                as_of_when = min(list(check_ins.values()))
            else:
                as_of_when = get_time()
        as_of_when = time_as_str(as_of_when)
        visits = {}
        for tag,time_in in check_ins.items():
            if time_in > as_of_when:
                continue
            this_visit = Visit(tag)
            this_visit.time_in = time_in
            if tag in check_outs and check_outs[tag] <= as_of_when:
                this_visit.time_out = check_outs[tag]
                this_visit.still_here = False
            else:
                this_visit.time_out = as_of_when
                this_visit.still_here = False
            this_visit.duration = (time_as_int(this_visit.time_out) -
                    time_as_int(this_visit.time_in))
            if tag in cfg.normal_tags:
                this_visit.type = cfg.REGULAR
            else:
                this_visit.type = cfg.OVERSIZE
            visits[tag] = this_visit
        return visits

# FIXME: here's where I am in editing. - tevpg

