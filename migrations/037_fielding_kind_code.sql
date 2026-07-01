-- 守備當季表加軍別：官網 /team/teamscore 的守備(Position=03)本就支援 KindCode，
-- 但先前只抓一軍(A)。加 kind_code 欄以另存二軍(D)當季守備，PK 納入 kind_code。
-- 冪等：欄位 IF NOT EXISTS；PK 以 DROP IF EXISTS + ADD 重建（每次 migrate 全跑亦安全）。

ALTER TABLE cpbl.fielding_current ADD COLUMN IF NOT EXISTS kind_code text NOT NULL DEFAULT 'A';

ALTER TABLE cpbl.fielding_current DROP CONSTRAINT IF EXISTS fielding_current_pkey;
ALTER TABLE cpbl.fielding_current ADD CONSTRAINT fielding_current_pkey
    PRIMARY KEY (year, kind_code, player_id, pos);
