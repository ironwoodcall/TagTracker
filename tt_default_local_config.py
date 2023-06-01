"""Local config for TagTracker.

This file contains local settings/overrides, that will not
be overwritten by git pulls.

"""
#pylint:disable=unused-import
from tt_colours import (HAVE_COLOURS,STYLE,Style,Fore,Back,
    PROMPT_STYLE,SUBPROMPT_STYLE,ANSWER_STYLE,TITLE_STYLE,SUBTITLE_STYLE,
    RESET_STYLE,NORMAL_STYLE,HIGHLIGHT_STYLE,WARNING_STYLE,ERROR_STYLE)
#from tt_config import (LOG_BASENAME,LOG_FOLDER,
#    PUBLISH_FOLDER,PUBLISH_FREQUENCY, TAGS_UPPERCASE, USE_COLOUR)
import tt_config as cfg
#pylint:enable=unused-import


# Datafiles/Logfiles
cfg.LOG_BASENAME = "cityhall_"  # Files will be {BASENAME}YY-MM-DD.LOG.
# cfg.LOG_FOLDER = "logs" # Folder to keep logfiles in

# System occasionally puts a copy of log in a publish folder
cfg.PUBLISH_FOLDER = r"/mnt/chromeos/GoogleDrive/MyDrive/tracker_logs"
# cfg.PUBLISH_FREQUENCY = 15 # minutes. "0" means do not publish

# Tags display in uppercase or lowercase?
cfg.TAGS_UPPERCASE = False

# Use colour in the program?
cfg.USE_COLOUR = True

# Styles related to colour
# These override values in tt_colours module
#STYLE[PROMPT_STYLE] = f"{Style.BRIGHT}{Fore.GREEN}{Back.BLACK}"
#STYLE[SUBPROMPT_STYLE] = f"{Style.BRIGHT}{Fore.GREEN}{Back.BLACK}"
STYLE[ANSWER_STYLE] = f"{Style.BRIGHT}{Fore.BLACK}{Back.BLUE}"
#STYLE[TITLE_STYLE] = f"{Style.BRIGHT}{Fore.WHITE}{Back.BLUE}"
#STYLE[SUBTITLE_STYLE] = f"{Style.BRIGHT}{Fore.CYAN}{Back.BLACK}"
#STYLE[RESET_STYLE] = f"{Style.RESET_ALL}"
#STYLE[NORMAL_STYLE] = f"{Style.RESET_ALL}"
#STYLE[HIGHLIGHT_STYLE] = f"{Style.BRIGHT}{Fore.CYAN}{Back.BLACK}"
#STYLE[WARNING_STYLE] = f"{Style.BRIGHT}{Fore.MAGENTA}{Back.BLACK}"
#STYLE[ERROR_STYLE] = f"{Style.BRIGHT}{Fore.WHITE}{Back.RED}"
