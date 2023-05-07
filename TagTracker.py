# TagTracker by Julias Hocking
#

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

def valid_time(inp:str) -> bool:
    """Check whether inp is a valid HH:MM string."""
    time_lengths = [4,5]
    if len(inp) in time_lengths:
        HH = inp[:2]
        MM = inp[-2:]
        if HH.isdigit() and MM.isdigit():#format should be right
            if int(HH) < 24 and int(MM) < 60:#physically possible earth time
                return True
    return False

def canonical_tag( maybe_tag:str ) -> str|None:
    """Return 'maybe_tag' as canonical tag representation (or None).

    Canonical tag representation is a single colour letter, a tag letter
    and a sequence number, without lead zeroes.  All lowercase.
    """
    # FIXME - for later
    if r := re.match(r"^ *([a-zA-z][a-zA-Z])0*([1-9][0-9]*) *$", maybe_tag ):
        return f"{r.group(1).lower()}{r.group(2)}"
    return None

def valid_tag( tag:str ) -> bool:
    """Return whether 'tag' simplifies to a valid [known] tag."""
    #FIXME: this is not used yet
    return bool(canonical_tag( tag ) in cfg.all_tags)

def iprint(text:str, x:int=1) -> None:
    """Print the text, indented."""
    print(f"{cfg.INDENT * x}{text}")

def read_tags() -> bool:
    """Fetch tag data from file.

    Read data from a pre-existing log file, if one exists
    check for .txt file for today's date in folder called 'logs'
    e.g. "logs/2023-04-20.txt"
    if exists, read for ins and outs
    if none exists, make one.
    """
    #FIXME: Refactor
    pathlib.Path("logs").mkdir(exist_ok = True) # make logs folder if missing
    global check_ins, check_outs
    check_ins = {} # check in dictionary tag:time
    check_outs = {} # check out dictionary tag:time
    try: # read saved stuff into dicts
        filedir = LOG_FILEPATH
        with open(filedir, 'r') as f:
            line = f.readline() # read check ins header
            line = f.readline() # read first tag entry if exists
            line_counter = 2 # track line number

            # FIXME: below check for the line being a tag should 
            # probably be based on cfg.valid_tags or canonical_tag()
            # rather than the first character being 'B'
            while line[0] != 'B': # while the first chr of each line isn't a header
                cells = line.rstrip().split(',')
                # if either a tag or time is invalid...
                if not cells[0] in cfg.all_tags or not valid_time(cells[1]):
                    print(f"Problem while reading {filedir} -- check-ins, line {line_counter}.")
                    return False
                elif cells[0] in check_ins:
                    print(f"Duplicate {cells[0]} check-in found at line {line_counter}")
                    return False
                check_ins[cells[0]] = cells[1]
                line = f.readline() # final will load the check outs header
                line_counter += 1 # increment line counter
            line = f.readline()
            line_counter += 1
            while line != '':
                cells = line.rstrip().split(',')
                if not cells[0] in cfg.all_tags or not valid_time(cells[1]):
                    print(f"Problem while reading {filedir} -- check-outs, line {line_counter}.")
                    return False
                elif cells[0] in check_outs:
                    print(f"Duplicate {cells[0]} check-out found at line {line_counter}")
                    return False
                check_outs[cells[0]] = cells[1]
                line = f.readline() # final will load trailing empty line
                line_counter += 1 # increment line counter
        print('Previous log for today successfully loaded')
    except FileNotFoundError: # if no file, don't read it lol
        print('No previous log for today found. Starting fresh...')
    return True

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


def minutes_to_time_str_list(times:list[int]) -> list[str]:
    """Convert list of times in minutes to list of HH:MM strings."""
    # FIXME: I think better to use minutes_to_time_str() than this
    # FIXME: this fn should now be unused & deprecated
    text_times = []
    for time_in_minutes in times:
        text_times.append(minutes_to_time_str(time_in_minutes))
    return text_times

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
    # FIXME: should use check_ins and use now() for any not returned out.
    for tag in check_outs:
        time_in = time_str_to_minutes(check_ins[tag])
        time_out = time_str_to_minutes(check_outs[tag])
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
            if stay < cfg.T_UNDER:  # Changed from <= to < so matches description.
                short_stays += 1
            elif stay <= cfg.T_OVER:
                medium_stays += 1
            else:
                long_stays += 1
        hrs_under = f"{(cfg.T_UNDER / 60):3.1f}" # times in hours for print clarity
        hrs_over = f"{(cfg.T_OVER / 60):3.1f}"

        iprint(f"\nSummary statistics as of {get_time()} "
               f"with {len(check_ins)-len(check_outs)} bikes still on hand:\n")
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
               f"by {count} bike(s)  [{cfg.MODE_ROUND_TO_NEAREST} minute blocks]")

    else: # don't try to calculate stats on nothing
        iprint("No bikes returned out, can't calculate statistics. "
               f"({tot_in} bikes currently checked in.)")

