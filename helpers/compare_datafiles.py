"""Compare same-named datafiles in different directories.

Look at same-named datafiles in different directories and report the count of
leftovers for each, in csv format.

This is useful for identifying problems in a dataflow.

tevpg 2024-02-06

"""

import os
import sys
import re

def parse_file(filename):
    # Initialize counters for each section
    checked_in_count = 0
    checked_out_count = 0
    valet_date = None

    # Regular expression pattern for matching the specified format
    pattern = r'^ *[a-z][a-z][0-9][0-9]*, *[0-2][0-9]:[0-5][0-9] *$'

    # Open the file and read line by line
    with open(filename, 'r') as file:
        # Flag to indicate which section we are in
        in_section = False
        out_section = False

        for line in file:
            line = line.strip()
            # Parse the valet date
            if line.startswith("Valet date:"):
                if valet_date is None:
                    valet_date = line.split(":")[1].strip()
                elif valet_date != line.split(":")[1].strip():
                    return None, None, None  # Different dates found
                continue

            # Check if we're entering or leaving a section
            if "Bikes checked in / tags out:" in line:
                in_section = True
                out_section = False
                continue
            elif "Bikes checked out / tags in:" in line:
                out_section = True
                in_section = False
                continue

            # Check if the line matches the specified pattern
            if re.match(pattern, line):
                # Count lines based on the section
                if in_section:
                    checked_in_count += 1
                elif out_section:
                    checked_out_count += 1
            else:
                in_section = False
                out_section = False

    return valet_date, checked_in_count - checked_out_count

def compare_files(filenames, all_directories):

    date = None
    filebase = None
    # Create a dictionary to store differences for each directory
    differences = {directory: None for directory in all_directories}

    # Parse files and store the differences
    for filename in filenames:
        this_date, difference = parse_file(filename)

        if this_date is None:
            print(f"Error: Unable to parse file: {filename}")
            return

        if date is None:
            date = this_date
        if filebase is None:
            filebase = os.path.basename(filename)

        if date != this_date:
            print(f"Error: date mismatch, file {filename}: '{this_date}'")
            return

        # Determine which directory the file belongs to
        directory = os.path.dirname(filename)
        # Store the difference for this directory
        differences[directory] = difference

    # Print the date followed by the differences for each directory
    print(f"{date}, {filebase},", end="")
    for directory in all_directories:
        difference = differences[directory]
        if difference is None:
            print("XXX,", end="")
        else:
            print(f"{difference},", end="")
    print()  # Move to the next line

# Check if the directory names are provided as command-line arguments
if len(sys.argv) < 2:
    print("Please provide at least one directory name as a command-line argument.")
    sys.exit(1)

# Extract the directory names from the command-line arguments
directories = sys.argv[1:]

# List files in the directories
files = []
for directory in directories:
    files.extend([os.path.join(directory, filename) for filename in os.listdir(directory) if filename.endswith(".dat")])

# Group files by their names
file_groups = {}
for file in files:
    name = os.path.basename(file)
    if name not in file_groups:
        file_groups[name] = [file]
    else:
        file_groups[name].append(file)

# Print header
print("Date,File,", end="")
for directory in directories:
    print(f" {directory},", end="")
print()  # Move to the next line

# Compare same-named files across directories
for files in sorted(file_groups.values()):
    compare_files(files, directories)

