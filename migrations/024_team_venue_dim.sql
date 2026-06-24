-- teams / venues 維度表：消除「三處真值」與不可 join 問題。
-- team_dim PK 用營運碼 AAA011（對齊 games/standings/specialRecords，取代舊 teams 表的 3 碼 team_id）。
-- venue_dim PK 對齊 games.venue 官網簡稱（取代 venues.py 硬編，並可擴充 city/capacity）。
-- seed 以 ON CONFLICT DO UPDATE 保持冪等（migrate() 每次全跑）。

CREATE TABLE IF NOT EXISTS cpbl.team_dim (
  team_code  text PRIMARY KEY,
  short      text,
  full_name  text,
  nickname   text,
  color      text,
  letter     text,
  league     text,
  active     boolean DEFAULT true
);

INSERT INTO cpbl.team_dim (team_code, short, full_name, nickname, color, letter, active) VALUES
  ('AAA011', '味全', '味全龍',         '味全', '#C8102E', 'W', true),
  ('ACN011', '兄弟', '中信兄弟',       '中信', '#C8A24A', 'B', true),
  ('ADD011', '統一', '統一7-ELEVEn獅', '統一', '#E35A13', 'L', true),
  ('AEO011', '富邦', '富邦悍將',       '富邦', '#2A4B9B', 'G', true),
  ('AJL011', '樂天', '樂天桃猿',       '樂天', '#8E1537', 'R', true),
  ('AKP011', '台鋼', '台鋼雄鷹',       '台鋼', '#15543C', 'T', true)
ON CONFLICT (team_code) DO UPDATE SET
  short=EXCLUDED.short, full_name=EXCLUDED.full_name, nickname=EXCLUDED.nickname,
  color=EXCLUDED.color, letter=EXCLUDED.letter, active=EXCLUDED.active;

CREATE TABLE IF NOT EXISTS cpbl.venue_dim (
  venue      text PRIMARY KEY,
  full_name  text,
  turf       text,                 -- artificial | natural
  indoor     boolean DEFAULT false,
  city       text,
  capacity   integer
);

INSERT INTO cpbl.venue_dim (venue, full_name, turf, indoor, city) VALUES
  ('大巨蛋',   '臺北大巨蛋',         'artificial', true,  '臺北市'),
  ('天母',     '天母棒球場',         'artificial', false, '臺北市'),
  ('洲際',     '臺中洲際棒球場',     'natural',    false, '臺中市'),
  ('澄清湖',   '澄清湖棒球場',       'natural',    false, '高雄市'),
  ('新莊',     '新莊棒球場',         'natural',    false, '新北市'),
  ('樂天桃園', '樂天桃園棒球場',     'natural',    false, '桃園市'),
  ('亞太主',   '亞太棒球村',         'natural',    false, '臺南市'),
  ('嘉義市',   '嘉義市立棒球場',     'natural',    false, '嘉義市'),
  ('花蓮',     '花蓮德興棒球場',     'natural',    false, '花蓮縣'),
  ('台南',     '臺南市立棒球場',     'natural',    false, '臺南市'),
  ('台東',     '臺東棒球場',         'natural',    false, '臺東縣'),
  ('斗六',     '斗六棒球場',         'natural',    false, '雲林縣')
ON CONFLICT (venue) DO UPDATE SET
  full_name=EXCLUDED.full_name, turf=EXCLUDED.turf, indoor=EXCLUDED.indoor, city=EXCLUDED.city;
