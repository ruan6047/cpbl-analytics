// 「如果現在對決」的固定 fixture（UX-PA-SIM-MATCHUP1）。
//
// FIXTURE_OK_* 逐字複製自 production `GET /api/v1/outcome/plate-appearance`
// （2026-07-25 實測，hitter=0000003467／pitcher=0000001821、trained_through=2025），
// 因此契約測試對帳的是真實回應形狀，不是想像的形狀。退化態 fixture 由真實回應
// 派生（只改判定相關欄位），確保「唯一差異就是被測條件」。
import type { PaSimOk, PaSimResponse } from "./api";

/** 中性情境（1 局上、無人出局、壘上無人、0–0）：低槓桿，delta 幅度小。 */
export const FIXTURE_OK_NEUTRAL: PaSimOk = {
  "available": true,
  "trained_through": 2025,
  "wp_span": "2018-2025",
  "uncertainty_method": "normal approximation over shrinkage effective sample size",
  "sample": {
    "hitter_pa": 3000,
    "pitcher_pa": 1376,
    "direct_pa": 39,
    "low_sample": false,
    "shrinkage_weight": {
      "hitter": 0.9375,
      "pitcher": 0.7747747747747747,
      "direct": 0.16317991631799164
    }
  },
  "state": {
    "inning": 1,
    "half": "1",
    "bases": "___",
    "outs": 0,
    "away_score": 0,
    "home_score": 0
  },
  "current_win_probability": 0.5275743348792388,
  "weighted_win_probability": 0.5270546083554819,
  "outcomes": {
    "K": {
      "probability": 0.12926217076869428,
      "win_probability": 0.5488086740566479,
      "delta_wp": 0.021234339177409134,
      "transition_level": "result+bases+outs",
      "transition_samples": 7281,
      "probability_interval_90": [
        0.11617030278565714,
        0.14235403875173144
      ]
    },
    "BB_HBP": {
      "probability": 0.09699863716366731,
      "win_probability": 0.4971901244325743,
      "delta_wp": -0.03038421044666445,
      "transition_level": "result+bases+outs",
      "transition_samples": 3641,
      "probability_interval_90": [
        0.08544950882349428,
        0.10854776550384035
      ]
    },
    "1B": {
      "probability": 0.17589746485303828,
      "win_probability": 0.49713804937731065,
      "delta_wp": -0.030436285501928118,
      "transition_level": "result+bases+outs",
      "transition_samples": 7755,
      "probability_interval_90": [
        0.1610400721164075,
        0.19075485758966906
      ]
    },
    "XBH": {
      "probability": 0.05127017620427648,
      "win_probability": 0.46361309086114244,
      "delta_wp": -0.06396124401809633,
      "transition_level": "result+bases+outs",
      "transition_samples": 1935,
      "probability_interval_90": [
        0.04266369013907447,
        0.059876662269478485
      ]
    },
    "HR": {
      "probability": 0.024955890491407028,
      "win_probability": 0.43257043587725125,
      "delta_wp": -0.09500389900198752,
      "transition_level": "result+bases+outs",
      "transition_samples": 713,
      "probability_interval_90": [
        0.018868644456210688,
        0.031043136526603368
      ]
    },
    "BIP_OUT": {
      "probability": 0.5124619365582793,
      "win_probability": 0.5490478993469763,
      "delta_wp": 0.021473564467737516,
      "transition_level": "result+bases+outs",
      "transition_samples": 20518,
      "probability_interval_90": [
        0.4929564288488906,
        0.531967444267668
      ]
    },
    "OTHER_REACH": {
      "probability": 0.009153723960637305,
      "win_probability": 0.4928557745180021,
      "delta_wp": -0.03471856036123666,
      "transition_level": "result+bases+outs",
      "transition_samples": 568,
      "probability_interval_90": [
        0.00543730869792803,
        0.01287013922334658
      ]
    }
  }
};

/** 高槓桿情境（9 局下 2 出局滿壘、主隊落後 1 分）：delta 幅度大，且 HR（樣本 41）
    的勝率低於 XBH（樣本 115）——經驗轉移核的小樣本雜訊，UI 必須揭露樣本數而非
    平滑掉這種不符直覺的排序。 */
