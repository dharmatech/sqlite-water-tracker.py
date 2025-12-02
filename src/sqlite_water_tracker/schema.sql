
CREATE TABLE IF NOT EXISTS water_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    ounces REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS user_weight (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL, 
    weight_lbs REAL NOT NULL 
);
-- ----------------------------------------------------------------------

-- CREATE TABLE IF NOT EXISTS user_settings (
--     id INTEGER PRIMARY KEY AUTOINCREMENT,
--     weight_unit TEXT NOT NULL DEFAULT 'lbs' CHECK (weight_unit IN ('lbs', 'kg')),
--     activity_level TEXT NOT NULL DEFAULT 'moderate' CHECK (activity_level IN ('sedentary', 'light', 'moderate', 'active', 'very_active'))
-- );

-- ----------------------------------------------------------------------

DROP VIEW IF EXISTS water_log_daily;
CREATE VIEW water_log_daily AS
SELECT
    SUBSTR(timestamp, 1, 10) AS date,
    SUM(ounces) AS total
FROM water_log
GROUP BY date;

DROP VIEW IF EXISTS water_log_daily_with_weight;
CREATE VIEW water_log_daily_with_weight AS
SELECT
    date,
    total,
    (
        SELECT weight_lbs
        FROM user_weight
        WHERE SUBSTR(timestamp, 1, 10) <= date
        ORDER BY timestamp DESC
        LIMIT 1
    ) AS weight
FROM water_log_daily;

DROP VIEW IF EXISTS water_log_daily_with_weight_and_target;
CREATE VIEW water_log_daily_with_weight_and_target AS
SELECT
    date,
    total,
    weight,
    weight / 2 AS target
FROM water_log_daily_with_weight
ORDER BY date;

DROP VIEW IF EXISTS water_log_daily_with_weight_target_percent;
CREATE VIEW water_log_daily_with_weight_target_percent AS
SELECT
    date,
    total,
    weight,
    target,
    ROUND(total * 100.0 / target, 2) AS percent_of_target
FROM water_log_daily_with_weight_and_target;

DROP VIEW IF EXISTS water_log_full;
CREATE VIEW water_log_full AS
SELECT
    date,
    total,
    weight,
    target,
    percent_of_target
FROM water_log_daily_with_weight_target_percent
ORDER BY date;
-- ----------------------------------------------------------------------
DROP VIEW IF EXISTS last_24_hours_summary;
CREATE VIEW IF NOT EXISTS last_24_hours_summary AS
SELECT
    *,
    ROUND(total_ounces_last_24_hours * 100.0 / target_ounces, 2) AS percent_of_target
FROM
(
    SELECT
        *,
        weight / 2 AS target_ounces
    FROM
    (
        SELECT 
            (SELECT SUM(ounces) FROM water_log WHERE timestamp >= datetime('now', '-1 day', 'localtime')) AS total_ounces_last_24_hours,
            (SELECT weight_lbs FROM user_weight ORDER BY timestamp DESC LIMIT 1)                          AS weight
    )    
);
-- ----------------------------------------------------------------------
DROP VIEW IF EXISTS rolling_24_hour_summary;
CREATE VIEW rolling_24_hour_summary AS
SELECT
    w1.id,
    w1.timestamp,
    w1.ounces,
    (
        SELECT SUM(w2.ounces)
        FROM water_log AS w2
        WHERE
            w2.timestamp > datetime(w1.timestamp, '-24 hours')
            AND w2.timestamp <= w1.timestamp
    ) AS rolling_24h_ounces
FROM water_log AS w1
ORDER BY w1.timestamp;

DROP VIEW IF EXISTS rolling_24_hour_summary_with_weight;
CREATE VIEW rolling_24_hour_summary_with_weight AS
SELECT
    id,
    timestamp,
    ounces,
    rolling_24h_ounces,
    (
        SELECT weight_lbs
        FROM user_weight
        WHERE timestamp <= r.timestamp
        ORDER BY timestamp DESC
        LIMIT 1
    ) AS weight
FROM rolling_24_hour_summary AS r;

DROP VIEW IF EXISTS rolling_24_hour_summary_with_weight_and_target;
CREATE VIEW rolling_24_hour_summary_with_weight_and_target AS
SELECT
    id,
    timestamp,
    ounces,
    rolling_24h_ounces,
    weight,
    weight / 2 AS target
FROM rolling_24_hour_summary_with_weight
ORDER BY timestamp;

DROP VIEW IF EXISTS rolling_24_hour_summary_with_weight_target_percent;
CREATE VIEW rolling_24_hour_summary_with_weight_target_percent AS
SELECT
    id,
    timestamp,
    ounces,
    rolling_24h_ounces,
    weight,
    target,
    ROUND(rolling_24h_ounces * 100.0 / target, 2) AS percent_of_target
FROM rolling_24_hour_summary_with_weight_and_target
ORDER BY timestamp;

DROP VIEW IF EXISTS rolling_log_full;
CREATE VIEW rolling_log_full AS
SELECT
    timestamp,
    ounces,
    rolling_24h_ounces,
    weight,
    target,
    percent_of_target
FROM rolling_24_hour_summary_with_weight_target_percent
ORDER BY timestamp;