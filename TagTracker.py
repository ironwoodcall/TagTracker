# TagTracker by Julias Hocking
import time
from TrackerConfig import *


def get_date() -> str:
    """get today's date and return as string: YYYY-MM-DD"""
    localtime = time.localtime()
    year = str(localtime.tm_year)
    month = str(localtime.tm_mon)
    day = str(localtime.tm_mday)
    month = ('0'+month)[-2:] # ensure leading zeroes
    day = ('0'+day)[-2:]
    date = f"{year}-{month}-{day}"
    return date

def now() -> str:
    '''returns current time in 24H format: HH:MM'''
    now = time.asctime(time.localtime())[11:16]
    return now

def validate_time(inp:str) -> bool:
    """Check whether an HH:MM format time string is valid,
    return True or False."""
    time_lengths = [4,5]
    if len(inp) in time_lengths:
        HH = inp[:2]
        MM = inp[-2:]
        if HH.isdigit() and MM.isdigit():#format should be right
            if int(HH) < 24 and int(MM) < 60:#physically possible earth time
                return True
    return False

def iprint(text:str, x:int=1) -> None:
    """print, plus configurable indent"""
    print(f"{INDENT * x}{text}")

def read_tags() -> bool:
    '''read data from a preexisting log file, if one exists
    check for .txt file for today's date in folder called 'logs' 
    ie "logs/2023-04-20.txt"
    if exists, read for ins and outs
    if none exists, make one'''
    Path("logs").mkdir(exist_ok = True) # make logs folder if none exists
    global check_ins, check_outs
    check_ins = {} # check in dictionary tag:time
    check_outs = {} # check out dictionary tag:time
    try: # read saved stuff into dicts
        filedir = f'logs/{DATE}.log'
        with open(filedir, 'r') as f:
            line = f.readline() # read check ins header
            line = f.readline() # read first tag entry if exists
            line_counter = 2 # track line number
            while line[0] != 'B': # while the first character of each line isn't a header
                cells = line.rstrip().split(',')
                # if either a tag or time is invalid...
                if not cells[0] in all_tags or not validate_time(cells[1]):
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
                if not cells[0] in all_tags or not validate_time(cells[1]):
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

def write_tags() -> None:
    '''write current data to today's log file'''
    lines = []
    lines.append('Bikes checked in / tags out:')
    for tag in check_ins: # for each bike checked in
        lines.append(f'{tag},{check_ins[tag]}') # add a line "tag,time"
    
    lines.append('Bikes checked out / tags in:')
    for tag in check_outs: # for each  checked 
        lines.append(f'{tag},{check_outs[tag]}') # add a line "tag,time"
    
    with open(f'logs/{DATE}.log', 'w') as f: # write stored lines to file
        for line in lines:
            f.write(line)
            f.write('\n')

def time_string_to_mins(HHMM) -> int:
    '''convert time string HH:MM to number of mins.'''
    cells = HHMM.split(':')
    hrs = int(cells[0])
    mins = int(cells[1])
    mins += hrs * 60
    return mins

def mins_to_time_string(stats:list[int]) -> list[str]:
    '''KIND OF reverse of above but for a batch of stats all at once.'''
    stats_HHMM = []
    for stat in stats:
        whole_hours = stat // 60
        mins_left = stat - 60*whole_hours
        MM = f'0{mins_left}'[-2:] # ensure leading zero
        HHMM = f"{whole_hours}:{MM}" # no leading zeroes here
        stats_HHMM.append(HHMM)
    return tuple(stats_HHMM)
    
def calc_stays() -> list[int]:
    '''calculate how long each tag has stayed in the bikevalet.
    (Leftovers aren't counted as stays for these purposes)'''
    global shortest_stay_tags_str
    global longest_stay_tags_str
    global min_stay
    global max_stay
    stays = []
    tags = []
    for tag in check_outs:
        time_in = time_string_to_mins(check_ins[tag])
        time_out = time_string_to_mins(check_outs[tag])
        stay = time_out - time_in
        stays.append(stay)
        tags.append(tag) # add to list of tags in same order for next step
    min_stay = min(stays)
    max_stay = max(stays)
    shortest_stay_tags = [tags[i] for i in range(len(stays)) if stays[i] == min_stay]
    longest_stay_tags = [tags[i] for i in range(len(stays)) if stays[i] == max_stay]
    shortest_stay_tags_str = ', '.join(shortest_stay_tags)
    longest_stay_tags_str = ', '.join(longest_stay_tags)
    return stays

