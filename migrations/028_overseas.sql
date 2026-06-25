-- 球員旅外經歷（資料源：淡江棒球維基「臺灣旅外職棒球員列表」+ 各聯盟模板）。
-- 維基人工編修、一次性抓 + 手動刷新；只存能對到本站球員(player_id)者（旅外後曾打中職）。
-- 標 source/needs_review 提醒可能需人工複查。
CREATE TABLE IF NOT EXISTS cpbl.overseas (
    player_id    TEXT NOT NULL,
    league       TEXT NOT NULL,           -- 美國職棒 / 日本職棒 / 韓國職棒 / 美國獨立聯盟…
    team         TEXT,                     -- 加盟球隊（首次）
    from_year    INT  NOT NULL,            -- 加盟年度
    source       TEXT NOT NULL DEFAULT 'twbsball',
    needs_review BOOLEAN NOT NULL DEFAULT true,
    PRIMARY KEY (player_id, league, from_year)
);
CREATE INDEX IF NOT EXISTS idx_overseas_player ON cpbl.overseas (player_id);
