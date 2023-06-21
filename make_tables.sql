/*TagTracker by Julias Hocking.

SQL script for creating tag tracking database tables.

This is intended to be .read on the desired .db file using SQLite 3.

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
*/


-- Create bike types table - referenced by visit constraints
CREATE TABLE IF NOT EXISTS bike_type_codes (
    code  TEXT PRIMARY KEY NOT NULL,
    descr TEXT NOT NULL);
-- Populate with bike types
INSERT INTO bike_type_codes (code, descr) VALUES
    ('regular','a bike stored on racks'),
    ('oversize','everything else');


-- Create 'visit' table for visit data
CREATE TABLE IF NOT EXISTS visit (
    id          TEXT PRIMARY KEY UNIQUE,
    date        TEXT CHECK (date IS strftime('%Y-%m-%d', date)),
    tag         TEXT , -- also foreign key to a table of many many many tags? maybe regex instead
    type        TEXT NOT NULL, -- see foreign key below
    time_in     TEXT CHECK (time_in  IS strftime('%H:%M', time_in)),
    time_out    TEXT CHECK (time_out IS strftime('%H:%M', time_out)),
    duration    TEXT CHECK (duration IS strftime('%H:%M', duration)),
    leftover    TEXT CHECK (leftover IN ('yes', 'no')),
    notes       TEXT,
    batch       TEXT CHECK (batch IS strftime('%Y-%m-%dT%H:%M', batch)),
    -- Constrain column `type` to only allow `code` values in bike_type_codes
    -- needs PRAGMA foreign_keys=ON to work
    FOREIGN KEY (type) REFERENCES bike_type_codes(code)
);


-- Create table for daily summaries of visit data.
CREATE TABLE IF NOT EXISTS day (
    date            TEXT PRIMARY_KEY UNIQUE,
    parked_regular  INTEGER NOT NULL    CHECK (parked_regular >= 0),
    parked_oversize INTEGER NOT NULL    CHECK (parked_oversize >= 0),
    parked_total    INTEGER NOT NULL    CHECK (parked_total >= 0),
    leftover        INTEGER NOT NULL    CHECK (leftover >= 0),
    max_reg         INTEGER NOT NULL    CHECK (max_reg >= 0),
    time_max_reg    TEXT                CHECK   (time_max_reg IS strftime('%H:%M', time_max_reg)),
    max_over        INTEGER NOT NULL    CHECK (max_over >= 0),
    time_max_over   TEXT                CHECK  (time_max_over IS strftime('%H:%M', time_max_over)),
    max_total       INTEGER NOT NULL    CHECK (max_total >= 0),
    time_max_total  TEXT                CHECK (time_max_total IS strftime('%H:%M', time_max_total)),
    time_open       TEXT                CHECK      (time_open IS strftime('%H:%M', time_open)),
    time_closed     TEXT                CHECK    (time_closed IS strftime('%H:%M', time_closed)),
    day_of_week     INTEGER NOT NULL    CHECK (0 <= max_reg <= 6),
    precip_mm       NUMERIC             CHECK (precip_mm < 20), -- max ever daily precip is 11.4mm
    temp_10am       NUMERIC             CHECK (temp_10am < 50),
    sunset          TEXT                CHECK         (sunset IS strftime('%H:%M', sunset)),
    event           TEXT,
    event_prox_km   NUMERIC,
    registrations   NUMERIC,
    notes           TEXT,
    batch           TEXT                CHECK (batch IS strftime('%Y-%m-%dT%H:%M', batch))
);
-- only weirder constraints left