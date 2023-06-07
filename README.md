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
See [installation instructions](https://github.com/ironwoodcall/TagTracker/wiki/TagTracker-installation) in wiki

# USAGE - basic commands / short versions
Usage is described when you run the `help` command in TagTracker
