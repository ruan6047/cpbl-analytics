# CPBL 需求候選清單

這是進入 vNext 需求階段前的輕量清單，**不是 Project #10 的正式任務卡，也不代表已決定投入或進入需求階段**。原 Project #4 Issue 凍結保留供追溯；需求方確認現在要投入時，才核對現況並建立正式卡。是否開卡仍以 [CPBL 藍圖](ROADMAP.md) 的產品目標為準。

- **賽前對戰資訊**：球迷在單場頁看比賽前，是否仍缺少有用的對戰重點？來源：[舊 #60](https://github.com/ruan6047/cpbl-analytics/issues/60)。
- **外野守備洞察**：球迷是否需要能理解外野手守備表現的資訊，以及現有資料能否支持可信呈現？來源：[舊 #64](https://github.com/ruan6047/cpbl-analytics/issues/64)、[舊 #65](https://github.com/ruan6047/cpbl-analytics/issues/65)、[舊 #66](https://github.com/ruan6047/cpbl-analytics/issues/66)。
- **更多打席模擬視角**：球迷是否需要比較不同比賽情境或對手球隊下的打席結果，而目前功能無法滿足？來源：[舊 #67](https://github.com/ruan6047/cpbl-analytics/issues/67)、[舊 #68](https://github.com/ruan6047/cpbl-analytics/issues/68)。
- **球路品質理解**：球迷是否需要跨球種比較投手表現，且現有資料足以避免誤導？來源：[舊 #69](https://github.com/ruan6047/cpbl-analytics/issues/69)。
- **全場情境推演**：球迷是否需要從特定局面理解後續比賽可能走向，與既有打席模擬有何不同價值？來源：[舊 #70](https://github.com/ruan6047/cpbl-analytics/issues/70)。
- **勝率模型的近年資料假說**：只用較近年度資料，是否能改善場中勝率估計的校準？來源：[舊 #95](https://github.com/ruan6047/cpbl-analytics/issues/95)。
- **賽中與正式逐球資料**：賽中暫態資料與賽後正式資料出現差異時，是否需要可追溯地辨識與收斂？來源：[舊 #54](https://github.com/ruan6047/cpbl-analytics/issues/54)。
- **賽後資料時效**：球迷或後續資料使用者是否需要在當晚取得完整正式賽果，先確認目前空窗的影響與官方資料可用時間？來源：[舊 #57](https://github.com/ruan6047/cpbl-analytics/issues/57)、[舊 #73](https://github.com/ruan6047/cpbl-analytics/issues/73)。
- **遠端資料取得備援**：本機長時間無法運作時，是否仍需要可靠取得每日資料的替代方式？來源：[舊 #74](https://github.com/ruan6047/cpbl-analytics/issues/74)、[舊 #75](https://github.com/ruan6047/cpbl-analytics/issues/75)、[舊 #76](https://github.com/ruan6047/cpbl-analytics/issues/76)、[舊 #77](https://github.com/ruan6047/cpbl-analytics/issues/77)。
- **備份可還原性**：現有備份在主要環境故障時能否實際還原，是否需要再次演練才能確認？來源：[舊 #71](https://github.com/ruan6047/cpbl-analytics/issues/71)。
- **持續整合環境一致性**：不同檢查環境的日期與時區行為是否一致，是否存在尚未證實的誤判風險？來源：[舊 #129](https://github.com/ruan6047/cpbl-analytics/issues/129)。
- **歷史守備位置**：球迷是否需要在球隊歷史賽季頁看見可信的球員守備位置，缺資料時如何理解？來源：[舊 #82](https://github.com/ruan6047/cpbl-analytics/issues/82)。
- **研究結論與證據一致**：供決策引用的勝率研究報告，是否仍把「樣本不足以判定」寫成「證據不支持」，或以點估計的差異過度解讀融合模型的失敗理由？若要引用，先依現行判定與不確定性證據修正理由；舊卡列出的份數、分類和數字不可直接沿用。來源：[舊 #105](https://github.com/ruan6047/cpbl-analytics/issues/105)、[已完成 #101](https://github.com/ruan6047/cpbl-analytics/issues/101)。
- **逐球欄位語意**：使用 `game_livelog` 的開發者是否仍會被壘包欄位註解、未記載的時點或特殊規則壘況例外誤導？先核對現行詞彙表與資料，再補仍缺的說明；已記載的出局數語意不重做。來源：[舊 #108](https://github.com/ruan6047/cpbl-analytics/issues/108)。
- **對外勝率數字可對帳**：方法頁與 API 公開的勝率數字，是否都能與權威證據逐項比對，避免修正證據後仍留下舊數字？現有測試只涵蓋列入清單的數字，新增資料包或即時讀取不是預設方案。來源：[舊 #147](https://github.com/ruan6047/cpbl-analytics/issues/147)、[已完成 #100](https://github.com/ruan6047/cpbl-analytics/issues/100)。
- **一次性回填驗證腳本的去留**：`verify_deep_tm_backfill.py` 已標為不可執行的一次性產物，目前沒有日常呼叫者；是否刪除尚未裁定。若將來有明確再使用情境，才決定是否補真正的斷言。來源：[舊 #50](https://github.com/ruan6047/cpbl-analytics/issues/50)。
- **單場勝率呈現一致**：單場頁曲線與賽況事實所用的勝率來源，是否仍會讓同一場出現難以解釋的差異？先用當前案例確認使用者影響，再決定是否統一來源；舊卡的特定落差數字與遷移方案不可直接沿用。來源：[舊 #97](https://github.com/ruan6047/cpbl-analytics/issues/97)。
- **改期比賽的完賽宣稱**：有中止比分且改排未來日期的保留賽，頁面是否仍可能誤顯「終場」或賽後結論？原三場案例的改期日已過，需先找現行受影響案例；既有修正分支未通過查核，不算已交付。來源：[舊 #161](https://github.com/ruan6047/cpbl-analytics/issues/161)。
