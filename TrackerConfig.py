"""Config for TagTracker by Julias Hocking."""

import os
import re

# Basename for the Logfiles. They will be {BASENAME}YY-MM-DD.LOG.
LOG_BASENAME = "cityhall_"

# Regular expression for parsing tags -- here & in main program.
PARSE_TAG_RE = re.compile( r"^ *([a-z]+)([a-z])0*([0-9]+) *$")

# time cutoffs for stays under x time and over y time
T_UNDER = 1.5*60 # minutes
T_OVER = 5*60

# size of 'buckets' for calculating the mode stay time
MODE_ROUND_TO_NEAREST = 30 # mins

# how long of a stay to confirm check-outs for?
CHECK_OUT_CONFIRM_TIME = 30 # mins

# Style preferences
INDENT = '  '
CURSOR = '>>> '

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

help_message = f"""{INDENT}List these commands     :   help  /  h
{INDENT}Check in or out         :   <tag name> (eg “wa3”)
{INDENT}Audit of logged tags    :   audit / a
{INDENT}Lookup times for a tag  :   query / q / ?
{INDENT}Edit a time for a tag   :   edit  / e
{INDENT}Delete a check in/out   :   del   / d
{INDENT}End of day statistics   :   stat  / s
{INDENT}Shutdown*               :   stop  / exit / quit / x
{INDENT}*using this isn't important; data is autosaved"""

# assemble list of normal tags
def build_tags_config(filename:str) -> list[str]:
    """Build a tag list from a file.

    Constructs a list of each allowable tag in a given category
    (normal, oversize, retired, etc) by reading its category.cfg file.
    """
    tags = []
    if not os.path.exists(filename): # make new tags config file if needed
        with open(filename, 'w') as f:
            header = ("# Enter lines of whitespace-separated tags, "
                    "eg 'wa0 wa1 wa2 wa3'\n")
            f.writelines(header)
    with open(filename, 'r') as f: # open and read
        lines = f.readlines()
    line_counter = 0 # init line counter to 0
    for line in lines:
        line_counter += 1 # increment for current line
        if not line[0] == '#': # for each non-comment line
            # (blank lines do nothing here anyway)
            line_words = line.rstrip().split() # split into each tag name
            for word in line_words: # check line for nonconforming tag names
                if not PARSE_TAG_RE.match(word):
                    print(f'Invalid tag "{word}" found '
                          f'in {filename} on line {line_counter}')
                    return None # stop loading
            tags += line_words # add all tags in that line to this tag type
    return tags

normal_tags   = build_tags_config('normal_tags.cfg')

oversize_tags = build_tags_config('oversize_tags.cfg')

retired_tags  = build_tags_config('retired_tags.cfg')

# combine allowable tags into single list for brevity in main script
try:
    all_tags = normal_tags + oversize_tags
    SETUP_PROBLEM = False # don't flag because it's fine
except TypeError: # if returned None for any of these tags lists
    # flag problem for main script
    SETUP_PROBLEM = "Unsuccessful load of config files;"

if not os.path.exists("tag_colour_abbreviations.cfg"):
    with open('tag_colour_abbreviations.cfg', 'w') as f:
        header = ("Enter each first letter(s) of a tag name corresponding to "
                  "a tag colour separated by whitespace on their own line, "
                  "eg 'b black' etc")
        f.writelines(header)
with open('tag_colour_abbreviations.cfg', 'r') as f:
    lines = f.readlines()[1:] # ignore header text
colour_letters = {}
for line in lines:
    if len(line.rstrip().split()) == 2:
        abbrev = line.rstrip().split()[0]
        colour = line.rstrip().split()[1]
        colour_letters[abbrev] = colour # add to dictionary

# pull startup header and version from changelog
with open('changelog.txt', 'r') as f:
    f.readline()
    f.readline() # skip empty lines
    VERSION = f.readline()[:-2] # cut off ':\n'
