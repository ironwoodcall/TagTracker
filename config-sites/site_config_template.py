"""TagTracker site config.

Written by TagTracker set-up (the site config manager), starting from
config-sites/site_config_template.py (or the copy named by
SITE_CONFIG_TEMPLATE in client_local_config.py).

Set-up changes only the items listed below; anything else in this file is
left as it is, so other settings can be added by hand. Settings here
override client_local_config.py, which overrides client_base_config.py.

Items set-up manages:
    SITE_NAME        Site name, no year: the config is reused each year.
    SITE_HANDLE      Permanent site ID, which must match this file's name
                     (site_<handle>_config.py). Lowercase letters, digits,
                     hyphens, underscores and periods; starts and ends with a
                     letter or digit; at most 32 characters.
    EVENT_MODE       True for an event (short-term) site: shorter command
                     list, no network features. False for a permanent site.
    DATA_OWNER_NAME  The data owner's name. Read only by set-up.
    DATA_OWNER       The notice TagTracker shows at start-up; set-up builds
                     it from DATA_OWNER_NAME.
    REGULAR_TAGS     Every regular tag, e.g. "pa0 pa1 ... pj15".
    OVERSIZE_TAGS    Every oversize tag.

To give every new site config more settings, copy this file somewhere
outside the program folder, add them, and point SITE_CONFIG_TEMPLATE at the
copy in client_local_config.py.
"""

EVENT_MODE = True  # True: event site (shorter command list, no network features)
