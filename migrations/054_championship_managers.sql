-- 1990–2025 年度總冠軍「奪冠總教練」canonical dataset。
--
-- 為什麼要這張表：`managers.championships`（來源 zh.wikipedia 球隊條目）不可信——36 個冠軍年
-- 中有 17 筆為 0（洪一中實際 7 座、呂文生 4 座、羅國璋被灌成 5 座）。而以 managers 任期年份
-- 反推同樣不可行：12 個冠軍年因季中換帥對到 2–3 位候選教練，年份粒度無法決定「奪冠當下是誰帶隊」。
--
-- 定案依據（逐年交叉查證，不採單一來源）：
--   1. zh.wikipedia 球隊條目「歷屆總教練」表（cpbl.managers）
--   2. 台灣棒球維基館個人條目經歷節（cpbl.coach_history），含精確到日的任期與敘事佐證
--   兩者衝突或多候選時，以個人條目的**職稱與精確起訖**為準（可分辨總教練／首席／代理／二軍）。
-- 官網無歷任總教練名單（/team/index 僅現任），故無官方來源可引，一律標註 twbsball 條目。
--
-- 換帥年的判定證據（此表最容易出錯之處，逐年留痕）：
--   1992 森下正夫：1991–92 副總教練，1992 升總教練（山根俊英 1993 才接任）
--   1999 徐生明：同年寺岡孝為「打擊教練」非總教練
--   2000 曾智偵：竹之內雅史該年僅「首席教練／代理總教練」
--   2001 林易增：3/20 接替戰績不佳下台的林百亨
--   2004–05 劉榮華：陳威成／陳秀雄任期解析雜訊，非當年總教練
--   2006 洪一中：蔡榮宗該期為「首席兼打擊教練」
--   2007–2011 呂文生：任期 2007/06/29–2012/02/16（大橋穰 2007/04 遭解任、羅國璋為首席教練僅短暫代理）；
--                      並以「亞洲職棒大賽中職冠軍代表隊總教練」身分出賽 2007／2008／2011，獨立佐證
--   2010 陳瑞振：陳琦豐該期為「首席教練」
--   2013 陳連宏：以代理總教練 4 勝 0 敗拿下總冠軍後真除（羅國璋僅代理開幕戰三場）
--   2016 葉君璋：張建銘無總教練職歷紀錄
CREATE TABLE IF NOT EXISTS cpbl.championship_managers (
    year                smallint PRIMARY KEY REFERENCES cpbl.championships(year),
    manager_name        text        NOT NULL,
    franchise_code      text        NOT NULL,
    source_url          text        NOT NULL,
    verification_status text        NOT NULL DEFAULT 'pending'
        CHECK (verification_status IN ('pending', 'verified')),
    verified_at         timestamptz,
    note                text,
    CHECK (verification_status <> 'verified' OR verified_at IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_champ_managers_name
    ON cpbl.championship_managers (manager_name);

INSERT INTO cpbl.championship_managers (
    year, manager_name, franchise_code, source_url, verification_status, verified_at, note
) VALUES
    (1990, '宋宦勳',      'AAA011', 'https://twbsball.dils.tku.edu.tw/wiki/index.php/宋宦勳', 'verified', '2026-07-14T00:00:00+08:00', NULL),
    (1991, '鄭昆吉',      'ADD011', 'https://twbsball.dils.tku.edu.tw/wiki/index.php/鄭昆吉', 'verified', '2026-07-14T00:00:00+08:00', NULL),
    (1992, '森下正夫',    'ACN011', 'https://twbsball.dils.tku.edu.tw/wiki/index.php/森下正夫', 'verified', '2026-07-14T00:00:00+08:00', '1991–92 副總教練，1992 年升任總教練'),
    (1993, '山根俊英',    'ACN011', 'https://twbsball.dils.tku.edu.tw/wiki/index.php/山根俊英', 'verified', '2026-07-14T00:00:00+08:00', NULL),
    (1994, '山根俊英',    'ACN011', 'https://twbsball.dils.tku.edu.tw/wiki/index.php/山根俊英', 'verified', '2026-07-14T00:00:00+08:00', NULL),
    (1995, '大石彌太郎',  'ADD011', 'https://twbsball.dils.tku.edu.tw/wiki/index.php/大石彌太郎', 'verified', '2026-07-14T00:00:00+08:00', NULL),
    (1996, '大石彌太郎',  'ADD011', 'https://twbsball.dils.tku.edu.tw/wiki/index.php/大石彌太郎', 'verified', '2026-07-14T00:00:00+08:00', NULL),
    (1997, '徐生明',      'AAA011', 'https://twbsball.dils.tku.edu.tw/wiki/index.php/徐生明', 'verified', '2026-07-14T00:00:00+08:00', NULL),
    (1998, '徐生明',      'AAA011', 'https://twbsball.dils.tku.edu.tw/wiki/index.php/徐生明', 'verified', '2026-07-14T00:00:00+08:00', NULL),
    (1999, '徐生明',      'AAA011', 'https://twbsball.dils.tku.edu.tw/wiki/index.php/徐生明', 'verified', '2026-07-14T00:00:00+08:00', '同年寺岡孝為打擊教練，非總教練'),
    (2000, '曾智偵',      'ADD011', 'https://twbsball.dils.tku.edu.tw/wiki/index.php/曾智偵', 'verified', '2026-07-14T00:00:00+08:00', '竹之內雅史該年僅首席教練／代理總教練'),
    (2001, '林易增',      'ACN011', 'https://twbsball.dils.tku.edu.tw/wiki/index.php/林易增', 'verified', '2026-07-14T00:00:00+08:00', '3/20 接替林百亨接任總教練'),
    (2002, '林易增',      'ACN011', 'https://twbsball.dils.tku.edu.tw/wiki/index.php/林易增', 'verified', '2026-07-14T00:00:00+08:00', NULL),
    (2003, '林易增',      'ACN011', 'https://twbsball.dils.tku.edu.tw/wiki/index.php/林易增', 'verified', '2026-07-14T00:00:00+08:00', NULL),
    (2004, '劉榮華',      'AEO011', 'https://twbsball.dils.tku.edu.tw/wiki/index.php/劉榮華', 'verified', '2026-07-14T00:00:00+08:00', NULL),
    (2005, '劉榮華',      'AEO011', 'https://twbsball.dils.tku.edu.tw/wiki/index.php/劉榮華', 'verified', '2026-07-14T00:00:00+08:00', NULL),
    (2006, '洪一中',      'AJL011', 'https://twbsball.dils.tku.edu.tw/wiki/index.php/洪一中', 'verified', '2026-07-14T00:00:00+08:00', '蔡榮宗該期為首席兼打擊教練'),
    (2007, '呂文生',      'ADD011', 'https://twbsball.dils.tku.edu.tw/wiki/index.php/呂文生(1962)', 'verified', '2026-07-14T00:00:00+08:00', '任期 2007/06/29 起；大橋穰 4 月遭解任、羅國璋為首席教練'),
    (2008, '呂文生',      'ADD011', 'https://twbsball.dils.tku.edu.tw/wiki/index.php/呂文生(1962)', 'verified', '2026-07-14T00:00:00+08:00', NULL),
    (2009, '呂文生',      'ADD011', 'https://twbsball.dils.tku.edu.tw/wiki/index.php/呂文生(1962)', 'verified', '2026-07-14T00:00:00+08:00', NULL),
    (2010, '陳瑞振',      'ACN011', 'https://twbsball.dils.tku.edu.tw/wiki/index.php/陳瑞振', 'verified', '2026-07-14T00:00:00+08:00', '陳琦豐該期為首席教練'),
    (2011, '呂文生',      'ADD011', 'https://twbsball.dils.tku.edu.tw/wiki/index.php/呂文生(1962)', 'verified', '2026-07-14T00:00:00+08:00', '任期至 2012/02/16'),
    (2012, '洪一中',      'AJL011', 'https://twbsball.dils.tku.edu.tw/wiki/index.php/洪一中', 'verified', '2026-07-14T00:00:00+08:00', NULL),
    (2013, '陳連宏',      'ADD011', 'https://twbsball.dils.tku.edu.tw/wiki/index.php/陳連宏', 'verified', '2026-07-14T00:00:00+08:00', '以代理總教練 4 勝 0 敗奪冠後真除；羅國璋僅代理開幕戰三場'),
    (2014, '洪一中',      'AJL011', 'https://twbsball.dils.tku.edu.tw/wiki/index.php/洪一中', 'verified', '2026-07-14T00:00:00+08:00', NULL),
    (2015, '洪一中',      'AJL011', 'https://twbsball.dils.tku.edu.tw/wiki/index.php/洪一中', 'verified', '2026-07-14T00:00:00+08:00', NULL),
    (2016, '葉君璋',      'AEO011', 'https://twbsball.dils.tku.edu.tw/wiki/index.php/葉君璋', 'verified', '2026-07-14T00:00:00+08:00', '張建銘無總教練職歷紀錄'),
    (2017, '洪一中',      'AJL011', 'https://twbsball.dils.tku.edu.tw/wiki/index.php/洪一中', 'verified', '2026-07-14T00:00:00+08:00', NULL),
    (2018, '洪一中',      'AJL011', 'https://twbsball.dils.tku.edu.tw/wiki/index.php/洪一中', 'verified', '2026-07-14T00:00:00+08:00', NULL),
    (2019, '洪一中',      'AJL011', 'https://twbsball.dils.tku.edu.tw/wiki/index.php/洪一中', 'verified', '2026-07-14T00:00:00+08:00', NULL),
    (2020, '林岳平',      'ADD011', 'https://twbsball.dils.tku.edu.tw/wiki/index.php/林岳平', 'verified', '2026-07-14T00:00:00+08:00', NULL),
    (2021, '林威助',      'ACN011', 'https://twbsball.dils.tku.edu.tw/wiki/index.php/林威助', 'verified', '2026-07-14T00:00:00+08:00', NULL),
    (2022, '林威助',      'ACN011', 'https://twbsball.dils.tku.edu.tw/wiki/index.php/林威助', 'verified', '2026-07-14T00:00:00+08:00', NULL),
    (2023, '葉君璋',      'AAA011', 'https://twbsball.dils.tku.edu.tw/wiki/index.php/葉君璋', 'verified', '2026-07-14T00:00:00+08:00', NULL),
    (2024, '平野惠一',    'ACN011', 'https://twbsball.dils.tku.edu.tw/wiki/index.php/平野惠一', 'verified', '2026-07-14T00:00:00+08:00', NULL),
    (2025, '古久保健二',  'AJL011', 'https://twbsball.dils.tku.edu.tw/wiki/index.php/古久保健二', 'verified', '2026-07-14T00:00:00+08:00', NULL)
ON CONFLICT (year) DO UPDATE SET
    manager_name = EXCLUDED.manager_name,
    franchise_code = EXCLUDED.franchise_code,
    source_url = EXCLUDED.source_url,
    verification_status = EXCLUDED.verification_status,
    verified_at = EXCLUDED.verified_at,
    note = EXCLUDED.note;
