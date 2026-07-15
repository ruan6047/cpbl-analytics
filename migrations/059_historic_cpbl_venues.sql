-- 歷史 CPBL 場地：games 的「台中」與官網球場頁／既有 crawler key「國體」為同一場地。
-- CPBL 官方頁：https://cpbl.com.tw/field/cont?sid=0M062382190802773937
-- 規格採官方目前頁（非特定改建前後年份）；不以最後 CPBL 使用年推論場地是否已拆除或停用。
INSERT INTO cpbl.venue_dim (
  venue, full_name, turf, indoor, city, capacity, address,
  infield_seats, outfield_seats, lf_dist, cf_dist, rf_dist, big_screen, field_sid
) VALUES (
  '國體', '臺中棒球場', 'natural', false, '臺中市', 8500, '臺中市北區雙十路一段16號',
  5500, 3000, 340, 400, 340, false, '0M062382190802773937'
)
ON CONFLICT (venue) DO UPDATE SET
  full_name = COALESCE(venue_dim.full_name, EXCLUDED.full_name),
  turf = COALESCE(venue_dim.turf, EXCLUDED.turf),
  indoor = COALESCE(venue_dim.indoor, EXCLUDED.indoor),
  city = COALESCE(venue_dim.city, EXCLUDED.city),
  capacity = COALESCE(venue_dim.capacity, EXCLUDED.capacity),
  address = COALESCE(venue_dim.address, EXCLUDED.address),
  infield_seats = COALESCE(venue_dim.infield_seats, EXCLUDED.infield_seats),
  outfield_seats = COALESCE(venue_dim.outfield_seats, EXCLUDED.outfield_seats),
  lf_dist = COALESCE(venue_dim.lf_dist, EXCLUDED.lf_dist),
  cf_dist = COALESCE(venue_dim.cf_dist, EXCLUDED.cf_dist),
  rf_dist = COALESCE(venue_dim.rf_dist, EXCLUDED.rf_dist),
  big_screen = COALESCE(venue_dim.big_screen, EXCLUDED.big_screen),
  field_sid = COALESCE(venue_dim.field_sid, EXCLUDED.field_sid);