export const FIXTURE_OK_CLUTCH: PaSimOk = {
  "available": true,
  "trained_through": 2025,
  "wp_span": "2018-2025",
  "uncertainty_method": "normal approximation over shrinkage effective sample size",
  "sample": {
    "hitter_pa": 3000,
    "pitcher_pa": 1376,
    "direct_pa": 39,
    "low_sample": false,
    "shrinkage_weight": {
      "hitter": 0.9375,
      "pitcher": 0.7747747747747747,
      "direct": 0.16317991631799164
    }
  },
  "state": {
    "inning": 9,
    "half": "2",
    "bases": "123",
    "outs": 2,
    "away_score": 3,
    "home_score": 2
  },
  "current_win_probability": 0.29693441878246374,
  "weighted_win_probability": 0.31988938179323234,
  "outcomes": {
    "K": {
      "probability": 0.12926217076869428,
      "win_probability": 0.011175993511354709,
      "delta_wp": -0.285758425271109,
      "transition_level": "result+bases+outs",
      "transition_samples": 374,
      "probability_interval_90": [
        0.11617030278565714,
        0.14235403875173144
      ]
    },
    "BB_HBP": {
      "probability": 0.09699863716366731,
      "win_probability": 0.6830021087446043,
      "delta_wp": 0.3860676899621406,
      "transition_level": "result+bases+outs",
      "transition_samples": 199,
      "probability_interval_90": [
        0.08544950882349428,
        0.10854776550384035
      ]
    },
    "1B": {
      "probability": 0.17589746485303828,
      "win_probability": 0.9341496832714733,
      "delta_wp": 0.6372152644890096,
      "transition_level": "result+bases+outs",
      "transition_samples": 306,
      "probability_interval_90": [
        0.1610400721164075,
        0.19075485758966906
      ]
    },
    "XBH": {
      "probability": 0.05127017620427648,
      "win_probability": 0.9926376465982426,
      "delta_wp": 0.6957032278157789,
      "transition_level": "result+bases+outs",
      "transition_samples": 115,
      "probability_interval_90": [
        0.04266369013907447,
        0.059876662269478485
      ]
    },
    "HR": {
      "probability": 0.024955890491407028,
      "win_probability": 0.9768131405251456,
      "delta_wp": 0.6798787217426818,
      "transition_level": "result+bases+outs",
      "transition_samples": 41,
      "probability_interval_90": [
        0.018868644456210688,
        0.031043136526603368
      ]
    },
    "BIP_OUT": {
      "probability": 0.5124619365582793,
      "win_probability": 0.010427065202068788,
      "delta_wp": -0.286507353580395,
      "transition_level": "result+bases+outs",
      "transition_samples": 961,
      "probability_interval_90": [
        0.4929564288488906,
        0.531967444267668
      ]
    },
    "OTHER_REACH": {
      "probability": 0.009153723960637305,
      "win_probability": 0.793828937181405,
      "delta_wp": 0.4968945183989413,
      "transition_level": "result+bases+outs",
      "transition_samples": 24,
      "probability_interval_90": [
        0.00543730869792803,
        0.01287013922334658
      ]
    }
  }
};

