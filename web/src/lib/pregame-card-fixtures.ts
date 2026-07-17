// PregameCard 五態 fixture（UX-OUTCOME-HOME 驗收條件 2）。
// 供 (1) pregame-card.test.ts 契約測試、(2) /dev/pregame-card 走查頁、
// (3) UX-GAME-HOME1 整合測試共用；payload 形狀鏡射真實 API，勿手改成理想化資料。

import type {
  PregameGameRef,
  PregameResponse,
  ResolvePregameInput,
} from "./pregame-card.ts";

const GAME_A: PregameGameRef = { season: 2026, game_sno: 198, kind_code: "A" };

/** available：模型可用且該場有預測（訊號含缺值，驗證主訊號退位規則）。 */
export const FIXTURE_AVAILABLE: ResolvePregameInput = {
  game: GAME_A,
  response: {
    available: true,
    trained_through: 2025,
    signals: {
      strength: "winrate_diff",
      offense: "team_ops_now_diff",
      suppression: "starter_era_diff",
      schedule: "rest_days_diff",
    },
    items: [
      {
        season: 2026,
        game_sno: 198,
        game_date: "2026-07-17",
        home: "樂天桃猿",
        away: "中信兄弟",
        home_win_probability: 0.617,
        model_interval_90: [0.541, 0.688],
        signals: {
          strength: {
            key: "winrate_diff",
            raw: 0.058,
            direction: "higher_favors_home",
          },
          offense: {
            key: "team_ops_now_diff",
            raw: -0.021,
            direction: "higher_favors_home",
          },
          suppression: {
            key: "starter_era_diff",
            raw: -0.84,
            direction: "lower_favors_home",
          },
          schedule: {
            key: "rest_days_diff",
            raw: 0,
            direction: "higher_favors_home",
          },
        },
      },
    ],
  },
};

/** available 變體：suppression 缺值（先發未公布），主訊號應退位到 strength。 */
export const FIXTURE_AVAILABLE_NO_STARTER: ResolvePregameInput = {
  game: { season: 2026, game_sno: 199, kind_code: "A" },
  response: {
    ...FIXTURE_AVAILABLE.response!,
    items: [
      {
        ...FIXTURE_AVAILABLE.response!.items![0],
        game_sno: 199,
        home_win_probability: 0.483,
        model_interval_90: [0.404, 0.556],
        signals: {
          ...FIXTURE_AVAILABLE.response!.items![0].signals,
          suppression: {
            key: "starter_era_diff",
            raw: null,
            direction: "lower_favors_home",
          },
        },
      },
    ],
  },
};

/** artifact missing：後端回 available=false（outcome_simple artifact 未建置）。 */
export const FIXTURE_ARTIFACT_MISSING: ResolvePregameInput = {
  game: GAME_A,
  response: { available: false, reason: "outcome_simple artifact 未建置" },
};

/** unsupported：二軍（kind D）等模型範圍外賽別；response 正常也不得渲染機率。 */
export const FIXTURE_UNSUPPORTED: ResolvePregameInput = {
  game: { season: 2026, game_sno: 42, kind_code: "D" },
  response: FIXTURE_AVAILABLE.response,
};

/** pending：模型可用但該場尚無預測（特徵未建／賽程剛排定）。 */
export const FIXTURE_PENDING: ResolvePregameInput = {
  game: { season: 2026, game_sno: 205, kind_code: "A" },
  response: {
    available: true,
    trained_through: 2025,
    signals: FIXTURE_AVAILABLE.response!.signals,
    items: FIXTURE_AVAILABLE.response!.items,
  },
};

/** error：fetch 失敗（網路／5xx）；消費端傳 fetchFailed，不阻塞外層賽程卡。 */
export const FIXTURE_ERROR: ResolvePregameInput = {
  game: GAME_A,
  response: null,
  fetchFailed: true,
};

export const PREGAME_FIXTURES = {
  available: FIXTURE_AVAILABLE,
  available_no_starter: FIXTURE_AVAILABLE_NO_STARTER,
  artifact_missing: FIXTURE_ARTIFACT_MISSING,
  unsupported: FIXTURE_UNSUPPORTED,
  pending: FIXTURE_PENDING,
  error: FIXTURE_ERROR,
} as const;

export type PregameFixtureName = keyof typeof PREGAME_FIXTURES;
