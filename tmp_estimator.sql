/* This query returns the number of bikes before/after
*  a given time of day for given day(s) of the week
*  and for a given closing time.  It is to get base data
*  from which to make estimates of further expected bikes.
*/


/* This is chatgpt's suggested improved version */
WITH all_dates AS (
    SELECT DISTINCT date FROM visit
)

SELECT
    day.date AS date,
    COALESCE(v1.before, 0) AS before,
    COALESCE(v2.after, 0) AS after
FROM
    day
LEFT JOIN (
    SELECT
        all_dates.date,
        COUNT(visit.date) AS before
    FROM
        all_dates
    LEFT JOIN
        visit ON all_dates.date = visit.date
               AND visit.time_in <= "16:30"
    GROUP BY
        all_dates.date
) AS v1 ON day.date = v1.date
LEFT JOIN (
    SELECT
        all_dates.date,
        COUNT(visit.date) AS after
    FROM
        all_dates
    LEFT JOIN
        visit ON all_dates.date = visit.date
               AND visit.time_in > "16:30"
    GROUP BY
        all_dates.date
) AS v2 ON day.date = v2.date
WHERE
    day.weekday IN (1, 2, 3, 4, 5)
    AND day.time_closed = "18:00"
ORDER BY
    day.date;




/* this was my earlier version. */
SELECT
    v1.before before, v2.after after
FROM
    day,

    (
        WITH all_dates AS (
            SELECT DISTINCT date FROM visit
        )
        SELECT all_dates.date, COUNT(visit.date) before
        FROM all_dates
        LEFT JOIN
            visit ON all_dates.date = visit.date
            AND visit.time_in <= "16:30"
        GROUP BY all_dates.date
        ORDER BY all_dates.date
    )
    v1,

    (
        WITH all_dates AS (
            SELECT DISTINCT date FROM visit
        )
        SELECT all_dates.date, COUNT(visit.date) after
        FROM all_dates
        LEFT JOIN
            visit ON all_dates.date = visit.date
            AND visit.time_in > "16:30"
        GROUP BY all_dates.date
        ORDER BY all_dates.date
    )
    v2

    WHERE
        day.date = v1.date
        AND day.date = v2.date
        AND day.weekday in (1,2,3,4,5)
        AND day.time_closed = "18:00"
;