def median_stay(stays:list) -> int:
    """compute the median of a list of stay lengths"""
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

def mode_stay(stays) -> (int,int):
    '''round stays and compute mode stay length'''
    round_stays = []
    for stay in stays:
        remainder = stay % MODE_ROUND_TO_NEAREST
        mult = stay // MODE_ROUND_TO_NEAREST
        if remainder > 4:
            mult += 1
        rounded = mult * MODE_ROUND_TO_NEAREST
        round_stays.append(rounded)
    mode = max(set(stays), key=stays.count)
    count = stays.count(mode)
    return mode, count

def show_stats():
    '''show # of bikes currently in, and statistics for day end form'''
    norm = 0 # counting bikes by type
    over = 0
    for tag in check_ins:
        if tag in norm_tags:
            norm += 1
        elif tag in over_tags:
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
        # convert each stat to HH:MM format
        max_stay_HHMM, min_stay_HHMM, mean_HHMM, median_HHMM, mode_HHMM = mins_to_time_string([max_stay, min_stay, mean, median, mode])
        
        stays_under = 0
        stays_between = 0
        stays_over = 0
        for stay in all_stays: # count stays over/under x time
            if stay <= T_UNDER:
                stays_under += 1
            elif stay <= T_OVER:
                stays_between += 1
            else:
                stays_over += 1
        hrs_under = T_UNDER / 60 # times in hours for print clarity
        hrs_over = T_OVER / 60
        
        print(f'''\
{INDENT}Total bikes: {tot_in}
{INDENT}AM bikes: {AM_ins}
{INDENT}PM bikes: {PM_ins}
{INDENT}Regular: {norm}
{INDENT}Oversize: {over}

{INDENT}Stays under {hrs_under} h: {stays_under}
{INDENT}Stays {hrs_under} - {hrs_over} h: {stays_between}
{INDENT}Stays over {hrs_over} h: {stays_over}

{INDENT}Max. stay = {max_stay_HHMM} --- {longest_stay_tags_str}
{INDENT}Min. stay = {min_stay_HHMM} --- {shortest_stay_tags_str}

{INDENT}Mean stay = {mean_HHMM}
{INDENT}Median stay = {median_HHMM}
{INDENT}Mode stay = {mode_HHMM} by {count} bikes - {MODE_ROUND_TO_NEAREST} min blocks''')
    else: # don't try to calculate stats on nothing
        iprint(f"Can't calulate statistics because no bikes have checked out yet. {tot_in} are checked in.")

def delete_entry(target = False, which_to_del = False, confirm = False) -> None:
    '''tag entry deletion dialogue'''
    del_syntax_message = "Syntax: d <tag> <both or check-out only (b/o)> <optional pre-confirm (y)>"
    if not(target in [False] + all_tags or which_to_del in [False, 'b', 'o'] or confirm in [False, 'y']):
        iprint(del_syntax_message) # remind of syntax if invalid input
        return None # interrupt
    if not target: # get target if unspecified
        iprint("Which tag's entry would you like to remove?")
        target = input(f"(tag name) {CURSOR}").lower()
    checked_in = target in check_ins
    checked_out = target in check_outs
    if not checked_in and not checked_out:
        iprint(f"'{target}' isn't in today's records (Cancelled deletion).")
    elif checked_out: # both events recorded
        time_in_temp = check_ins[target]
        time_out_temp = check_outs[target]
        if not which_to_del: # ask which to del if not specified
            iprint(f"This tag has both a check-in ({time_in_temp}) and a check-out ({time_out_temp}) recorded.")
            iprint(f"Do you want to delete (b)oth events, or just the check-(o)ut?")
            which_to_del = input(f"(b/o) {CURSOR}").lower()
        if which_to_del == 'b':
            if confirm == 'y': # pre-confirmation
                sure = True
            else:
                iprint(f"Are you sure you want to delete both events for {target}? (y/N)")
                sure = input(f"(y/N) {CURSOR}").lower() == 'y'
            if sure:
                check_ins.pop(target)
                check_outs.pop(target)
                iprint(f"Deleted all records today for {target} (in at {time_in_temp}, out at {time_out_temp}).")
            else:
                iprint(f"Cancelled deletion.")
        
        elif which_to_del == 'o': # selected to delete
            if confirm == 'y':
                sure = True
            else:
                iprint(f"Are you sure you want to delete the check-out record for {target}? (y/N)")
                sure = input(f"(y/N) {CURSOR}").lower() == 'y'
            
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
                iprint(f"This tag has only a check-in recorded. Are you sure you want to delete it? (y/N)")
                sure = input(f"(y/N) {CURSOR}").lower() == 'y'
            if sure:
                time_temp = check_ins[target]
                check_ins.pop(target)
                iprint(f"Deleted today's {time_temp} check-in for {target}.")
            else:
                iprint(f"Cancelled deletion.")
        else:#  which_to_del == 'o':
            iprint(f"{target} has only a check-in ({time_in_temp}) recorded; can't delete a nonexistent check-out.")

