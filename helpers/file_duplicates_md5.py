"""Find files that are duplicate as determined by identical md5hash.

usage: this_program dir [dir..]

Output right now is *extremely* ugly

Todd Glover
2024-02
"""


import os
import sys
import hashlib
from collections import defaultdict

def find_duplicate_files(start_folders):
    # Dictionary to store files grouped by their md5 hash
    files_by_md5 = defaultdict(list)

    for start_folder in start_folders:
        # Iterate through all files and subdirectories in each start folder
        for root, _, files in os.walk(start_folder):
            for filename in files:
                filepath = os.path.join(root, filename)
                # Calculate the md5 hash of the file
                with open(filepath, 'rb') as f:
                    file_hash = hashlib.md5()
                    while chunk := f.read(4096):
                        file_hash.update(chunk)
                    file_md5 = file_hash.hexdigest()
                # Add the file path to the dictionary using the md5 hash as key
                files_by_md5[file_md5].append(filepath)
    
    # Filter out groups with only one file (no duplicates)
    duplicate_files = {md5: paths for md5, paths in files_by_md5.items() if len(paths) > 1}
    
    return duplicate_files

if __name__ == "__main__":
    # Check if directories are provided as command-line arguments
    if len(sys.argv) < 2:
        print("Usage: python script.py directory1 [directory2 ...]")
        sys.exit(1)

    start_folders = sys.argv[1:]

    duplicates = find_duplicate_files(start_folders)

    if duplicates:
        print("Duplicate files found:")
        for filepaths in duplicates.values():
            max_lengths = [len(filepath) for filepath in filepaths]
            for i, filepath in enumerate(filepaths):
                print(filepath.ljust(max_lengths[i] + 1), end=' ')
            print()
    else:
        print("No duplicate files found.")





'''
import os
import sys
import hashlib
from collections import defaultdict

def find_duplicate_files(start_folders):
    # Dictionary to store files grouped by their md5 hash
    files_by_md5 = defaultdict(list)

    for start_folder in start_folders:
        # Iterate through all files and subdirectories in each start folder
        for root, _, files in os.walk(start_folder):
            for filename in files:
                filepath = os.path.join(root, filename)
                # Calculate the md5 hash of the file
                with open(filepath, 'rb') as f:
                    file_hash = hashlib.md5()
                    while chunk := f.read(4096):
                        file_hash.update(chunk)
                    file_md5 = file_hash.hexdigest()
                # Add the file path to the dictionary using the md5 hash as key
                files_by_md5[file_md5].append(filepath)
    
    # Filter out groups with only one file (no duplicates)
    duplicate_files = {md5: paths for md5, paths in files_by_md5.items() if len(paths) > 1}
    
    return duplicate_files

if __name__ == "__main__":
    # Check if directories are provided as command-line arguments
    if len(sys.argv) < 2:
        print("Usage: python script.py directory1 [directory2 ...]")
        sys.exit(1)

    start_folders = sys.argv[1:]

    duplicates = find_duplicate_files(start_folders)

    if duplicates:
        print("Duplicate files found:")
        for filepaths in duplicates.values():
            print(",".join(filepaths))
    else:
        print("No duplicate files found.")
'''
