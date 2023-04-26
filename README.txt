TagTracker by Julias Hocking
SETUP
1. Run TagTracker once to create 'logs' directory and .cfg's to put lists of valid normal, oversize and retired tags in.
2. Populate these files as directed by their headers
(for now, only retired tags have their own .cfg, and valid tags and other settings are in TrackerConfig.py)


USAGE - basic commands
List these commands	:    help
Check in or out   	:    <tag name> (eg “wa3”)
Audit of logged tags    :    audit / a
Lookup times for a tag	:    query / q / ?
Edit a time for a tag	:    edit  / e
Delete a check in/out	:    del   / d
End of day statistics	:    stat  / s
Shutdown*                :    stop  / x
*using this isn't really important; the tracker automatically writes the working info to the day's log as it goes anyways

Single-line command processing:
TBD