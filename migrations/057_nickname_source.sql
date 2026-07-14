-- 暱稱來源新增 'field+prose'：結構化欄位與內文取**聯集**而非欄位優先。
-- 實例：彭政閔的欄位列了火星恰／恰哥／中職先生／恰總，卻沒有他最廣為人知的「恰恰」——
-- 該詞只出現在內文。只取欄位會漏掉最具指標意義的稱呼（ruan6047 指正「蒼蠅」時一併發現）。
-- 含內文成分者仍標 needs_review（內文句型鬆散，易誤抓）。
ALTER TABLE cpbl.person_nickname DROP CONSTRAINT IF EXISTS person_nickname_source_check;
ALTER TABLE cpbl.person_nickname ADD CONSTRAINT person_nickname_source_check
    CHECK (source IN ('field', 'prose', 'field+prose'));