/** 打者側無樣本：估計會退化為聯盟分布 → 不得當成這兩人的機率呈現。 */
export const FIXTURE_LEAGUE_FALLBACK_HITTER: PaSimOk = {
  "available": true,
  "trained_through": 2025,
  "wp_span": "2018-2025",
  "uncertainty_method": "normal approximation over shrinkage effective sample size",
  "sample": {
    "hitter_pa": 0,
    "pitcher_pa": 1376,
    "direct_pa": 0,
    "low_sample": true,
    "shrinkage_weight": {
      "hitter": 0.0,
      "pitcher": 0.7747747747747747,
      "direct": 0.0
    }
  },
  "state": {
    "inning": 1,
    "half": "1",
    "bases": "___",
    "outs": 0,
    "away_score": 0,
    "home_score": 0
  },
  "current_win_probability": 0.5275743348792388,
  "weighted_win_probability": 0.5270546083554819,
  "outcomes": {
    "K": {
      "probability": 0.12926217076869428,
      "win_probability": 0.5488086740566479,
      "delta_wp": 0.021234339177409134,
      "transition_level": "result+bases+outs",
      "transition_samples": 7281,
      "probability_interval_90": [
        0.11617030278565714,
        0.14235403875173144
      ]
    },
    "BB_HBP": {
      "probability": 0.09699863716366731,
      "win_probability": 0.4971901244325743,
      "delta_wp": -0.03038421044666445,
      "transition_level": "result+bases+outs",
      "transition_samples": 3641,
      "probability_interval_90": [
        0.08544950882349428,
        0.10854776550384035
      ]
    },
    "1B": {
      "probability": 0.17589746485303828,
      "win_probability": 0.49713804937731065,
      "delta_wp": -0.030436285501928118,
      "transition_level": "result+bases+outs",
      "transition_samples": 7755,
      "probability_interval_90": [
        0.1610400721164075,
        0.19075485758966906
      ]
    },
    "XBH": {
      "probability": 0.05127017620427648,
      "win_probability": 0.46361309086114244,
      "delta_wp": -0.06396124401809633,
      "transition_level": "result+bases+outs",
      "transition_samples": 1935,
      "probability_interval_90": [
        0.04266369013907447,
        0.059876662269478485
      ]
    },
    "HR": {
      "probability": 0.024955890491407028,
      "win_probability": 0.43257043587725125,
      "delta_wp": -0.09500389900198752,
      "transition_level": "result+bases+outs",
      "transition_samples": 713,
      "probability_interval_90": [
        0.018868644456210688,
        0.031043136526603368
      ]
    },
    "BIP_OUT": {
      "probability": 0.5124619365582793,
      "win_probability": 0.5490478993469763,
      "delta_wp": 0.021473564467737516,
      "transition_level": "result+bases+outs",
      "transition_samples": 20518,
      "probability_interval_90": [
        0.4929564288488906,
        0.531967444267668
      ]
    },
    "OTHER_REACH": {
      "probability": 0.009153723960637305,
      "win_probability": 0.4928557745180021,
      "delta_wp": -0.03471856036123666,
      "transition_level": "result+bases+outs",
      "transition_samples": 568,
      "probability_interval_90": [
        0.00543730869792803,
        0.01287013922334658
      ]
    }
  }
};

/** 機率總和 0.887（BIP_OUT 被改小）：未過對帳，整段不顯示。 */
export const FIXTURE_SUM_MISMATCH: PaSimOk = {
  "available": true,
  "trained_through": 2025,
  "wp_span": "2018-2025",
  "uncertainty_method": "normal approximation over shrinkage effective sample size",
  "sample": {
    "hitter_pa": 3000,
    "pitcher_pa": 1376,
    "direct_pa": 39,
    "low_sample": false,
    "shrinkage_weight": {
      "hitter": 0.9375,
      "pitcher": 0.7747747747747747,
      "direct": 0.16317991631799164
    }
  },
  "state": {
    "inning": 1,
    "half": "1",
    "bases": "___",
    "outs": 0,
    "away_score": 0,
    "home_score": 0
  },
  "current_win_probability": 0.5275743348792388,
  "weighted_win_probability": 0.5270546083554819,
  "outcomes": {
    "K": {
      "probability": 0.12926217076869428,
      "win_probability": 0.5488086740566479,
      "delta_wp": 0.021234339177409134,
      "transition_level": "result+bases+outs",
      "transition_samples": 7281,
      "probability_interval_90": [
        0.11617030278565714,
        0.14235403875173144
      ]
    },
    "BB_HBP": {
      "probability": 0.09699863716366731,
      "win_probability": 0.4971901244325743,
      "delta_wp": -0.03038421044666445,
      "transition_level": "result+bases+outs",
      "transition_samples": 3641,
      "probability_interval_90": [
        0.08544950882349428,
        0.10854776550384035
      ]
    },
    "1B": {
      "probability": 0.17589746485303828,
      "win_probability": 0.49713804937731065,
      "delta_wp": -0.030436285501928118,
      "transition_level": "result+bases+outs",
      "transition_samples": 7755,
      "probability_interval_90": [
        0.1610400721164075,
        0.19075485758966906
      ]
    },
    "XBH": {
      "probability": 0.05127017620427648,
      "win_probability": 0.46361309086114244,
      "delta_wp": -0.06396124401809633,
      "transition_level": "result+bases+outs",
      "transition_samples": 1935,
      "probability_interval_90": [
        0.04266369013907447,
        0.059876662269478485
      ]
    },
    "HR": {
      "probability": 0.024955890491407028,
      "win_probability": 0.43257043587725125,
      "delta_wp": -0.09500389900198752,
      "transition_level": "result+bases+outs",
      "transition_samples": 713,
      "probability_interval_90": [
        0.018868644456210688,
        0.031043136526603368
      ]
    },
    "BIP_OUT": {
      "probability": 0.4,
      "win_probability": 0.5490478993469763,
      "delta_wp": 0.021473564467737516,
      "transition_level": "result+bases+outs",
      "transition_samples": 20518,
      "probability_interval_90": [
        0.4929564288488906,
        0.531967444267668
      ]
    },
    "OTHER_REACH": {
      "probability": 0.009153723960637305,
      "win_probability": 0.4928557745180021,
      "delta_wp": -0.03471856036123666,
      "transition_level": "result+bases+outs",
      "transition_samples": 568,
      "probability_interval_90": [
        0.00543730869792803,
        0.01287013922334658
      ]
    }
  }
};

