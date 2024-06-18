"""Convert DAT (v1 TagTracker) to JSON (v2 TagTracker) file.

One-time script to convert the older files into v2 json format.
2024-06-04

"""

import os
import sys
import re
import argparse

sys.path.append("../")

from common.tt_trackerday import TrackerDay,OldTrackerDay,old_to_new,TrackerDayError
import tt_datafile as df
import client_base_config as cfg

# These are extracted from the database, harkening back to a time when registrations
# were tracked separately and then merged into the database separately from datafiles.
# Yuck.
# Registrations were tracked in datafiles starting around Feb 2024.
HISTORIC_REGISTRATION_VALUES={
   "2023-06-04": 2,
   "2023-03-17": 5,
   "2023-03-18": 8,
   "2023-03-19": 2,
   "2023-03-20": 6,
   "2023-03-21": 4,
   "2023-03-22": 5,
   "2023-03-23": 7,
   "2023-03-24": 2,
   "2023-03-25": 1,
   "2023-03-26": 3,
   "2023-03-27": 4,
   "2023-03-28": 15,
   "2023-03-29": 9,
   "2023-03-30": 7,
   "2023-03-31": 2,
   "2023-04-02": 3,
   "2023-04-03": 1,
   "2023-04-04": 1,
   "2023-04-05": 1,
   "2023-04-08": 6,
   "2023-04-10": 2,
   "2023-04-12": 1,
   "2023-04-13": 1,
   "2023-04-14": 3,
   "2023-04-15": 6,
   "2023-04-17": 4,
   "2023-04-19": 5,
   "2023-04-20": 2,
   "2023-04-24": 3,
   "2023-04-25": 2,
   "2023-04-26": 1,
   "2023-04-27": 4,
   "2023-04-28": 5,
   "2023-04-30": 1,
   "2023-05-01": 2,
   "2023-05-02": 4,
   "2023-05-03": 1,
   "2023-05-05": 1,
   "2023-05-08": 2,
   "2023-05-09": 2,
   "2023-05-10": 1,
   "2023-05-14": 3,
   "2023-05-15": 1,
   "2023-05-16": 1,
   "2023-05-18": 2,
   "2023-05-19": 1,
   "2023-05-20": 1,
   "2023-05-22": 3,
   "2023-05-23": 6,
   "2023-05-24": 1,
   "2023-05-25": 1,
   "2023-05-26": 2,
   "2023-05-29": 2,
   "2023-05-30": 2,
   "2023-05-31": 1,
   "2023-06-02": 5,
   "2023-06-03": 1,
   "2023-06-05": 1,
   "2023-06-06": 1,
   "2023-06-08": 1,
   "2023-06-11": 3,
   "2023-06-12": 3,
   "2023-06-13": 3,
   "2023-06-15": 3,
   "2023-06-19": 1,
   "2023-06-21": 1,
   "2023-06-26": 3,
   "2023-06-27": 1,
   "2023-06-30": 1,
   "2023-07-04": 1,
   "2023-07-06": 1,
   "2023-07-10": 1,
   "2023-07-11": 1,
   "2023-07-13": 1,
   "2023-07-18": 3,
   "2023-07-19": 1,
   "2023-07-20": 1,
   "2023-07-21": 1,
   "2023-07-25": 1,
   "2023-07-28": 2,
   "2023-07-31": 1,
   "2023-08-01": 3,
   "2023-08-10": 3,
   "2023-08-13": 1,
   "2023-08-23": 1,
   "2023-08-24": 2,
   "2023-08-27": 1,
   "2023-09-08": 2,
   "2023-09-17": 1,
   "2023-09-20": 12,
   "2023-09-21": 2,
   "2023-09-24": 2,
   "2023-09-25": 1,
   "2023-09-27": 1,
   "2023-10-03": 1,
   "2023-10-07": 1,
   "2023-10-11": 1,
   "2023-10-21": 1,
   "2023-11-08": 2,
   "2023-11-15": 1,
   "2023-11-16": 2,
   "2023-11-24": 1,
   "2023-11-27": 1,
   "2023-12-06": 1,
   "2023-12-20": 1,
   "2023-12-26": 2,
   "2024-01-03": 1,
   "2024-01-24": 3,
   "2024-01-25": 1,
   "2024-01-26": 3,
   "2024-01-29": 4,
   "2024-01-30": 2,
   "2024-01-31": 7,
   "2024-02-01": 17,
   "2024-02-02": 2,
   "2024-02-04": 3,
   "2024-02-05": 4,
   "2024-02-06": 1,
   "2024-02-07": 7,
   "2024-02-08": 18,
   "2024-02-09": 1,
   "2024-02-12": 4,
   "2023-07-08": 1,
   "2023-08-06": 3,
   "2023-09-29": 1,
   "2023-10-04": 1,
   "2023-12-29": 1,
   "2024-02-16": 1,
   "2024-02-19": 1,
   "2024-02-20": 1,
   "2024-02-21": 6,
   "2024-02-22": 1,
   "2024-02-23": 1,
   "2024-02-24": 1,
   "2024-02-26": 3,
   "2024-02-28": 13,
   "2024-02-29": 6,
   "2024-03-01": 1,
   "2024-03-04": 1,
   "2024-03-05": 1,
   "2024-03-06": 4,
   "2024-03-07": 9,
   "2024-03-08": 2,
   "2024-03-09": 3,
   "2024-03-12": 1,
   "2024-03-13": 4,
   "2024-03-14": 1,
   "2024-03-18": 1,
   "2024-03-20": 10,
   "2024-03-24": 1,
   "2024-03-27": 5,
   "2024-03-28": 1,
   "2024-04-01": 3,
   "2024-04-03": 3,
   "2024-04-05": 1,
   "2024-04-10": 7,
   "2024-04-12": 4,
   "2024-04-15": 3,
   "2024-04-17": 1,
   "2024-04-18": 3,
   "2024-04-22": 5,
   "2024-04-23": 2,
   "2024-04-24": 1,
   "2024-04-26": 2,
   "2024-04-29": 1,
   "2024-05-01": 3,
   "2024-05-02": 2,
   "2024-05-03": 3,
   "2024-05-04": 1,
   "2024-05-07": 2,
   "2024-05-08": 5,
   "2024-05-09": 2,
   "2024-05-10": 1,
   "2024-05-12": 1,
   "2024-05-13": 4,
   "2024-05-15": 3,
   "2024-05-17": 1,
   "2024-05-19": 1,
   "2024-05-22": 1,
   "2024-05-27": 4,
   "2024-05-30": 1,
   "2024-06-01": 1,
   "2024-06-03": 2,
}


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

    # Maybe insert a historic registration value not in the datafile
    if new_day.date in HISTORIC_REGISTRATION_VALUES and not new_day.registrations.num_registrations:
        print("   adding historic registration value saved from db")
        new_day.registrations.num_registrations = HISTORIC_REGISTRATION_VALUES[new_day.date]

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

    # Set the new file to the same timestamp as the old file
    source_stat = os.stat(file_path)
    os.utime(new_file_path, (source_stat.st_atime, source_stat.st_mtime))


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
