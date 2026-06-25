-- 維基百科 {{Infobox CPBL player}} 補充資料（所屬球隊／國際賽獎牌／歷年獎項）。
-- 一次抓 + 手動刷新；以 name+birthday 高信心比對到 players.id。

CREATE TABLE IF NOT EXISTS cpbl.wiki_tenures (
  player_id   text NOT NULL,
  phase       text NOT NULL,      -- player | coach | other(行政/領隊)
  seq         int  NOT NULL,
  team_raw    text NOT NULL,
  role        text,               -- 教練職稱（總教練/打擊教練…），球員時期為 NULL
  from_year   int,
  to_year     int,                -- NULL = 進行中
  source      text,
  needs_review boolean DEFAULT false,
  PRIMARY KEY (player_id, phase, seq)
);

CREATE TABLE IF NOT EXISTS cpbl.wiki_medals (
  player_id   text NOT NULL,
  seq         int  NOT NULL,
  color       text NOT NULL,      -- 金 | 銀 | 銅
  competition text,
  event       text,
  year        int,
  source      text,
  PRIMARY KEY (player_id, seq)
);

CREATE TABLE IF NOT EXISTS cpbl.wiki_awards (
  player_id text NOT NULL,
  seq       int  NOT NULL,
  award     text NOT NULL,
  note      text,                 -- 守備位置等附註（捕手/外野手…）
  years     int[],
  source    text,
  PRIMARY KEY (player_id, seq)
);
