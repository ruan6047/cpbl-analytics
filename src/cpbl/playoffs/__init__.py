"""季後賽專頁的共用核心（#283 S02 起）。

``state``：T0–T5 與正交狀態的純函式（注入時鐘、無 I/O）。讀取與供應在
:mod:`cpbl.postseason_contract`；S04 的 readers／封套之後另建於本 package，不改 ``state``。
"""