def query(target = False, do_printing = True) -> str:
    '''Query the check in/out times of a specific tag.'''
    if not target: # only do dialog if no target passed
        iprint(f"Which tag would you like to query?")
        target = input(f"(tag name) {CURSOR}").lower()
    if target in retired_tags:
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

def get_time_input(inp = False) -> bool or str:
    '''Helper for edit_entry(); if no time passed in, get a valid
    24h time input from the user and return an HH:MM string.'''
    if not inp:
        iprint(f"What is the correct time for this event?")
        iprint(f"Use 24-hour format, or 'now' to use the current time ({now()})")
        inp = input(f"(HH:MM) {CURSOR}").lower()
    if inp == 'now':
        return now()
    elif validate_time(inp):
        HH = inp[:2]
        MM = inp[-2:]
        HHMM = f"{HH}:{MM}"
    else:
        return False # cancel time
    return HHMM

def edit_entry(target = False, in_or_out = False, new_time = False):
    '''Dialog to correct a tag's check in/out time.'''
    edit_syntax_message = "Syntax: e <bike's tag> <in or out (i/o)> <new time or 'now'>"
    if not target:
        iprint(f"Which bike's record do you want to edit?")
        target = input(f"(tag ID) {CURSOR}").lower()
    elif not target in all_tags:
        iprint(edit_syntax_message)
        return False
    if target in all_tags:
        if target in check_ins:
            if not in_or_out:
                iprint(f"Do you want to change this bike's check-(i)n or check-(o)ut time?")
                in_or_out = input(f"(i/o) {CURSOR}").lower()
                if not in_or_out in ['i','o']:
                    iprint(f"'{in_or_out}' needs to be 'i' or 'o' (cancelled edit).")
                    return False
            if not in_or_out in ['i','o']:
                iprint(edit_syntax_message)
            else:
                new_time = get_time_input(new_time)
                if new_time == False:
                    iprint('Invalid time entered (cancelled edit).')
                elif in_or_out == 'i':
                    if time_string_to_mins(new_time) > time_string_to_mins(check_outs[target]):
                        iprint("Can't set a check-IN later than a check-OUT;")
                        iprint(f"{target} checked OUT at {check_outs[target]}")
                    else:
                        iprint(f"Check-IN time for {target} changed to {new_time}.")
                        check_ins[target] = new_time
                elif in_or_out == 'o':
                    if time_string_to_mins(new_time) < time_string_to_mins(check_ins[target]):
                        # don't check a tag out earlier than it checked in
                        iprint(f"Can't set a check-OUT earlier than a check-IN;")
                        iprint(f"{target} checked IN at {check_ins[target]}")
                    else:
                        iprint(f"Check-OUT time for {target} changed to {new_time}.")
                        check_outs[target] = new_time   
        else:
            iprint(f"{target} isn't in today's records (cancelled edit).")
    else:
        iprint(f"'{target}' isn't a valid tag (cancelled edit).")

def count_colours(inv:list[str]) -> str:
    '''Count the number of tags corresponding to each config'd colour abbreviation
    in a given list, and return results as a str. Probably avoid calling
    this on empty lists'''
    just_colour_abbreviations = []
    for tag in inv: # shorten tags to just their colours
        shortened = ''
        for char in tag: # add every letter character to start
            if not char.isdigit():
                shortened += char
        # cut off last, non-colour letter and add to list of abbrevs
        if shortened in colour_letters:
            just_colour_abbreviations.append(shortened)
        else:
            for x in range(10):
                cutoff_by_x = shortened[:-x]
                if cutoff_by_x in colour_letters:
                    just_colour_abbreviations.append(cutoff_by_x)
        
    colour_count = {} # build the count dictionary
    for abbrev in colour_letters: # for each valid colour, loop through all tags
        if abbrev in just_colour_abbreviations:
            this_colour_count = 0
            for tag in just_colour_abbreviations:
                if tag == abbrev:
                    this_colour_count += 1
            colour_name = colour_letters[abbrev]
            colour_count[colour_name] = this_colour_count
    
    colour_count_str = '' # convert count dict to string
    for colour in colour_count:
        colour_count_str += f",  {colour} x {colour_count[colour]}"
    colour_count_str = colour_count_str[3:] # cut off leading comma
        
    return colour_count_str

