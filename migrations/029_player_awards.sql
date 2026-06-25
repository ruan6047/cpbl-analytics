-- 球員年度獎項得主（資料源：官網 /stats/yearaward 五分類，1990 起）。
-- 官網 winner cell 直接連 /team/person?acnt=<player_id>，故以 player_id 精準入庫、免名比對。
-- 一次性抓 + 手動刷新（官網爬蟲僅本機台灣 IP 可跑）。
CREATE TABLE IF NOT EXISTS cpbl.player_awards (
    player_id TEXT NOT NULL,
    year      INT  NOT NULL,
    category  TEXT NOT NULL,            -- 打擊 / 投手 / 金手套 / 最佳十人 / 其他
    award     TEXT NOT NULL,            -- 安打王 / 全壘打王 / 年度MVP / 投手(金手套) …
    source    TEXT NOT NULL DEFAULT 'cpbl',
    PRIMARY KEY (player_id, year, category, award)
);
CREATE INDEX IF NOT EXISTS idx_player_awards_player ON cpbl.player_awards (player_id);
