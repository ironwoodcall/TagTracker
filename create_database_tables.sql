/*TagTracker by Julias Hocking.

SQL script for creating database tables.

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
CREATE TABLE IF NOT EXISTS bike_size_codes (
    code  TEXT PRIMARY KEY NOT NULL,
    descr TEXT NOT NULL);


-- Populate above table
INSERT INTO bike_size_codes (code, descr) VALUES
    ('regular','a bike stored on racks'),
    ('oversize','everything else');


--Create 'visit' table for visit data
CREATE TABLE IF NOT EXISTS visit (
    id          TEXT PRIMARY KEY UNIQUE,
    date        TEXT NOT NULL,
    tag         TEXT NOT NULL,
    type        TEXT NOT NULL,
    time_in     TEXT NOT NULL,
    time_out    TEXT NOT NULL,
    duration    TEXT NOT NULL,
    leftover    TEXT NOT NULL,
    notes       TEXT,
    batch       TEXT NOT NULL,
    CONSTRAINT fk_vis_type
    FOREIGN KEY (type)
    REFERENCES bike_size_codes(code));


-- Create table for daily summaries of visit data.
CREATE TABLE IF NOT EXISTS day (
    date            TEXT PRIMARY_KEY UNIQUE,
    parked_regular  INTEGER,
    parked_oversize INTEGER,
    parked_total    INTEGER,
    leftover        INTEGER,
    max_reg         INTEGER,
    time_max_reg    TEXT,
    max_over        INTEGER,
    time_max_over   TEXT,
    max_total       INTEGER,
    time_max_total  TEXT,
    time_open       TEXT,
    time_closed     TEXT,
    day_of_week     INTEGER NOT NULL,
    precip_mm       NUMERIC,
    temp_10am       NUMERIC,
    sunset          TEXT,
    event           TEXT,
    event_prox_km   NUMERIC,
    registrations   NUMERIC, -- insert separately (TBD)
    notes           TEXT,
    batch           TEXT NOT NULL
);
