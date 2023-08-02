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
CREATE TABLE IF NOT EXISTS types (
    code  TEXT PRIMARY KEY NOT NULL,
    descr TEXT NOT NULL);
-- Populate with bike types
INSERT INTO types (code, descr) VALUES
    ('R','Regular - a bike stored in racks'),
    ('O', 'Oversize - rides not stored in racks');

-- Create 'visit' table for visit data
CREATE TABLE IF NOT EXISTS visit (
    id          TEXT PRIMARY KEY,
    date        TEXT CHECK (date IS strftime('%Y-%m-%d', date)),
    tag         TEXT NOT NULL,
    type        TEXT NOT NULL,
    time_in     TEXT CHECK (time_in  IS strftime('%H:%M', time_in)),
    time_out    TEXT CHECK ((time_out IS strftime('%H:%M', time_out)) OR (time_out IS '')),
    duration    TEXT CHECK (duration IS strftime('%H:%M', duration)),
    notes       TEXT,
    batch       TEXT CHECK (batch IS strftime('%Y-%m-%dT%H:%M', batch)),
    CHECK ((time_out >= time_in) OR (time_out IS ''))
    CHECK (tag glob '[a-z][a-z][0-9]' or tag glob '[a-z][a-z][a-z][0-9]' or tag glob '[a-z][a-z][0-9][0-9]' or tag glob '[a-z][a-z][a-z][0-9][0-9]')
    FOREIGN KEY (type) REFERENCES types(code)
);

-- Create table for daily summaries of visit data.
CREATE TABLE IF NOT EXISTS day (
    date            TEXT PRIMARY KEY,
    parked_regular  INTEGER NOT NULL CHECK (parked_regular >= 0),
    parked_oversize INTEGER NOT NULL CHECK (parked_oversize >= 0),
    parked_total    INTEGER NOT NULL CHECK (parked_total >= 0),
    leftover        INTEGER          CHECK (leftover >= 0),
    max_reg         INTEGER          CHECK (max_reg >= 0),
    time_max_reg    TEXT             CHECK (time_max_reg IS strftime('%H:%M', time_max_reg)),
    max_over        INTEGER          CHECK (max_over >= 0),
    time_max_over   TEXT             CHECK (time_max_over IS strftime('%H:%M', time_max_over)),
    max_total       INTEGER          CHECK (max_total >= 0),
    time_max_total  TEXT             CHECK (time_max_total IS strftime('%H:%M', time_max_total)),
    time_open       TEXT    NOT NULL CHECK (time_open IS strftime('%H:%M', time_open)),
    time_closed     TEXT    NOT NULL CHECK (time_closed IS strftime('%H:%M', time_closed)),
    weekday         INTEGER NOT NULL CHECK (1 <= weekday <= 7), -- ISO 8601: 1-7 Mon-Sun
    precip_mm       NUMERIC          CHECK (precip_mm < 90), -- Vic. record daily precip is 11.4 mm
    temp            NUMERIC          CHECK (temp < 50),
    sunset          TEXT             CHECK (sunset IS strftime('%H:%M', sunset)),
    event           TEXT,
    event_prox_km   NUMERIC,
    registrations   INTEGER,
    notes           TEXT,
    batch           TEXT             CHECK (batch IS strftime('%Y-%m-%dT%H:%M', batch)),

    CHECK (time_closed > time_open)
);


-- Taglists table for db-only operation and tracking tag context
CREATE TABLE IF NOT EXISTS taglist (
    date TEXT PRIMARY KEY,
    retired TEXT NOT NULL,
    oversize TEXT NOT NULL,
    regular TEXT NOT NULL
);


-- Views for data that is only from as recently as yesterday (account for partial days)
CREATE VIEW visit_except_today AS SELECT * FROM visit WHERE date < strftime('%Y-%m-%d');

CREATE VIEW day_except_today AS SELECT * FROM day WHERE date < strftime('%Y-%m-%d');