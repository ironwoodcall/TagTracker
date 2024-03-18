#!/usr/bin/env python3
"""One-time script to add service hours to historic datafiles.

Delete as soon as historic conversions are complete & loaded into DB
"""
import sys
sys.path.append("../")
import datetime
import os
import re
from typing import Tuple
from tt_conf import valet_hours


HEADER_DATE = "Valet date:"
HEADER_OPENS = "Valet opens:"
HEADER_CLOSES = "Valet closes:"

datfolder = r"/fs/sysbits/tagtracker/data_conversion/remotedata.fix_hours"

# Add valet date/hours header lines to a datafile.

whoami = os.path.basename(__file__)

thedate = "2023-03-16"  # day beforethe first day of interest
enddate = "2023-07-01"
while thedate <= enddate:
    datedate = datetime.datetime.strptime(
        thedate, "%Y-%m-%d"
    ) + datetime.timedelta(1)
    thedate = datedate.strftime("%Y-%m-%d")

    (vopen, vclose) = valet_hours(thedate)

    fname = f"cityhall_{thedate}"
    path = os.path.join(datfolder, f"cityhall_{thedate}.dat")
    print()
    if not os.path.exists(path):
        print(f"File {path} not found")
        continue
    with open(path, "r") as f:
        print(f"Reading {path}")
        lines = f.readlines()
    ##needs_dates = True
    for num,line in enumerate(lines):
        if re.match(
            rf"({HEADER_DATE}|{HEADER_OPENS}|{HEADER_CLOSES})",
            line,
        ):
            lines[num] = f"## commented out by {whoami}: {line}"
            ##print(f"Skipping {path}")
            ##needs_dates = False

    ##if not needs_dates:
    ##    continue
    with open(path, "w") as f:
        print(f"Rewriting {path}")
        f.write(f"# added by {whoami}\n")
        f.write(f"{HEADER_DATE} {thedate}\n")
        f.write(f"{HEADER_OPENS} {vopen}\n")
        f.write(f"{HEADER_CLOSES} {vclose}\n")
        f.write(f"# end of addition by {whoami}\n\n")
        f.writelines(lines)
