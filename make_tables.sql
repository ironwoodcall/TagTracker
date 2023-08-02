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
    ('regular','a bike stored on racks'),
    ('oversize','everything else');


-- Create all tags table - referenced by visit constraints
CREATE TABLE IF NOT EXISTS tags (tag_id TEXT PRIMARY KEY NOT NULL);
INSERT INTO tags (tag_id) VALUES -- All valid tags evr used downtown to check against
    ('be0'), ('be1'), ('be2'), ('be3'), ('be4'), ('be5'), ('be6'), ('be7'), ('be8'), ('be9'),
    ('bf0'), ('bf1'), ('bf2'), ('bf3'), ('bf4'), ('bf5'), ('bf6'), ('bf7'), ('bf8'), ('bf9'),
    ('bg0'), ('bg1'), ('bg2'), ('bg3'), ('bg4'), ('bg5'), ('bg6'), ('bg7'), ('bg8'), ('bg9'),
    ('bh0'), ('bh1'), ('bh2'), ('bh3'), ('bh4'), ('bh5'), ('bh6'), ('bh7'), ('bh8'), ('bh9'),
    ('bi0'), ('bi1'), ('bi2'), ('bi3'), ('bi4'), ('bi5'), ('bi6'), ('bi7'), ('bi8'), ('bi9'),
    ('bj0'), ('bj1'), ('bj2'), ('bj3'), ('bj4'), ('bj5'), ('bj6'), ('bj7'), ('bj8'), ('bj9'),
    ('bk0'), ('bk1'), ('bk2'), ('bk3'), ('bk4'), ('bk5'), ('bk6'), ('bk7'), ('bk8'), ('bk9'),
    ('bl0'), ('bl1'), ('bl2'), ('bl3'), ('bl4'), ('bl5'), ('bl6'), ('bl7'), ('bl8'), ('bl9'),
    ('bm0'), ('bm1'), ('bm2'), ('bm3'), ('bm4'), ('bm5'), ('bm6'), ('bm7'), ('bm8'), ('bm9'),
    ('bn0'), ('bn1'), ('bn2'), ('bn3'), ('bn4'), ('bn5'), ('bn6'), ('bn7'), ('bn8'), ('bn9'),
    ('bo0'), ('bo1'), ('bo2'), ('bo3'), ('bo4'), ('bo5'), ('bo6'), ('bo7'), ('bo8'), ('bo9'),
    ('bp0'), ('bp1'), ('bp2'), ('bp3'), ('bp4'), ('bp5'), ('bp6'), ('bp7'), ('bp8'), ('bp9'),
    ('bq0'), ('bq1'), ('bq2'), ('bq3'), ('bq4'), ('bq5'), ('bq6'), ('bq7'), ('bq8'), ('bq9'),
    ('br0'), ('br1'), ('br2'), ('br3'), ('br4'), ('br5'), ('br6'), ('br7'), ('br8'), ('br9'),
    ('bs0'), ('bs1'), ('bs2'), ('bs3'), ('bs4'), ('bs5'), ('bs6'), ('bs7'), ('bs8'), ('bs9'),
    ('bt0'), ('bt1'), ('bt2'), ('bt3'), ('bt4'), ('bt5'), ('bt6'), ('bt7'), ('bt8'), ('bt9'),

    ('oa0'), ('oa1'), ('oa2'), ('oa3'), ('oa4'), ('oa5'), ('oa6'), ('oa7'), ('oa8'), ('oa9'), ('oa10'), ('oa11'), ('oa12'), ('oa13'), ('oa14'), ('oa15'),
    ('ob0'), ('ob1'), ('ob2'), ('ob3'), ('ob4'), ('ob5'), ('ob6'), ('ob7'), ('ob8'), ('ob9'), ('ob10'), ('ob11'), ('ob12'), ('ob13'), ('ob14'), ('ob15'),
    ('oc0'), ('oc1'), ('oc2'), ('oc3'), ('oc4'), ('oc5'), ('oc6'), ('oc7'), ('oc8'), ('oc9'), ('oc10'), ('oc11'), ('oc12'), ('oc13'), ('oc14'), ('oc15'),
    ('od0'), ('od1'), ('od2'), ('od3'), ('od4'), ('od5'), ('od6'), ('od7'), ('od8'), ('od9'), ('od10'), ('od11'), ('od12'), ('od13'), ('od14'), ('od15'),
    ('oe0'), ('oe1'), ('oe2'), ('oe3'), ('oe4'), ('oe5'), ('oe6'), ('oe7'), ('oe8'), ('oe9'), ('oe10'), ('oe11'), ('oe12'), ('oe13'), ('oe14'), ('oe15'),

    ('pa0'), ('pa1'), ('pa2'), ('pa3'), ('pa4'), ('pa5'), ('pa6'), ('pa7'), ('pa8'), ('pa9'), ('pa10'), ('pa11'), ('pa12'), ('pa13'), ('pa14'), ('pa15'),
    ('pb0'), ('pb1'), ('pb2'), ('pb3'), ('pb4'), ('pb5'), ('pb6'), ('pb7'), ('pb8'), ('pb9'), ('pb10'), ('pb11'), ('pb12'), ('pb13'), ('pb14'), ('pb15'),
    ('pc0'), ('pc1'), ('pc2'), ('pc3'), ('pc4'), ('pc5'), ('pc6'), ('pc7'), ('pc8'), ('pc9'), ('pc10'), ('pc11'), ('pc12'), ('pc13'), ('pc14'), ('pc15'),
    ('pd0'), ('pd1'), ('pd2'), ('pd3'), ('pd4'), ('pd5'), ('pd6'), ('pd7'), ('pd8'), ('pd9'), ('pd10'), ('pd11'), ('pd12'), ('pd13'), ('pd14'), ('pd15'),
    ('pe0'), ('pe1'), ('pe2'), ('pe3'), ('pe4'), ('pe5'), ('pe6'), ('pe7'), ('pe8'), ('pe9'), ('pe10'), ('pe11'), ('pe12'), ('pe13'), ('pe14'), ('pe15'),

    ('wa0'), ('wa1'), ('wa2'), ('wa3'), ('wa4'), ('wa5'), ('wa6'), ('wa7'), ('wa8'), ('wa9'), ('wa10'), ('wa11'), ('wa12'), ('wa13'), ('wa14'), ('wa15'),
    ('wb0'), ('wb1'), ('wb2'), ('wb3'), ('wb4'), ('wb5'), ('wb6'), ('wb7'), ('wb8'), ('wb9'), ('wb10'), ('wb11'), ('wb12'), ('wb13'), ('wb14'), ('wb15'),
    ('wc0'), ('wc1'), ('wc2'), ('wc3'), ('wc4'), ('wc5'), ('wc6'), ('wc7'), ('wc8'), ('wc9'), ('wc10'), ('wc11'), ('wc12'), ('wc13'), ('wc14'), ('wc15'),
    ('wd0'), ('wd1'), ('wd2'), ('wd3'), ('wd4'), ('wd5'), ('wd6'), ('wd7'), ('wd8'), ('wd9'), ('wd10'), ('wd11'), ('wd12'), ('wd13'), ('wd14'), ('wd15'),
    ('we0'), ('we1'), ('we2'), ('we3'), ('we4'), ('we5'), ('we6'), ('we7'), ('we8'), ('we9'), ('we10'), ('we11'), ('we12'), ('we13'), ('we14'), ('we15')
;


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