def delete_entry(target = False, which_to_del=False, confirm = False) -> None:
    """Perform tag entry deletion dialogue."""
    del_syntax_message = ("Syntax: d <tag> <both or check-out only"
            " (b/o)> <optional pre-confirm (y)>")
    if not(target in [False] + cfg.all_tags or which_to_del in [False, 'b', 'o']
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

def query_tag(target = False, do_printing = True) -> str:
    """Query the check in/out times of a specific tag."""
    #FIXME: what is do_printing meant to do?
    if not target: # only do dialog if no target passed
        iprint("Which tag would you like to query?")
        target = input(f"(tag name) {cfg.CURSOR}").lower()
    if target in cfg.retired_tags:
        iprint(f"{target} has been retired.")
        return 'retired' # tag is retired
    else:
        try:
            iprint(f"{target} checked IN at {check_ins[target]}")
        except KeyError:
            iprint(f"'{target}' isn't in today's records.")
            return 'none' # tag is neither in nor out
        try:
            iprint(f"{target} checked OUT at {check_outs[target]}")
            return 'both' # tag is in and out
        except KeyError:
            return 'in' # tag is in but not out

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
    elif valid_time(inp):
        HH = inp[:2]
        MM = inp[-2:]
        HHMM = f"{HH}:{MM}"
    else:
        return False # cancel time
    return HHMM

def edit_entry(target = False, in_or_out = False, new_time = False):
    """Perform Dialog to correct a tag's check in/out time."""
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
                    if target in check_outs and \
                        (time_str_to_minutes(new_time) >
                        time_str_to_minutes(check_outs[target])):
                        iprint("Can't set a check-IN later than a check-OUT;")
                        iprint(f"{target} checked OUT at {check_outs[target]}")
                    else:
                        iprint(f"Check-IN time for {target} "
                               f"changed to {new_time}.")
                        check_ins[target] = new_time
                elif in_or_out == 'o':
                    if (time_str_to_minutes(new_time) <
                            time_str_to_minutes(check_ins[target])):
                        # don't check a tag out earlier than it checked in
                        iprint("Can't set a check-OUT earlier than a check-IN;")
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
    # FIXME: test for and handle empty list passed-in
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
    for abbrev in cfg.colour_letters: # for each valid colour, loop through all tags
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

def show_audit() -> None:
    """Perform audit function.

    Prints a list of all tags that should be in the corral
    and bikes that should be on hand.  Format to be easy to use
    during mid-day reconciliations.
    """
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
            if tag in check_outs:# if string is in checked_in AND in checked_out
                query_tag(tag)
                iprint(f"Overwrite {check_outs[tag]} check-out with "
                       f"current time ({get_time()})? (y/N)")
                sure = input(f"(y/N) {cfg.CURSOR}") == 'y'
                if sure:
                    edit_entry(target = tag, in_or_out = 'o',
                            new_time = get_time())
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
                    iprint(f"**{tag} checked OUT**")
                else:
                    iprint("Cancelled check-out")
        else:# if string is in neither dict
            check_ins[tag] = get_time()# check it in
            iprint(f"{tag} checked IN")


def process_prompt(prompt:str) -> None:
    """Process one user-input command.

    This is the logic for main loop
    """
    cells = prompt.strip().split() # break into each phrase (already .lower()'d)
    try:
        kwd = cells[0] # take first phrase as fn to call
        if cells[0][0] in ['?', '/'] and len(cells[0])>1: # take non-letter query prompts without space
            query_tag(cells[0][1:], False)
        elif kwd in cfg.statistics_kws:
            show_stats()
        elif kwd in cfg.help_kws:
            print(cfg.help_message)
        elif kwd in cfg.audit_kws:
            show_audit()
        elif kwd in cfg.edit_kws:
            args = len(cells) - 1 # number of arguments passed
            target, in_or_out, new_time = None, None, None# initialize all
            if args > 0:
                target = cells[1]
            if args > 1:
                in_or_out = cells[2]
            if args > 2:
                new_time = cells[3]
            edit_entry(target = target, in_or_out = in_or_out,
                    new_time = new_time)

        elif kwd in cfg.del_kws:
            args = len(cells) - 1 # number of arguments passed
            target, which_to_del, pre_confirm = False, False, False
            if args > 0:
                target = cells[1]
            if args > 1:
                which_to_del = cells[2]
            if args > 2:
                pre_confirm = cells[3]
            delete_entry(target = target, which_to_del = which_to_del,
                    confirm = pre_confirm)

        elif kwd in cfg.query_kws:
            try:
                query_tag(target = cells[1]) # query the tag that follows cmd
            except IndexError:
                query_tag() # if no tag passed run the dialog
        elif kwd in cfg.quit_kws:
            exit() # quit program
        elif kwd in cfg.all_tags:
            tag_check(kwd)
        else: # not anything recognized so...
            iprint(f"'{prompt}' isn't a recognized tag or command "
                   "(type 'help' for a list of these).")
    except IndexError: # if no prompt
        return None

def main() -> None:
    """Run main program loop."""
    rotate_log()
    write_tags() # save before input regardless
    #show_audit() # show all bikes currently in
    prompt = input(f"\n\nEnter a tag or command {cfg.CURSOR}").lower() # take input
    process_prompt(prompt)
    main() # loop

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