/** 缺 HR 鍵（模擬 API 改動結果集合）：契約破損，整段不顯示。 */
export const FIXTURE_MISSING_OUTCOME = {
  "available": true,
  "trained_through": 2025,
  "wp_span": "2018-2025",
  "uncertainty_method": "normal approximation over shrinkage effective sample size",
  "sample": {
    "hitter_pa": 3000,
    "pitcher_pa": 1376,
    "direct_pa": 39,
    "low_sample": false,
    "shrinkage_weight": {
      "hitter": 0.9375,
      "pitcher": 0.7747747747747747,
      "direct": 0.16317991631799164
    }
  },
  "state": {
    "inning": 1,
    "half": "1",
    "bases": "___",
    "outs": 0,
    "away_score": 0,
    "home_score": 0
  },
  "current_win_probability": 0.5275743348792388,
  "weighted_win_probability": 0.5270546083554819,
  "outcomes": {
    "K": {
      "probability": 0.12926217076869428,
      "win_probability": 0.5488086740566479,
      "delta_wp": 0.021234339177409134,
      "transition_level": "result+bases+outs",
      "transition_samples": 7281,
      "probability_interval_90": [
        0.11617030278565714,
        0.14235403875173144
      ]
    },
    "BB_HBP": {
      "probability": 0.09699863716366731,
      "win_probability": 0.4971901244325743,
      "delta_wp": -0.03038421044666445,
      "transition_level": "result+bases+outs",
      "transition_samples": 3641,
      "probability_interval_90": [
        0.08544950882349428,
        0.10854776550384035
      ]
    },
    "1B": {
      "probability": 0.17589746485303828,
      "win_probability": 0.49713804937731065,
      "delta_wp": -0.030436285501928118,
      "transition_level": "result+bases+outs",
      "transition_samples": 7755,
      "probability_interval_90": [
        0.1610400721164075,
        0.19075485758966906
      ]
    },
    "XBH": {
      "probability": 0.05127017620427648,
      "win_probability": 0.46361309086114244,
      "delta_wp": -0.06396124401809633,
      "transition_level": "result+bases+outs",
      "transition_samples": 1935,
      "probability_interval_90": [
        0.04266369013907447,
        0.059876662269478485
      ]
    },
    "BIP_OUT": {
      "probability": 0.5124619365582793,
      "win_probability": 0.5490478993469763,
      "delta_wp": 0.021473564467737516,
      "transition_level": "result+bases+outs",
      "transition_samples": 20518,
      "probability_interval_90": [
        0.4929564288488906,
        0.531967444267668
      ]
    },
    "OTHER_REACH": {
      "probability": 0.009153723960637305,
      "win_probability": 0.4928557745180021,
      "delta_wp": -0.03471856036123666,
      "transition_level": "result+bases+outs",
      "transition_samples": 568,
      "probability_interval_90": [
        0.00543730869792803,
        0.01287013922334658
      ]
    }
  }
} as unknown as PaSimOk;

// ---- API 明示的不可用回應（一律 HTTP 200，reason 由後端給定） ----

/** artifact 未建置（`_read_pa_artifact` 檔案不存在）。 */
export const FIXTURE_ARTIFACT_ABSENT: PaSimResponse = {
  available: false,
  reason: "pa_sim artifact 未建置",
};

/** artifact 存在但損毀／契約鍵不全（ml-sim1-review P3 已修為 fail-closed）。 */
export const FIXTURE_ARTIFACT_CORRUPT: PaSimResponse = {
  available: false,
  reason: "pa_sim artifact 無法載入",
};

/** 其他明示原因（非 artifact 問題）：不可與 artifact 態共用文案。 */
export const FIXTURE_UNAVAILABLE_OTHER: PaSimResponse = {
  available: false,
  reason: "無法唯一定位完整打席",
};
