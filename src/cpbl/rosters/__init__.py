"""季後賽官方 32 人資格名單（#284 S03）。

本機 `cpbl-roster` CLI 是唯一會員 writer：解析 → 預覽 → 消歧 → 帶預覽雜湊確認的單交易提交。
生產只經 `scripts/refresh-cpbl-prod.sh` 的 `ROSTER_ONLY=1` 模式做 insert-only 同步（`sync.py`）。

⛔ 資格名單不代表先發、當場 28 人登錄或可用；本套件不產生任何可用性判斷。
"""
