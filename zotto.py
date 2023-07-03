#!/usr/bin/python3
#
# Import zotto to make life more interesting.

import re
import random

#FIXME  - add things t ===o to do words in string, e..
#           sub the -> teh; trout -> chicken; hockey -> hookey;
#           Capialized soetinmes MIscapitalized

def _occasion() -> bool:
    """Indicate whether to make a change."""
    percentage_to_change = 10
    return bool(random.randint(1, 100) <= percentage_to_change)


def _zonkme(matchobj) -> str:
    original = matchobj.group(0)
    if not _occasion():
        return original
    if isinstance(original, str) and original.isdigit():
        new = f"{int(original)+1}"
    else:
        new = original
    if len(new) < len(original):
        new = f"{'0' * (len(original) - len(new))}{new}"
    elif len(new) > len(original):
        new = original
    return new


def _zprint(*arg, **kwarg):
    zarg = list(arg)
    for n, el in enumerate(zarg):
        ##if not random.randint(0,3): # Only change it sometimes
        if isinstance(el, str):
            zarg[n] = re.sub(r"(\d+)", _zonkme, el)
        elif isinstance(el, int):
            if _occasion():
                zarg[n] = el + 1
    _print(*zarg, **kwarg)


random.seed()
_print = print
__builtins__["print"] = _zprint
