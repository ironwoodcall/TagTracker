# Config for TagTracker by Julias Hocking
from pathlib import Path
# time cutoffs for stays under x time and over y time
T_UNDER = 1.5*60 # minutes
T_OVER = 5*60

# mode stay
MODE_ROUND_TO_NEAREST = 30 # mins

# how long a stay to confirm check outs for?
CHECK_OUT_CONFIRM_TIME = 30 # mins

# prompt style
INDENT = '  '
CURSOR = '>>> '

# single-letter abbreviations for normal bike tag colours
white_tags = ['wa0', 'wa1', 'wa2', 'wa3', 'wa4', 'wa5', 'wa6', 'wa7', 'wa8', 'wa9', 'wa10', 'wa11', 'wa12', 'wa13', 'wa14', 'wa15',
              'wb0', 'wb1', 'wb2', 'wb3', 'wb4', 'wb5', 'wb6', 'wb7', 'wb8', 'wb9', 'wb10', 'wb11', 'wb12', 'wb13', 'wb14', 'wb15',
              'wc0', 'wc1', 'wc2', 'wc3', 'wc4', 'wc5', 'wc6', 'wc7', 'wc8', 'wc9', 'wc10', 'wc11', 'wc12', 'wc13', 'wc14', 'wc15',
              'wd0', 'wd1', 'wd2', 'wd3', 'wd4', 'wd5', 'wd6', 'wd7', 'wd8', 'wd9', 'wd10', 'wd11', 'wd12', 'wd13', 'wd14', 'wd15',
              'we0', 'we1', 'we2', 'we3', 'we4', 'we5', 'we6', 'we7', 'we8', 'we9', 'we10', 'we11', 'we12', 'we13', 'we14', 'we15']

purple_tags = ['pa0', 'pa1', 'pa2', 'pa3', 'pa4', 'pa5', 'pa6', 'pa7', 'pa8', 'pa9', 'pa10', 'pa11', 'pa12', 'pa13', 'pa14', 'pa15',
               'pb0', 'pb1', 'pb2', 'pb3', 'pb4', 'pb5', 'pb6', 'pb7', 'pb8', 'pb9', 'pb10', 'pb11', 'pb12', 'pb13', 'pb14', 'pb15',
               'pc0', 'pc1', 'pc2', 'pc3', 'pc4', 'pc5', 'pc6', 'pc7', 'pc8', 'pc9', 'pc10', 'pc11', 'pc12', 'pc13', 'pc14', 'pc15',
               'pd0', 'pd1', 'pd2', 'pd3', 'pd4', 'pd5', 'pd6', 'pd7', 'pd8', 'pd9', 'pd10', 'pd11', 'pd12', 'pd13', 'pd14', 'pd15',
               'pe0', 'pe1', 'pe2', 'pe3', 'pe4', 'pe5', 'pe6', 'pe7', 'pe8', 'pe9', 'pe10', 'pe11', 'pe12', 'pe13', 'pe14', 'pe15']

black_tags = ['be0', 'be1', 'be2', 'be3', 'be4', 'be5', 'be6', 'be7', 'be8', 'be9',
              'bf0', 'bf1', 'bf2', 'bf3', 'bf4', 'bf5', 'bf6', 'bf7', 'bf8', 'bf9',
              'bg0', 'bg1', 'bg2', 'bg3', 'bg4', 'bg5', 'bg6', 'bg7', 'bg8', 'bg9',
              'bh0', 'bh1', 'bh2', 'bh3', 'bh4', 'bh5', 'bh6', 'bh7', 'bh8', 'bh9',
              'bi0', 'bi1', 'bi2', 'bi3', 'bi4', 'bi5', 'bi6', 'bi7', 'bi8', 'bi9',
              'bj0', 'bj1', 'bj2', 'bj3', 'bj4', 'bj5', 'bj6', 'bj7', 'bj8', 'bj9']

# assemble list of retired tags
if not Path("Retired Tags.cfg").is_file(): # make new retired tags file if none yet exists
    with open('Retired Tags.cfg', 'w') as f:
        header = "Enter each retired tag on its own line with no punctuation, eg 'wa4'\n"
        f.writelines(header)
with open('Retired Tags.cfg', 'r') as f:
    lines = f.readlines()[1:] # ignore header text
retired_tags = [line.rstrip() for line in lines]

# combine colours for normal size bikes
norm_tags = white_tags + purple_tags

# colours for oversize bikes
over_tags = black_tags

# combine allowable tags into single list for brevity in main script
all_tags = norm_tags + over_tags
valid_tags = []
for tag in all_tags:
    if not tag in retired_tags:
        valid_tags.append(tag)

colour_letters = { # doesn't have to be 1 letter only
    'b':'black',
    'w':'white',
    'p':'purple'
}

# keywords to trigger showing stats for day end
statistics_kws = [
    's',
    'stat',
    'stats',
    'statistics'
]

# keywords for audit
audit_kws = [
    'audit',
    'a'
]

# keywords to quit the program
quit_kws = [
    'quit',
    'exit',
    'stop',
    'x'
]

# keywords to delete a tag entry
del_kws = [
    'del',
    'delete',
    'd'
]

# keywords to query a tag
query_kws = [
    'query',
    'lookup',
    'q',
    '?'
]

# editing
edit_kws = [
    'edit',
    'change',
    'e'
]

# help message
help_kws = [
    'help',
    'commands'
]

help_message = """TAG TRACKER FUNCTIONS
List these commands	:    help
Check in or out   	:    <tag name> (eg “wa3”)
Audit of logged tags    :    audit / a
Lookup times for a tag	:    query / q / ?
Edit a time for a tag	:    edit  / e
Delete a check in/out	:    del   / d
End of day statistics	:    stat  / s
Shutdown                :    stop  / x
"""
