#!/bin/env python3
"""
Test for internet.
"""
import sys
sys.path.append("../")

import tt_internet_monitor


def main():
    if tt_internet_monitor.InternetMonitor._check_internet():
        print("Yes Internet")
    else:
        print("No Internet")

if __name__ == "__main__":
    main()



