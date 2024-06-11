/*TagTracker by Julias Hocking.

SQL script for creating tag tracking database tables.

This is intended to be .read on the desired .db file using SQLite 3.

Copyright (C) 2023-2024 Julias Hocking & Todd Glover

    Notwithstanding the licensing information below, this code may not
    be used in a commercial (for-profit, non-profit or government) setting
    without the copyright-holder's written consent.

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


-- Create tables for bikeparkingdb
--
-- Reminder: set PRAGMA FOREIGN KEYS = ON; at session starts

-- There would be a 1:1 corrrespondence between 'id' and 'handle' values.
-- 'id' column is useful in code; 'handle' is useful for URLs and things
-- that might be helpful for maintenance and urL parameters etc

-- Note to self: comments at end of lines are retained in the schema definition
-- so using them keeps them visible in the '.sch' command in sqlite3

CREATE TABLE ORG (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    org_handle TEXT NOT NULL,   -- shortform text form of org
    org_name TEXT,  -- optional(?) descriptive name of org
    can_view_orgs TEXT,    -- list of org_handles whose data this org can see
    UNIQUE (org_handle)
);

INSERT INTO ORG (org_handle,org_name,can_view_orgs) VALUES ("no_org","Default Org","*");

-- A site is an arbitrary name of a location or event an org manages.
-- It affects aggregations of an org's data but is not tied to authorization
CREATE TABLE ORGSITE ( -- arbitrary sites used by an org. Not tied to authz.
    id integer PRIMARY KEY AUTOINCREMENT,
    org_id INTEGER DEFAULT 1,   -- FIXME right now everything goes under one org
    site_handle TEXT DEFAULT 'unspecified', -- human-handy reference to the site
    site_name TEXT, -- optional long name of the site
    FOREIGN KEY (org_id) REFERENCES ORG (id),
    UNIQUE (org_id, site_handle)
);


CREATE TABLE DAY (  -- Summary data about one org at one site on one day
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    -- org_id INTEGER, -- is this needed?
    orgsite_id INTEGER,
    -- site_handle TEXT NOT NULL, -- don't need this if have orgsite_id

    date DATE
        NOT NULL
        CHECK(
            date LIKE '____-__-__'
            AND date BETWEEN '2000-01-01' AND '2100-01-01'
        ),


    time_open TEXT
        CHECK (
            time_open LIKE "__:__"
            AND time_open BETWEEN '00:00' AND '24:00'
        ),
    time_closed TEXT
        CHECK (
            time_closed LIKE "__:__"
            AND time_closed BETWEEN '00:00' AND '24:00'
        ),
    weekday INTEGER NOT NULL,

    num_parked_regular INTEGER,
    num_parked_oversize INTEGER,
    num_parked_combined INTEGER,

    num_remaining_regular INTEGER,
    num_remaining_oversize INTEGER,
    num_remaining_combined INTEGER,

    -- num_leftover INTEGER,

    num_fullest_regular INTEGER,
    num_fullest_oversize INTEGER,
    num_fullest_combined INTEGER,

    time_fullest_regular TEXT,
    time_fullest_oversize TEXT,
    time_fullest_combined TEXT,

    bikes_registered INTEGER,
    -- weather statistics are looked up online from government sources
    max_temperature FLOAT, -- to be looked up online, can be null
    precipitation FLOAT, -- to be looked up online, can be null
    -- time_dusk TEXT -- to be looked up online, can be null
    --    CHECK (
    --        time_open LIKE "__:__"
    --        AND time_open BETWEEN '00:00' AND '24:00'
    --    ),

    batch TEXT,
    -- FOREIGN KEY (org_id) REFERENCES ORG (id),
    FOREIGN KEY (orgsite_id) REFERENCES ORGSITE (id),
    -- UNIQUE ( date,org_id,orgsite_id)
    UNIQUE ( date,orgsite_id)
);
CREATE INDEX day_date_idx on day (date);
-- CREATE INDEX day_org_id_idx on day (org_id);
-- CREATE INDEX day_orgsite_id_idx on day (orgsite_id);

CREATE TABLE VISIT ( -- one bike visit for one org/site/date
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    day_id INTEGER,
    time_in TEXT --
        NOT NULL
        CHECK (
            time_in LIKE "__:__"
            AND time_in BETWEEN '00:00' AND '24:00'
        ),
    time_out TEXT
            CHECK (
            time_in = "" OR (time_in LIKE "__:__"
            AND time_in BETWEEN '00:00' AND '24:00')
        ),
    duration INTEGER,
    bike_type TEXT
        CHECK (bike_type IN ('R', 'O')),
    bike_id TEXT, -- optional str to identify the bike (eg a tagid)
    FOREIGN KEY (day_id) REFERENCES DAY (id) ON DELETE CASCADE
);

CREATE TABLE BLOCK ( -- activity in a given half hour for an org/site/date
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    day_id INTEGER,
    time_start TEXT
        NOT NULL
        CHECK(
            time_start LIKE "__:__"
            AND time_start BETWEEN '00:00' AND '24:00'
        ),

        num_incoming_regular INTEGER,
        num_incoming_oversize INTEGER,
        num_incoming_combined INTEGER,

        num_outgoing_regular INTEGER,
        num_outgoing_oversize INTEGER,
        num_outgoing_combined INTEGER,

        num_on_hand_regular INTEGER,
        num_on_hand_oversize INTEGER,
        num_on_hand_combined INTEGER,

        num_fullest_regular INTEGER,
        num_fullest_oversize INTEGER,
        num_fullest_combined INTEGER,

        time_fullest_regular TEXT
        CHECK(
            time_fullest_regular LIKE "__:__"
            AND time_fullest_regular BETWEEN '00:00' AND '24:00'
        ),
         time_fullest_oversize TEXT
        CHECK(
            time_fullest_oversize LIKE "__:__"
            AND time_fullest_oversize BETWEEN '00:00' AND '24:00'
        ),
        time_fullest_combined TEXT
        CHECK(
            time_fullest_combined LIKE "__:__"
            AND time_fullest_combined BETWEEN '00:00' AND '24:00'
        ),

    FOREIGN KEY (day_id) REFERENCES DAY (id) ON DELETE CASCADE
);

-- Information about the most recent successful data load
CREATE TABLE DATALOADS ( -- info about most recent successful data loads
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    day_id INTEGER,
    datafile_name TEXT, -- absolute path to file from which data loaded
    datafile_fingerprint TEXT, -- fingerprint (eg md5) of the file
    datafile_timestamp TEXT, -- timestamp of the file
    load_timestamp TEXT,    -- time at which the file was loaded
    batch TEXT,
    FOREIGN KEY (day_id) REFERENCES DAY (id) ON DELETE CASCADE
);



/*

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

*/
