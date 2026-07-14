-- 官方球隊登錄名單（`/team/index?teamNo=` 的 TeamPlayersList）。
--
-- 為什麼需要：先前「現役選手」是**出賽推導**（batting_current/pitching_current 需有成績、
-- 二軍靠 gamelog 出賽），登錄了但整季未出賽的選手會被漏掉。ruan6047 裁示改以球團登錄名單
-- 為準。教練列亦在同頁（無 Acnt 連結），由 cpbl_coaches 另行處理，本表只收球員。
CREATE TABLE IF NOT EXISTS cpbl.team_roster (
    year        smallint NOT NULL,
    team_code   text     NOT NULL,
    player_id   text     NOT NULL,
    name        text     NOT NULL,
    pos         text,                       -- 投手／捕手／內野手／外野手
    uniform_no  text,
    updated_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (year, team_code, player_id)
);

CREATE INDEX IF NOT EXISTS idx_team_roster_player ON cpbl.team_roster (player_id);
