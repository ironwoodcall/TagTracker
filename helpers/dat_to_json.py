"""Convcert DAT (v1 TagTracker) to JSON (v2 TagTracker) file.

"""

import os
import sys
import re
import argparse

sys.path.append("../")

from tt_trackerday import TrackerDay,OldTrackerDay,old_to_new,TrackerDayError
import tt_datafile as df
import client_base_config as cfg


def process_file(file_path,site_handle:str="",site_name:str="",target_dir:str="") -> bool:

    print(f"Converting {file_path}.")
    errs = []
    old_day = df.read_datafile(file_path,errs)
    if errs:
        print(f"  ERRORS READING {file_path}\n    ")
        print("\n  ".join(errs))
        return False

    new_day = old_to_new(old_day)
    new_day.fill_default_bits(site_handle=cfg.SITE_HANDLE,site_name=cfg.SITE_NAME)
    # Allow override
    new_day.site_name = site_name if site_name else new_day.site_name
    new_day.site_handle = site_handle if site_handle else new_day.site_handle

    if target_dir:
        new_file_name = re.sub(r'\.dat$', '.json', os.path.basename(file_path))
        new_file_path = os.path.join(target_dir, new_file_name)
    else:
        new_file_path = re.sub(r'\.dat$', '.json', file_path)
    new_day.filepath = new_file_path

    errs = new_day.lint_check(strict_datetimes=True,allow_quick_checkout=True)
    if errs:
        print(f"  ERRORS AFTER CONVERSION {file_path}\n    ")
        print("\n  ".join(errs))
        return False

    new_day.save_to_file(new_file_path)

def main(file_list,site_handle:str="",site_name:str="",target_dir:str=""):

    for file_path in file_list:
        process_file(file_path,site_handle=site_handle,site_name=site_name,target_dir=target_dir)

if __name__ == '__main__':
    # Set up argument parser
        # Set up argument parser
    parser = argparse.ArgumentParser(description='Process some data files.')
    parser.add_argument('files', metavar='FILE', type=str, nargs='+', help='Data files to process')
    parser.add_argument('--site_handle', type=str, help='Override for site handle')
    parser.add_argument('--site_name', type=str, help='Override for site name')
    parser.add_argument('--target_dir', type=str, help='Directory to save the converted files')


    # Parse the arguments
    args = parser.parse_args()

    # Get the list of data files from the command line arguments
    # file_list = args.files
    # site_handle = args.site_handle
    # site_name = args.site_name
    # target_dir = args.target_dir


    # Process each file in the list
    main( file_list=args.files,site_handle=args.site_handle,site_name=args.site_name,target_dir=args.target_dir)
