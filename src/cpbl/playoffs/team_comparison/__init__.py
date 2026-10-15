"""季後賽第 2 區「隊伍表現」三範圍比較（#287 S06）。

- :mod:`.core`：純計算（原始計數嚴格加總、率、球風軸、連續紀錄、共享尺度）；無 I/O。
- :mod:`.builder`：本機離線 builder（``cpbl-build-team-comparison``），寫不可變 build／列並切 current。
- :mod:`.reader`：``playoffs-comparison/v1`` 唯讀組裝（GET 不讀 A gamelog、不重建）。
- :mod:`.sync`：本機 → 生產的 insert-only 同步（``refresh-cpbl-prod.sh`` 的 TEAM_COMPARISON_ONLY）。

⛔ 不 import／呼叫 ``cpbl.reports.background``、舊 assembler 或其同一計算（#287 D3）。
"""
