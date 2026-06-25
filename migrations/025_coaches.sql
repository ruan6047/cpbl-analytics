-- 現役教練團（官網 /team/index 內嵌名單；僅現役、無歷史勝率）。
-- 每季重爬覆蓋（同 current 系列）。PK 含 name 以容忍無背號者。
CREATE TABLE IF NOT EXISTS cpbl.coaches (
    year       smallint NOT NULL,
    team_code  text     NOT NULL,
    name       text     NOT NULL,
    pos        text,                 -- 角色：一軍總教練 / 一軍投手教練 …
    uniform_no text,
    PRIMARY KEY (year, team_code, name)
);
