"""TagTracker by Julias Hocking.

Reporting functions for  the TagTracker suite.

Copyright (C) 2023 Julias Hocking

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU Affero General Public License as published
    by the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU Affero General Public License for more details.

    You should have received a copy of the GNU Affero General Public License
    along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

# Time ranges for categorizing stay-lengths, in hours.
# First category will always be 0 - [0], last will always be > [-1]
VISIT_CATEGORIES = [1.5,5]

# size of 'buckets' for calculating the mode stay time
MODE_ROUND_TO_NEAREST = 30 # mins

# List ow many ranked busiest times of day in report?
BUSIEST_RANKS = 4