'''
import os
import sys
import re

def parse_file(filename):
    # Initialize counters for each section
    checked_in_count = 0
    checked_out_count = 0
    valet_date = None

    # Regular expression pattern for matching the specified format
    pattern = r'^ *[a-z][a-z][0-9][0-9]*, *[0-2][0-9]:[0-5][0-9] *$'

    # Open the file and read line by line
    with open(filename, 'r') as file:
        # Flag to indicate which section we are in
        in_section = False
        out_section = False

        for line in file:
            line = line.strip()
            # Parse the valet date
            if line.startswith("Valet date:"):
                if valet_date is None:
                    valet_date = line.split(":")[1].strip()
                elif valet_date != line.split(":")[1].strip():
                    return None, None, None  # Different dates found
                continue

            # Check if we're entering or leaving a section
            if "Bikes checked in / tags out:" in line:
                in_section = True
                out_section = False
                continue
            elif "Bikes checked out / tags in:" in line:
                out_section = True
                in_section = False
                continue

            # Check if the line matches the specified pattern
            if re.match(pattern, line):
                # Count lines based on the section
                if in_section:
                    checked_in_count += 1
                elif out_section:
                    checked_out_count += 1
            else:
                in_section = False
                out_section = False

    return valet_date, checked_in_count - checked_out_count

def compare_files(filenames):

    date = None
    # Parse files and print the differences
    for filename in filenames:
        this_date, difference = parse_file(filename)

        if this_date is None:
            print(f"Error: Unable to parse file: {filename}")
            return
        if date is None:
            date = this_date
            print(f"{date}, ", end="")

        if date != this_date:
            print(f"Error: date mismatch, file {filename}: '{this_date}'")
            return

        print(f"{difference},", end="")

    print()  # Move to the next line

# Check if the directory names are provided as command-line arguments
if len(sys.argv) < 2:
    print("Please provide at least one directory name as a command-line argument.")
    sys.exit(1)

# Extract the directory names from the command-line arguments
directories = sys.argv[1:]

# List files in the directories
files = []
for directory in directories:
    files.extend([os.path.join(directory, filename) for filename in os.listdir(directory) if filename.endswith(".dat")])

# Group files by their names
file_groups = {}
for file in files:
    name = os.path.basename(file)
    if name not in file_groups:
        file_groups[name] = [file]
    else:
        file_groups[name].append(file)

# Print header
print("Date,", end="")
for directory in directories:
    print(f" {directory},", end="")
print()  # Move to the next line


# Compare same-named files across directories
for files in file_groups.values():
    compare_files(files)



import os
import sys
import re

def parse_file(filename):
    # Initialize counters for each section
    checked_in_count = 0
    checked_out_count = 0
    valet_date = None

    # Regular expression pattern for matching the specified format
    pattern = r'^ *[a-z][a-z][0-9][0-9]*, *[0-2][0-9]:[0-5][0-9] *$'

    # Open the file and read line by line
    with open(filename, 'r') as file:
        # Flag to indicate which section we are in
        in_section = False
        out_section = False

        for line in file:
            line = line.strip()
            # Parse the valet date
            if line.startswith("Valet date:"):
                if valet_date is None:
                    valet_date = line.split(":")[1].strip()
                elif valet_date != line.split(":")[1].strip():
                    return None, None, None  # Different dates found
                continue

            # Check if we're entering or leaving a section
            if "Bikes checked in / tags out:" in line:
                in_section = True
                out_section = False
                continue
            elif "Bikes checked out / tags in:" in line:
                out_section = True
                in_section = False
                continue


            # Check if the line matches the specified pattern
            if re.match(pattern, line):
                # Count lines based on the section
                if in_section:
                    checked_in_count += 1
                elif out_section:
                    checked_out_count += 1
            else:
                in_section = False
                out_section = False

            # Count lines based on the section
            if in_section and not line.strip() == "":
                checked_in_count += 1
            elif out_section and not line.strip() == "":
                checked_out_count += 1

    return valet_date, checked_in_count - checked_out_count

def compare_twins(dir1, dir2):
    # Print header
    print("Date, File 1, File 2")

    # List files in the directories
    files1 = os.listdir(dir1)
    files2 = os.listdir(dir2)

    # Compare same-named files between the directories
    for file1 in files1:
        if file1.endswith(".dat") and file1 in files2:
            filename1 = os.path.join(dir1, file1)
            filename2 = os.path.join(dir2, file1)
            # Parse both files
            date1, difference1 = parse_file(filename1)
            date2, difference2 = parse_file(filename2)
            # Check if the dates parsed from both files are the same
            if date1 != date2:
                print(f"Error: {date1} != {date2}, {filename1}, {filename2}")
            elif difference1 != difference2:
                # Print the date, difference in file 1, and difference in file 2
                print(f"{date1}, {difference1}, {difference2}")
            else:
                # Print the date, difference in file 1, and difference in file 2
                print(f"        {date1}, {difference1}, {difference2}")


# Check if the directory names are provided as command-line arguments
if len(sys.argv) < 3:
    print("Please provide two directory names as command-line arguments.")
    sys.exit(1)

# Extract the directory names from the command-line arguments
dir1 = sys.argv[1]
dir2 = sys.argv[2]

compare_twins(dir1, dir2)
'''
