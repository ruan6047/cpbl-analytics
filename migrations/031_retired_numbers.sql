-- 各隊退休背號（引退背號）。來源＝維基 franchise 條目「退休背號」段，一次抓+手動刷新。
CREATE TABLE IF NOT EXISTS cpbl.retired_numbers (
  team_code    text NOT NULL,
  number       int  NOT NULL,
  holder_type  text NOT NULL,      -- player | fans | org
  player_id    text,               -- holder_type=player 且比對到才有（供連結球員頁）
  holder_name  text,               -- 顯示名（球員名／球迷／球團）
  retired_year int,
  status       text,               -- active（現存）| revoked（已失效/已恢復使用）
  note         text,
  source       text,
  needs_review boolean DEFAULT false,
  PRIMARY KEY (team_code, number)
);
