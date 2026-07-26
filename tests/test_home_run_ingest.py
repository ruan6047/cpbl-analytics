"""/stats/hr 逐轟 ingest 的 parser 與冪等寫入契約。"""


from cpbl.ingest import cpbl_home_runs as hr

_HTML = """
<table><tr><th>#</th><th>年度</th><th>場次</th><th>局數</th><th>日期</th><th>場地</th>
<th>打者</th><th>打者所屬球隊</th><th>投手</th><th>投手所屬球隊</th><th>打點</th><th>備註</th></tr>
<tr><td>1</td><td>2026</td><td>3</td><td>5</td><td>2026/03/29</td><td>大巨蛋</td>
<td><a href="/team/person?acnt=0000007304">曾聖安</a></td><td>味全龍</td>
<td><a href="/team/person?acnt=0000006906">艾菩樂</a></td><td>樂天桃猿</td><td>2</td><td>滿貫全壘打</td></tr>
<tr><td>2</td><td>2026</td><td>4</td><td></td><td></td><td></td>
<td>缺少連結</td><td></td><td><a href="/team/person?acnt=0000000001">投手</a></td><td></td><td>x</td><td></td></tr>
</table>
"""


def test_parse_hr_rows_keeps_event_identity_and_tolerates_missing_optional_cells() -> None:
    rows = hr.parse_home_runs(_HTML, "A")

    assert len(rows) == 1
    row = rows[0]
    assert row.key == (2026, "A", 3, 5, "0000007304", "0000006906")
    assert row.game_date.isoformat() == "2026-03-29"
    assert row.rbi == 2
    assert row.note == "滿貫全壘打"
    assert row.home_run_type is None
    assert row.citizenship is None


def test_parser_uses_source_year_and_does_not_assume_every_cell_exists() -> None:
    rows = hr.parse_home_runs(_HTML.replace("2026/03/29", "not-a-date"), "C")

    assert len(rows) == 1
    assert rows[0].year == 2026
    assert rows[0].kind_code == "C"
    assert rows[0].game_date is None


def test_enrich_dimension_matches_only_known_natural_keys() -> None:
    base = hr.parse_home_runs(_HTML, "A")
    matching = hr.parse_home_runs(_HTML, "A")
    unrelated = hr.parse_home_runs(_HTML.replace("0000007304", "0000009999"), "A")

    hr.apply_dimension(base, matching + unrelated, "home_run_type", 5)
    hr.apply_dimension(base, matching, "citizenship", 0)

    assert base[0].home_run_type == 5
    assert base[0].citizenship == 0


def test_upsert_is_parameterized_and_updates_dimension_values(monkeypatch) -> None:
    calls: list[tuple[str, list[tuple]]] = []

    class Cursor:
        def executemany(self, sql: str, records: list[tuple]) -> None:
            calls.append((sql, records))

    class Connection:
        def cursor(self) -> Cursor:
            return Cursor()

    class Context:
        def __enter__(self) -> Connection:
            return Connection()

        def __exit__(self, *_args) -> None:
            return None

    monkeypatch.setattr(hr, "conn", lambda: Context())
    row = hr.parse_home_runs(_HTML, "A")[0]
    row.home_run_type = 5
    row.citizenship = 0

    assert hr.upsert_home_runs([row]) == 1
    sql, records = calls[0]
    assert "VALUES (%s,%s,%s,%s,%s,%s," in sql
    assert "ON CONFLICT (year, kind_code, game_sno, inning, hitter_acnt, pitcher_acnt)" in sql
    assert "home_run_type=EXCLUDED.home_run_type" in sql
    assert records[0][-2:] == (5, 0)
