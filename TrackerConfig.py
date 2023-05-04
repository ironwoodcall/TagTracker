# Config for TagTracker by Julias Hocking
from pathlib import Path

# Basename for the Logfiles. They will be {BASENAME}YY-MM-DD.LOG.
LOG_BASENAME = ""


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
statistics_kws = ['s','stat']

# keywords for audit of logged tags
audit_kws = ['audit','a']

# keywords to quit the program
quit_kws = ['quit','exit','stop','x']

# keywords to delete a tag entry
del_kws = ['del','delete','d']

# keywords to query a tag
query_kws = ['query','q','?', '/']

# editing
edit_kws = ['edit','e']

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
if not Path("Normal Tags.cfg").is_file(): # make new normal tags file if none yet exists
    with open('Normal Tags.cfg', 'w') as f:
        header = "Enter each NORMAL tag on its own line, separating any comments with whitespace eg 'wa4 comment'\n"
        f.writelines(header)
with open('Normal Tags.cfg', 'r') as f:
    lines = f.readlines()[1:] # ignore header text
norm_tags = [line.rstrip().split()[0] for line in lines if not line in ['', '\n']]

# assemble list of oversize tags
if not Path("Oversize Tags.cfg").is_file(): # make new oversize tags file if none yet exists
    with open('Oversize Tags.cfg', 'w') as f:
        header = "Enter each OVERSIZE tag on its own line, separating any comments with whitespace eg 'be4 comment'\n"
        f.writelines(header)
with open('Oversize Tags.cfg', 'r') as f:
    lines = f.readlines()[1:] # ignore header text
over_tags = [line.rstrip().split()[0] for line in lines if not line in ['', '\n']]

# assemble list of retired tags
if not Path("Retired Tags.cfg").is_file(): # make new retired tags file if none yet exists
    with open('Retired Tags.cfg', 'w') as f:
        header = "Enter each RETIRED tag on its own line with no punctuation, separating any comments with whitespace eg 'wa4 lost/damaged/etc'\n"
        f.writelines(header)
with open('Retired Tags.cfg', 'r') as f:
    lines = f.readlines()[1:] # ignore header text
retired_tags = [line.rstrip().split()[0] for line in lines if not line in ['', '\n']]

# combine allowable tags into single list for brevity in main script
all_tags = norm_tags + over_tags
valid_tags = [tag for tag in all_tags if not tag in retired_tags]


if not Path("Tag Colour Abbreviations.cfg").is_file(): # make new retired tags file if none yet exists
    with open('Tag Colour Abbreviations.cfg', 'w') as f:
        header = "Enter each first letter(s) of a tag name corresponding to a tag colour separated by whitespace on its own line, eg 'b black' etc"
        f.writelines(header)
with open('Tag Colour Abbreviations.cfg', 'r') as f:
    lines = f.readlines()[1:] # ignore header text
colour_letters = {}
for line in lines:
    if len(line.rstrip().split()) == 2:
        abbrev = line.rstrip().split()[0]
        colour = line.rstrip().split()[1]
        colour_letters[abbrev] = colour # add to dictionary


# pull startup header and version from changelog
with open('changelog.txt', 'r') as f:
    f.readline()#[:-1] # cut off '\n'
    f.readline() # skip empty line
    VERSION = f.readline()[:-2] # cut off ':\n'