def audit() -> None:
    '''Prints a list of all tags that should be in the corral.'''
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
        iprint(f"Tags that should be in the return basket:")
        iprint(f"by colour:     {count_colours(basket)}", 2)
        iprint(f"individually:  {basket_str}", 2)
    else:
        iprint('No tags should be in the basket.')

def tag_check(tag:str) -> None:
    """Process a prompt that's just a tag ID"""
    if not tag in retired_tags:
        checked_in = tag in check_ins
        checked_out = tag in check_outs
        if checked_in:
            if checked_out:# if string is in checked_in AND in checked_out
                query(tag)
                iprint(f"Overwrite {check_outs[tag]} check-out with current time ({now()})? (y/N)")
                sure = input(f"(y/N) {CURSOR}") == 'y'
                if sure:
                    edit_entry(target = tag, in_or_out = 'o', new_time = now())
                else:
                    iprint("Cancelled")
            else:
                now_mins = time_string_to_mins(now())
                check_in_mins = time_string_to_mins(check_ins[tag])
                time_diff_mins = now_mins - check_in_mins
                if time_diff_mins < CHECK_OUT_CONFIRM_TIME: # if stay has been less than a half hour...
                    iprint(f"This bike checked in at {check_ins[tag]} ({time_diff_mins} mins ago).")
                    iprint("Do you want to check it out? (Y/n)")
                    sure = input(f"(Y/n) {CURSOR}").lower() in ['', 'y'] # just Enter -> yes for this very normal action
                else: # don't check for long stays
                    sure = True
                if sure:
                    check_outs[tag] = now()# check it out
                    iprint(f"**{tag} checked OUT**")
                else:
                    iprint("Cancelled check-out")
        else:# if string is in neither dict
            check_ins[tag] = now()# check it in
            iprint(f"{tag} checked IN")
    else: # must be retired
        iprint(f"{tag} is retired.")

def process_prompt(prompt:str) -> None:
    '''logic for main loop'''
    cells = prompt.strip().split() # break into each phrase (already .lower()'d)
    kwd = cells[0] # take first phrase as fn to call
    try:
        if cells[0][0] in ['?', '/'] and len(cells[0])>1: # take non-letter query prompts without space
            query(cells[0][1:], False)
        elif kwd in statistics_kws:
            show_stats()
        elif kwd in help_kws:
            print(help_message)
        elif kwd in audit_kws:
            audit()
        elif kwd in edit_kws:
            args = len(cells) - 1 # number of arguments passed
            target, in_or_out, new_time = None, None, None# initialize all
            if args > 0:
                target = cells[1]
            if args > 1:
                in_or_out = cells[2]
            if args > 2:
                new_time = cells[3]        
            edit_entry(target = target, in_or_out = in_or_out, new_time = new_time)
            
        elif kwd in del_kws:
            args = len(cells) - 1 # number of arguments passed
            target, which_to_del, pre_confirm = False, False, False # initialize all to False
            if args > 0:
                target = cells[1]
            if args > 1:
                which_to_del = cells[2]
            if args > 2:
                pre_confirm = cells[3]        
            delete_entry(target = target, which_to_del = which_to_del, confirm = pre_confirm)
            
        elif kwd in query_kws:
            try:
                query(target = cells[1]) # query the tag passed after the command
            except IndexError:
                query() # if no tag passed run the dialog
        elif kwd in quit_kws:
            exit() # quit program
        elif kwd in all_tags:
            tag_check(kwd)
        else: # not anything recognized so...
            iprint(f"'{prompt}' isn't a recognized tag or command (type 'help' for a list of these).")
    except IndexError: # if no prompt
        return None
    
def main() -> None:
    '''main program loop'''
    write_tags() # save before input regardless
    #audit() # show all bikes currently in
    prompt = input(f"\n\nEnter a tag or command {CURSOR}").lower() # take input
    process_prompt(prompt)
    main() # loop

# STARTUP
print(f"TagTracker {VERSION} by Julias Hocking")
DATE = get_date()
if read_tags(): # only run main() if tags read successfully
    main()
else: # if read_tags() problem
    print(f"\n{INDENT}Closing automatically in 30 seconds...")
    time.sleep(30)