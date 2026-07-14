-- 1990–2025 年度總冠軍 canonical dataset。
-- 實際進行總冠軍賽的年份以 CPBL 官方封王戰 box score 為逐年來源；
-- 1992／1994／1995 因包辦上下半季而直接奪冠，來源為 CPBL 官方歷史新聞，亞軍不適用。
CREATE TABLE IF NOT EXISTS cpbl.championships (
    year                  smallint PRIMARY KEY,
    champion_team_code    text        NOT NULL,
    runner_up_team_code   text,
    franchise_code        text        NOT NULL,
    source_url             text        NOT NULL,
    verification_status   text        NOT NULL DEFAULT 'pending'
        CHECK (verification_status IN ('pending', 'verified')),
    verified_at            timestamptz,
    CHECK (verification_status <> 'verified' OR verified_at IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_championships_franchise
    ON cpbl.championships (franchise_code, year);

INSERT INTO cpbl.championships (
    year, champion_team_code, runner_up_team_code, franchise_code,
    source_url, verification_status, verified_at
) VALUES
    (1990, 'AAA011', 'ABB011', 'AAA011', 'https://www.cpbl.com.tw/box?year=1990&KindCode=C&gameSno=6', 'verified', '2026-07-14T00:00:00+08:00'),
    (1991, 'ADD011', 'AAA011', 'ADD011', 'https://www.cpbl.com.tw/box?year=1991&KindCode=C&gameSno=7', 'verified', '2026-07-14T00:00:00+08:00'),
    (1992, 'ACC011', NULL,     'ACN011', 'https://www.cpbl.com.tw/xmdoc/cont?sid=0L132508224704611366', 'verified', '2026-07-14T00:00:00+08:00'),
    (1993, 'ACC011', 'ADD011', 'ACN011', 'https://www.cpbl.com.tw/box?year=1993&KindCode=C&gameSno=6', 'verified', '2026-07-14T00:00:00+08:00'),
    (1994, 'ACC011', NULL,     'ACN011', 'https://www.cpbl.com.tw/xmdoc/cont?sid=0L132508224704611366', 'verified', '2026-07-14T00:00:00+08:00'),
    (1995, 'ADD011', NULL,     'ADD011', 'https://www.cpbl.com.tw/xmdoc/cont?sid=0L132509713020586356', 'verified', '2026-07-14T00:00:00+08:00'),
    (1996, 'ADD011', 'AAA011', 'ADD011', 'https://www.cpbl.com.tw/box?year=1996&KindCode=C&gameSno=6', 'verified', '2026-07-14T00:00:00+08:00'),
    (1997, 'AAA011', 'AFF011', 'AAA011', 'https://www.cpbl.com.tw/box?year=1997&KindCode=C&gameSno=6', 'verified', '2026-07-14T00:00:00+08:00'),
    (1998, 'AAA011', 'AEG011', 'AAA011', 'https://www.cpbl.com.tw/box?year=1998&KindCode=C&gameSno=7', 'verified', '2026-07-14T00:00:00+08:00'),
    (1999, 'AAA011', 'AHH011', 'AAA011', 'https://www.cpbl.com.tw/box?year=1999&KindCode=C&gameSno=5', 'verified', '2026-07-14T00:00:00+08:00'),
    (2000, 'ADD011', 'AEG011', 'ADD011', 'https://www.cpbl.com.tw/box?year=2000&KindCode=C&gameSno=7', 'verified', '2026-07-14T00:00:00+08:00'),
    (2001, 'ACC011', 'ADD011', 'ACN011', 'https://www.cpbl.com.tw/box?year=2001&KindCode=C&gameSno=7', 'verified', '2026-07-14T00:00:00+08:00'),
    (2002, 'ACC011', 'AHH011', 'ACN011', 'https://www.cpbl.com.tw/box?year=2002&KindCode=C&gameSno=3', 'verified', '2026-07-14T00:00:00+08:00'),
    (2003, 'ACC011', 'AEG011', 'ACN011', 'https://www.cpbl.com.tw/box?year=2003&KindCode=C&gameSno=6', 'verified', '2026-07-14T00:00:00+08:00'),
    (2004, 'AEG011', 'ADD011', 'AEO011', 'https://www.cpbl.com.tw/box?year=2004&KindCode=C&gameSno=7', 'verified', '2026-07-14T00:00:00+08:00'),
    (2005, 'AEG011', 'AII011', 'AEO011', 'https://www.cpbl.com.tw/box?year=2005&KindCode=C&gameSno=4', 'verified', '2026-07-14T00:00:00+08:00'),
    (2006, 'AJK011', 'ADD011', 'AJL011', 'https://www.cpbl.com.tw/box?year=2006&KindCode=C&gameSno=4', 'verified', '2026-07-14T00:00:00+08:00'),
    (2007, 'ADD011', 'AJK011', 'ADD011', 'https://www.cpbl.com.tw/box?year=2007&KindCode=C&gameSno=7', 'verified', '2026-07-14T00:00:00+08:00'),
    (2008, 'ADD011', 'ACC011', 'ADD011', 'https://www.cpbl.com.tw/box?year=2008&KindCode=C&gameSno=7', 'verified', '2026-07-14T00:00:00+08:00'),
    (2009, 'ADD011', 'ACC011', 'ADD011', 'https://www.cpbl.com.tw/box?year=2009&KindCode=C&gameSno=7', 'verified', '2026-07-14T00:00:00+08:00'),
    (2010, 'ACC011', 'AEG011', 'ACN011', 'https://www.cpbl.com.tw/box?year=2010&KindCode=C&gameSno=4', 'verified', '2026-07-14T00:00:00+08:00'),
    (2011, 'ADD011', 'AJK011', 'ADD011', 'https://www.cpbl.com.tw/box?year=2011&KindCode=C&gameSno=5', 'verified', '2026-07-14T00:00:00+08:00'),
    (2012, 'AJK011', 'ADD011', 'AJL011', 'https://www.cpbl.com.tw/box?year=2012&KindCode=C&gameSno=5', 'verified', '2026-07-14T00:00:00+08:00'),
    (2013, 'ADD011', 'AEM011', 'ADD011', 'https://www.cpbl.com.tw/box?year=2013&KindCode=C&gameSno=4', 'verified', '2026-07-14T00:00:00+08:00'),
    (2014, 'AJK011', 'ACN011', 'AJL011', 'https://www.cpbl.com.tw/box?year=2014&KindCode=C&gameSno=5', 'verified', '2026-07-14T00:00:00+08:00'),
    (2015, 'AJK011', 'ACN011', 'AJL011', 'https://www.cpbl.com.tw/box?year=2015&KindCode=C&gameSno=7', 'verified', '2026-07-14T00:00:00+08:00'),
    (2016, 'AEM011', 'ACN011', 'AEO011', 'https://www.cpbl.com.tw/box?year=2016&KindCode=C&gameSno=6', 'verified', '2026-07-14T00:00:00+08:00'),
    (2017, 'AJK011', 'ACN011', 'AJL011', 'https://www.cpbl.com.tw/box?year=2017&KindCode=C&gameSno=4', 'verified', '2026-07-14T00:00:00+08:00'),
    (2018, 'AJK011', 'ADD011', 'AJL011', 'https://www.cpbl.com.tw/box?year=2018&KindCode=C&gameSno=5', 'verified', '2026-07-14T00:00:00+08:00'),
    (2019, 'AJK011', 'ACN011', 'AJL011', 'https://www.cpbl.com.tw/box?year=2019&KindCode=C&gameSno=5', 'verified', '2026-07-14T00:00:00+08:00'),
    (2020, 'ADD011', 'ACN011', 'ADD011', 'https://www.cpbl.com.tw/box?year=2020&KindCode=C&gameSno=7', 'verified', '2026-07-14T00:00:00+08:00'),
    (2021, 'ACN011', 'ADD011', 'ACN011', 'https://www.cpbl.com.tw/box?year=2021&KindCode=C&gameSno=4', 'verified', '2026-07-14T00:00:00+08:00'),
    (2022, 'ACN011', 'AJL011', 'ACN011', 'https://www.cpbl.com.tw/box?year=2022&KindCode=C&gameSno=4', 'verified', '2026-07-14T00:00:00+08:00'),
    (2023, 'AAA011', 'AJL011', 'AAA011', 'https://www.cpbl.com.tw/box?year=2023&KindCode=C&gameSno=7', 'verified', '2026-07-14T00:00:00+08:00'),
    (2024, 'ACN011', 'ADD011', 'ACN011', 'https://www.cpbl.com.tw/box?year=2024&KindCode=C&gameSno=5', 'verified', '2026-07-14T00:00:00+08:00'),
    (2025, 'AJL011', 'ACN011', 'AJL011', 'https://www.cpbl.com.tw/box?year=2025&KindCode=C&gameSno=5', 'verified', '2026-07-14T00:00:00+08:00')
ON CONFLICT (year) DO UPDATE SET
    champion_team_code = EXCLUDED.champion_team_code,
    runner_up_team_code = EXCLUDED.runner_up_team_code,
    franchise_code = EXCLUDED.franchise_code,
    source_url = EXCLUDED.source_url,
    verification_status = EXCLUDED.verification_status,
    verified_at = EXCLUDED.verified_at;
