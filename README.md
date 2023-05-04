# TagTracker by Julias Hocking

This is a simple tag tracking/data gathering system for bike valet operations I wrote for use at Victoria, BC's downtown bike valet program.
It generates persistent .log files titled by date that can be collated and analyzed later.
I intend to write some kind of script for this later.

Some important assumptions the program makes:
* Opening hours don't cross midnight - the program automatically decides whether to start a new .log based on the computer's date
* Each tag has a unique identifier that starts with at least 1 letter that relates consistently to the tag's colour
* Tag names don't match any of the command keywords listed below
* Each tag separates into two pieces, one for the bike and one for the customer, like a coat check
* Tags are reused day-to-day but not within a single day

The "intended" workflow using the tracker is:
1. bike checks in - bike receives half tag, owner receives half tag
2. log check-in with tracker
3. bike checks out - half tags are reunited
4. log check-out with tracker
5. tag is placed in some kind of return basket and not reused that day


# SETUP
1. Put all TagTracker files into the folder you want to use them in.
2. Run TagTracker once to generate 'logs' folder and .cfg's, and close it.
3. Populate .cfg files as directed by their headers:
 - the first letter of each tag name should represent what colour the tag is, ie 'wa4' is a white tag.
 This makes auditing the records easier because the program can group tags by colour.
 Make sure to list each abbreviation you're using in the "Tag Colour Abbreviations.cfg"
 - for me 'normal' tags means bikes that can easily be lifted and hung by their seat on a rack, ie the majority of bikes
 - 'oversize' bikes means anything too big or heavy to be reasonably racked, ie e-bikes, bikes with trailers, etc
 - 'retired' tags is anything that WAS in use, but has been taken out of service (missing, damaged, etc).
 These will trigger a specific message to be printed letting the user know the tag is retired rather than just invalid.
 4. Park some bikes!
 (5. If you want, you can change some style options in TrackerConfig.py)
 

# USAGE - basic commands / short versions

```
List these commands     :   help  / h
Check in or out         :   <tag name> (eg “wa3”)
Audit of logged tags    :   audit / a
Lookup times for a tag  :   query / q / ?
Edit a time for a tag   :   edit  / e
Delete a check in/out   :   del   / d
End of day statistics   :   stat  / s
Shutdown*               :   stop  / exit / quit / x
*using this isn't important; working info is autosaved to the day's .log file

Single-line command processing:
Normally the commands edit, del, and query will all begin some sort of dialog.
To save time, you can optionally put some arguments for the command into one string separated by spaces.
As long as these are in the right order you can specify in advance as much or as little as you want to:
ie instead of entering "edit", then, as prompted: <tag name>, then "i" for check-in, then "1340" for the new time,
...you'd just enter "e wb4 i 1340" all as one
or to delete tag bi8's check-out: "d bi8 o y"

```
