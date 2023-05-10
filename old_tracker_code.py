# Code I removed from tagtracker.py but kept for I don't know why
# seeing we have a version control system, but old habits die hard.
'''
def valid_time(inp:str) -> bool:
    """Check whether inp is a valid HH:MM string."""
    # FIXME: remove all calls to valid_time(), use fix_hhmm() instead.
    return bool(fix_hhmm(inp))
'''

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

'''

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

'''

'''
# FIXME: these are no longer needed.
# keywords for day end statistics
statistics_kws = ['s','stat','stats','sum','summary']
# keywords for audit of logged tags
audit_kws = ['audit','a','aud']
# keywords to quit the program
quit_kws = ['quit','exit','stop','x','bye']
# keywords to delete a tag entry
del_kws = ['del','delete','d']
# keywords to query a tag
query_kws = ['query','q','?','/']
# editing
edit_kws = ['edit','e','ed']
# help message
help_kws = ['help','h']
'''
