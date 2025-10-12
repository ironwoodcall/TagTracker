PRAGMA foreign_keys = OFF;
BEGIN TRANSACTION;

-- 1. Add new columns if they do not already exist
ALTER TABLE VISIT ADD COLUMN time_in_minutes INTEGER;
ALTER TABLE VISIT ADD COLUMN time_out_minutes INTEGER;

-- 2. Populate the new minute columns based on existing HH:MM or HH:MM:SS data
UPDATE VISIT
SET
    time_in_minutes = CASE
        WHEN time_in IS NULL OR time_in = '' THEN NULL
        WHEN length(time_in) = 5 AND time_in GLOB '[0-2][0-9]:[0-5][0-9]' THEN
            CASE
                WHEN substr(time_in, 1, 2) = '24' AND substr(time_in, 4, 2) = '00' THEN 1440
                ELSE CAST(substr(time_in, 1, 2) AS INTEGER) * 60 + CAST(substr(time_in, 4, 2) AS INTEGER)
            END
        WHEN length(time_in) = 8 AND time_in GLOB '[0-2][0-9]:[0-5][0-9]:[0-5][0-9]' THEN
            CASE
                WHEN substr(time_in, 1, 2) = '24' AND substr(time_in, 4, 2) = '00' AND substr(time_in, 7, 2) = '00' THEN 1440
                ELSE CAST(substr(time_in, 1, 2) AS INTEGER) * 60 + CAST(substr(time_in, 4, 2) AS INTEGER)
            END
        ELSE NULL
    END,
    time_out_minutes = CASE
        WHEN time_out IS NULL OR time_out = '' THEN NULL
        WHEN length(time_out) = 5 AND time_out GLOB '[0-2][0-9]:[0-5][0-9]' THEN
            CASE
                WHEN substr(time_out, 1, 2) = '24' AND substr(time_out, 4, 2) = '00' THEN 1440
                ELSE CAST(substr(time_out, 1, 2) AS INTEGER) * 60 + CAST(substr(time_out, 4, 2) AS INTEGER)
            END
        WHEN length(time_out) = 8 AND time_out GLOB '[0-2][0-9]:[0-5][0-9]:[0-5][0-9]' THEN
            CASE
                WHEN substr(time_out, 1, 2) = '24' AND substr(time_out, 4, 2) = '00' AND substr(time_out, 7, 2) = '00' THEN 1440
                ELSE CAST(substr(time_out, 1, 2) AS INTEGER) * 60 + CAST(substr(time_out, 4, 2) AS INTEGER)
            END
        ELSE NULL
    END;

-- 3. Recreate the VISIT table with updated CHECK constraints and copy data
CREATE TABLE VISIT_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    day_id INTEGER,
    time_in TEXT NOT NULL
        CHECK (
            length(time_in) = 8
            AND time_in GLOB '[0-2][0-9]:[0-5][0-9]:[0-5][0-9]'
            AND time_in BETWEEN '00:00:00' AND '24:00:00'
        ),
    time_in_minutes INTEGER
        CHECK (
            time_in_minutes IS NULL
            OR (time_in_minutes BETWEEN 0 AND 1440)
        ),
    time_out TEXT
        CHECK (
            time_out IS NULL
            OR time_out = ''
            OR (
                length(time_out) = 8
                AND time_out GLOB '[0-2][0-9]:[0-5][0-9]:[0-5][0-9]'
                AND time_out BETWEEN '00:00:00' AND '24:00:00'
            )
        ),
    time_out_minutes INTEGER
        CHECK (
            time_out_minutes IS NULL
            OR (time_out_minutes BETWEEN 0 AND 1440)
        ),
    duration INTEGER,
    bike_type TEXT
        CHECK (bike_type IN ('R', 'O')),
    bike_id TEXT,
    FOREIGN KEY (day_id) REFERENCES DAY (id) ON DELETE CASCADE
);

INSERT INTO VISIT_new (
    id,
    day_id,
    time_in,
    time_in_minutes,
    time_out,
    time_out_minutes,
    duration,
    bike_type,
    bike_id
)
SELECT
    id,
    day_id,
    CASE
        WHEN time_in IS NULL OR time_in = '' THEN NULL
        WHEN length(time_in) = 5 AND time_in GLOB '[0-2][0-9]:[0-5][0-9]' THEN
            time_in || ':00'
        WHEN length(time_in) = 8 AND time_in GLOB '[0-2][0-9]:[0-5][0-9]:[0-5][0-9]' THEN
            time_in
        ELSE time_in
    END,
    time_in_minutes,
    CASE
        WHEN time_out IS NULL OR time_out = '' THEN time_out
        WHEN length(time_out) = 5 AND time_out GLOB '[0-2][0-9]:[0-5][0-9]' THEN
            time_out || ':00'
        WHEN length(time_out) = 8 AND time_out GLOB '[0-2][0-9]:[0-5][0-9]:[0-5][0-9]' THEN
            time_out
        ELSE time_out
    END,
    time_out_minutes,
    duration,
    bike_type,
    bike_id
FROM VISIT;

DROP TABLE VISIT;
ALTER TABLE VISIT_new RENAME TO VISIT;

-- 4. Create indexes for faster lookups
CREATE INDEX IF NOT EXISTS visit_day_id_idx ON VISIT (day_id);
CREATE INDEX IF NOT EXISTS visit_time_in_minutes_idx ON VISIT (time_in_minutes);
CREATE INDEX IF NOT EXISTS visit_time_out_minutes_idx ON VISIT (time_out_minutes);

COMMIT;
PRAGMA foreign_keys = ON;
