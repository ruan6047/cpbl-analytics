import { type Col } from "@/components/leaderboard";

type Role = "batting" | "pitching";

// 投打對決：role=batting → 列出對戰的投手；pitching → 列出對戰的打者
export function matchupCols(role: Role): Col[] {
  const opp = role === "batting" ? "投手" : "打者";
  return [
    { key: "opp_name", label: opp, tip: `對戰${opp}（點擊看個人頁）`, link: { base: "/players/", idKey: "opp_id" } },
    { key: "opp_team", label: "對手隊", tone: "dim", tip: "對手所屬球隊（同隊不對戰，已自然排除）" },
    { key: "plate_appearances", label: "打席", fmt: "i", bar: true, tip: "對戰打席（PA）" },
    { key: "at_bats", label: "打數", fmt: "i", tone: "dim", tip: "打數（AB）" },
    { key: "hits", label: "安打", fmt: "i", tip: role === "batting" ? "安打" : "被安打" },
    { key: "home_runs", label: "全壘打", fmt: "i", tip: role === "batting" ? "全壘打" : "被全壘打" },
    { key: "bb", label: "四壞", fmt: "i", tone: "dim", tip: "四壞球（保送）" },
    { key: "so", label: "三振", fmt: "i", tone: "dim", tip: role === "batting" ? "被三振" : "奪三振" },
    { key: "avg", label: "打擊率", fmt: "f3", bar: true, lowerBetter: role === "pitching", tip: role === "batting" ? "打擊率" : "被打擊率" },
    { key: "obp", label: "上壘率", fmt: "f3", bar: true, lowerBetter: role === "pitching", tip: "上壘率" },
    { key: "slg", label: "長打率", fmt: "f3", bar: true, lowerBetter: role === "pitching", tip: "長打率" },
    { key: "ops", label: "OPS", fmt: "f3", bar: true, lowerBetter: role === "pitching", tone: "accent", tip: "OPS = 上壘率＋長打率" },
    { key: "whiff_pct", label: "揮空%", fmt: "f1", tone: "dim", tip: "揮空率：揮棒落空 ÷ 揮棒" },
  ];
}

// 對戰各隊
export function vsTeamCols(role: Role): Col[] {
  if (role === "batting")
    return [
      { key: "fight_team_name", label: "對手隊", tip: "對戰的對手球隊" },
      { key: "total_games", label: "出賽", fmt: "i", tone: "dim", tip: "對戰場數" },
      { key: "plate_appearances", label: "打席", fmt: "i", tip: "打席（PA）" },
      { key: "at_bats", label: "打數", fmt: "i", tone: "dim", tip: "打數（AB）" },
      { key: "hits", label: "安打", fmt: "i", tip: "安打" },
      { key: "home_runs", label: "全壘打", fmt: "i", tip: "全壘打" },
      { key: "rbi", label: "打點", fmt: "i", tip: "打點" },
      { key: "bb", label: "四壞", fmt: "i", tone: "dim", tip: "四壞球" },
      { key: "so", label: "三振", fmt: "i", tone: "dim", tip: "被三振" },
      { key: "avg", label: "打擊率", fmt: "f3", tip: "打擊率" },
      { key: "obp", label: "上壘率", fmt: "f3", tip: "上壘率" },
      { key: "slg", label: "長打率", fmt: "f3", tip: "長打率" },
      { key: "ops", label: "OPS", fmt: "f3", tone: "accent", tip: "OPS" },
    ];
  return [
    { key: "fight_team_name", label: "對手隊", tip: "對戰的對手球隊" },
    { key: "total_games", label: "出賽", fmt: "i", tone: "dim", tip: "對戰場數" },
    { key: "starts", label: "先發", fmt: "i", tone: "dim", tip: "先發場數" },
    { key: "wins", label: "勝", fmt: "i", tip: "勝場" },
    { key: "loses", label: "敗", fmt: "i", tip: "敗場" },
    { key: "save_ok", label: "救援", fmt: "i", tip: "救援成功" },
    { key: "inning_pitched_cnt", label: "局數", fmt: "i", tip: "投球局數（整數部分）" },
    { key: "era", label: "防禦率", fmt: "f2", tone: "accent", tip: "防禦率 ERA" },
    { key: "whip", label: "WHIP", fmt: "f2", tip: "每局被上壘率" },
    { key: "hits", label: "被安", fmt: "i", tone: "dim", tip: "被安打" },
    { key: "home_runs", label: "被轟", fmt: "i", tone: "dim", tip: "被全壘打" },
    { key: "bb", label: "四壞", fmt: "i", tone: "dim", tip: "投出四壞" },
    { key: "so", label: "三振", fmt: "i", tip: "奪三振" },
    { key: "earned_runs", label: "自責", fmt: "i", tone: "warn", tip: "自責分" },
  ];
}
