-- 年度總冠軍成員：由官網 games(kind_code='C') 推導冠軍隊，
-- 標注該年一軍有成績的球員（season + gamelog）與總教練（managers 姓名比對）。
-- 由 cpbl-build-championships 離線重建（冪等 TRUNCATE+INSERT）。
CREATE TABLE IF NOT EXISTS cpbl.championship_members (
    player_id  text     NOT NULL,
    year       smallint NOT NULL,
    team_code  text     NOT NULL,
    role       text     NOT NULL DEFAULT 'player',  -- 'player' | 'manager'
    PRIMARY KEY (player_id, year)
);
CREATE INDEX IF NOT EXISTS idx_champ_members_player ON cpbl.championship_members (player_id);
