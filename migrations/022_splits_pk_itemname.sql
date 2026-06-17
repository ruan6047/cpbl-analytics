-- 分項主鍵修正：官網「球場」分組所有列的 ItemIndex 都是 1，與舊主鍵
-- (year,kind_code,acnt,item_group_code,item_index) 衝突 → 9 個球場被 UPSERT 蓋成 1 筆。
-- 修法：把 item_name 加進主鍵（與 item_index 並存，6 欄）。球場 index 同、name 異 → 唯一；
-- 局數等空名列 name 同、index 異 → 唯一。新主鍵是舊主鍵的超集，既有資料必然不衝突。
-- 冪等：僅當主鍵尚未含 item_name 時才換。
UPDATE cpbl.batting_splits  SET item_name = '' WHERE item_name IS NULL;
UPDATE cpbl.pitching_splits SET item_name = '' WHERE item_name IS NULL;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint c
    JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY (c.conkey)
    WHERE c.conrelid = 'cpbl.batting_splits'::regclass AND c.contype = 'p' AND a.attname = 'item_name'
  ) THEN
    ALTER TABLE cpbl.batting_splits ALTER COLUMN item_name SET NOT NULL;
    ALTER TABLE cpbl.batting_splits DROP CONSTRAINT IF EXISTS batting_splits_pkey;
    ALTER TABLE cpbl.batting_splits
      ADD CONSTRAINT batting_splits_pkey PRIMARY KEY (year, kind_code, acnt, item_group_code, item_index, item_name);
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint c
    JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY (c.conkey)
    WHERE c.conrelid = 'cpbl.pitching_splits'::regclass AND c.contype = 'p' AND a.attname = 'item_name'
  ) THEN
    ALTER TABLE cpbl.pitching_splits ALTER COLUMN item_name SET NOT NULL;
    ALTER TABLE cpbl.pitching_splits DROP CONSTRAINT IF EXISTS pitching_splits_pkey;
    ALTER TABLE cpbl.pitching_splits
      ADD CONSTRAINT pitching_splits_pkey PRIMARY KEY (year, kind_code, acnt, item_group_code, item_index, item_name);
  END IF;
END $$;
