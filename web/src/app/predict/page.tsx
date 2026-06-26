"use client";

import { useEffect, useMemo, useState } from "react";
import { MatchupCard } from "@/components/matchup-card";
import {
  type Backtest,
  clientGet,
  type FeatureMeta,
  type Matchup,
  type MatchupsResponse,
  type OutcomeModel,
  type SimulateResponse,
  type Team,
} from "@/lib/client";

type Mode = "upcoming" | "simulate";
const DEFAULT_SELECTED = [
  "winrate_diff",
  "prior_winpct_diff",
  "runs_scored_diff",
  "runs_allowed_diff",
  "recent_form_diff",
  "h2h_home",
  "starter_era_diff",
  "home_field",
];

export default function PredictPage() {
  const [feats, setFeats] = useState<FeatureMeta[]>([]);
  const [teams, setTeams] = useState<Team[]>([]);
  const [selected, setSelected] = useState<string[]>(DEFAULT_SELECTED);
  const [mode, setMode] = useState<Mode>("upcoming");

  const [model, setModel] = useState<OutcomeModel | null>(null);
  const [weights, setWeights] = useState<Record<string, number>>({});
  const [items, setItems] = useState<Matchup[]>([]);
  const [sim, setSim] = useState<Matchup | null>(null);
  const [home, setHome] = useState("");
  const [away, setAway] = useState("");
  const [loading, setLoading] = useState(false);
  const [backtest, setBacktest] = useState<Backtest | null>(null);
  const [activeGroup, setActiveGroup] = useState<string>("");

  const label = useMemo(() => Object.fromEntries(feats.map((f) => [f.key, f.label])), [feats]);
  // 依群組分區（保留後端順序）
  const groups = useMemo(() => {
    const m = new Map<string, FeatureMeta[]>();
    for (const f of feats) {
      const g = f.group ?? "其他";
      (m.get(g) ?? m.set(g, []).get(g)!).push(f);
    }
    return [...m.entries()];
  }, [feats]);
  // 共線軟提醒：已選特徵中，同一 corr 群組被選了 ≥2 個 → 列出該群組名稱
  const corrWarn = useMemo(() => {
    const byCorr = new Map<string, string[]>();
    for (const f of feats) {
      if (f.corr && selected.includes(f.key)) (byCorr.get(f.corr) ?? byCorr.set(f.corr, []).get(f.corr)!).push(f.label);
    }
    return [...byCorr.entries()].filter(([, v]) => v.length >= 2);
  }, [feats, selected]);

  useEffect(() => {
    clientGet<{ features: FeatureMeta[] }>("/api/v1/outcome/features").then((d) =>
      setFeats(d.features),
    );
    clientGet<{ teams: Team[] }>("/api/v1/outcome/teams").then((d) => {
      setTeams(d.teams);
      if (d.teams.length >= 2) {
        setHome(d.teams[0].code);
        setAway(d.teams[1].code);
      }
    });
    clientGet<Backtest>("/api/v1/outcome/backtest").then(setBacktest).catch(() => {});
  }, []);

  useEffect(() => {
    const q = selected.join(",");
    if (selected.length === 0) return;
    setLoading(true);
    if (mode === "upcoming") {
      clientGet<MatchupsResponse>(`/api/v1/outcome/matchups?features=${q}&limit=12`)
        .then((d) => {
          setModel(d.model);
          setWeights(d.model.weights);
          setItems(d.items);
        })
        .finally(() => setLoading(false));
    } else if (home && away && home !== away) {
      clientGet<SimulateResponse>(`/api/v1/outcome/simulate?home=${home}&away=${away}&features=${q}`)
        .then((d) => {
          setModel(d.model);
          setWeights(d.model.weights);
          setSim(d.matchup);
        })
        .finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, [selected, mode, home, away]);

  const toggle = (k: string) =>
    setSelected((s) => (s.includes(k) ? s.filter((x) => x !== k) : [...s, k]));

  return (
    <div>
      <header className="mb-5">
        <h1 className="text-2xl font-bold">賽事預測 · 單場對戰</h1>
        <p className="mt-2 text-sm text-muted">
          勾選你在意的變因,把雙方真實數字攤開比較;勝率用歷史學出的「預設權重」起算,
          你也能拖滑桿手動微調(拖大 = 更決斷)。
          {model && (
            <span className="ml-1 text-muted">
              模型參考準確率 {(model.accuracy * 100).toFixed(1)}%(基準{" "}
              {(model.baseline * 100).toFixed(1)}%)。
            </span>
          )}
        </p>
      </header>

      {backtest?.available && <BacktestPanel bt={backtest} />}

      {/* 模式切換 */}
      <div className="mb-4 inline-flex rounded-lg border border-line p-1 text-sm">
        {(["upcoming", "simulate"] as Mode[]).map((mo) => (
          <button
            key={mo}
            onClick={() => setMode(mo)}
            className={`rounded-md px-3 py-1.5 transition ${
              mode === mo ? "bg-ink text-white" : "text-muted hover:text-white"
            }`}
          >
            {mo === "upcoming" ? "今日/近期賽事" : "任選兩隊模擬"}
          </button>
        ))}
      </div>

      {/* 變因開關（標籤頁：一次只顯示一個群組；滑鼠移過去看說明） */}
      <section className="mb-4">
        {(() => {
          const cur = activeGroup || (groups[0]?.[0] ?? "");
          const curFeats = groups.find(([g]) => g === cur)?.[1] ?? [];
          return (
            <>
              {/* 群組標籤列 */}
              <div className="mb-3 flex flex-wrap gap-1.5 border-b border-line pb-2">
                {groups.map(([gname, gfeats]) => {
                  const nSel = gfeats.filter((f) => selected.includes(f.key)).length;
                  const on = gname === cur;
                  return (
                    <button key={gname} onClick={() => setActiveGroup(gname)}
                      className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition ${
                        on ? "bg-ink text-white" : "bg-surface-2 text-muted hover:text-ink"}`}>
                      {gname}
                      {nSel > 0 && (
                        <span className={`rounded px-1 text-[10px] font-bold ${on ? "bg-white/25" : "bg-accent/15 text-accent"}`}>{nSel}</span>
                      )}
                    </button>
                  );
                })}
              </div>
              {/* 當前群組的特徵 */}
              <div className="flex flex-wrap gap-2">
                {curFeats.map((f) => {
                  const on = selected.includes(f.key);
                  return (
                    <div key={f.key} className="group relative">
                      <button onClick={() => toggle(f.key)}
                        className={`rounded-lg border px-3 py-1.5 text-sm transition ${
                          on ? "border-accent bg-ink/15 text-accent"
                            : "border-line bg-surface-2 text-faint hover:border-line"}`}>
                        {on ? "✓ " : ""}
                        {f.label}
                      </button>
                      {f.desc && (
                        <span role="tooltip"
                          className="pointer-events-none absolute left-1/2 top-full z-10 mt-2 w-60 -translate-x-1/2 rounded-lg border border-line bg-neutral-900 px-3 py-2 text-xs leading-relaxed text-muted opacity-0 shadow-xl transition-opacity duration-150 group-hover:opacity-100">
                          {f.desc}
                        </span>
                      )}
                    </div>
                  );
                })}
              </div>
            </>
          );
        })()}
        {corrWarn.length > 0 && (
          <div className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-800">
            ⚠ 相依提醒：{corrWarn.map(([g, labels]) => `「${g}」(${labels.join("、")})`).join("；")}
            互相高度相關，同時選用屬重複訊號——模型已自動分攤權重，但解讀影響力時請留意可擇一即可。
          </div>
        )}
      </section>

      {/* 權重滑桿 */}
      {selected.length > 0 && (
        <section className="mb-6 rounded-xl border border-line p-4">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-medium text-muted">變因權重(影響力)</h2>
            <button
              onClick={() => model && setWeights(model.weights)}
              className="text-xs text-faint hover:text-accent"
            >
              重設為預設
            </button>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            {selected.map((k) => (
              <label key={k} className="flex items-center gap-3 text-sm">
                <span className="w-24 shrink-0 text-muted">{label[k] ?? k}</span>
                <input
                  type="range"
                  min={0}
                  max={1}
                  step={0.02}
                  value={weights[k] ?? 0}
                  onChange={(e) =>
                    setWeights((w) => ({ ...w, [k]: parseFloat(e.target.value) }))
                  }
                  className="flex-1 accent-accent"
                />
                <span className="w-10 text-right font-mono text-xs text-faint">
                  {(weights[k] ?? 0).toFixed(2)}
                </span>
              </label>
            ))}
          </div>
        </section>
      )}

      {/* 任選兩隊：下拉選 */}
      {mode === "simulate" && (
        <section className="mb-4 flex flex-wrap items-center gap-3 text-sm">
          <TeamSelect label="客隊" teams={teams} value={away} onChange={setAway} />
          <span className="text-faint">@</span>
          <TeamSelect label="主隊" teams={teams} value={home} onChange={setHome} />
        </section>
      )}

      {/* 卡片 */}
      <section className="space-y-2">
        {loading && <p className="text-sm text-faint">計算中…</p>}
        {!loading && mode === "upcoming" &&
          (items.length === 0 ? (
            <p className="text-sm text-faint">目前無未開打場次(休賽期或賽季結束)。</p>
          ) : (
            items.map((m, i) => <MatchupCard key={i} m={m} weights={weights} />)
          ))}
        {!loading && mode === "simulate" && sim && <MatchupCard m={sim} weights={weights} />}
      </section>
    </div>
  );
}

// 模型回測面板：誠實展示「全特徵模型」相對「無腦全押主場」的走查回測準確率。
// 重點在透明與教育（單場勝負天花板 ~60%），不在擊敗賭盤。
function BacktestPanel({ bt }: { bt: Backtest }) {
  const [open, setOpen] = useState(false);
  const models = bt.models ?? [];
  const baseAcc = models.find((m) => m.name === "全押主場")?.accuracy ?? 0.5;
  const bestAcc = Math.max(...models.filter((m) => m.name !== "全押主場").map((m) => m.accuracy), 0);
  const seasons = (bt.test_seasons ?? []).filter((s): s is number => s != null);
  const span = seasons.length ? `${seasons[0]}–${seasons[seasons.length - 1]}` : "—";
  const max = Math.max(...models.map((m) => m.accuracy), 0.6);
  return (
    <section className="mb-6 rounded-xl border border-line bg-surface p-4">
      <button onClick={() => setOpen((o) => !o)} className="flex w-full items-center justify-between text-left">
        <div>
          <h2 className="text-sm font-semibold text-ink">模型回測 · 全特徵 vs 全押主場</h2>
          <p className="mt-0.5 text-[11px] text-faint">
            走查回測 {span} 季共 {bt.n_test} 場（每季僅用過去資料預測）。
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className="font-mono text-lg font-bold tabular-nums text-accent">
            {(bestAcc * 100).toFixed(1)}%
          </span>
          <span className="text-xs text-faint">{open ? "▲" : "▼"}</span>
        </div>
      </button>

      <div className="mt-3 space-y-1.5">
        {models.map((m) => {
          const win = m.name !== "全押主場" && m.accuracy > baseAcc;
          return (
            <div key={m.name} className="flex items-center gap-2 text-xs">
              <span className="w-32 shrink-0 text-muted">{m.name}</span>
              <div className="relative h-4 flex-1 overflow-hidden rounded bg-surface-2">
                <div
                  className={`h-full rounded ${m.name === "全押主場" ? "bg-faint/40" : "bg-accent"}`}
                  style={{ width: `${(m.accuracy / max) * 100}%` }}
                />
              </div>
              <span className="w-12 shrink-0 text-right font-mono tabular-nums text-ink">
                {(m.accuracy * 100).toFixed(1)}%
              </span>
              {win && <span className="w-4 text-up">✓</span>}
              {m.name === "全押主場" && <span className="w-4" />}
            </div>
          );
        })}
      </div>

      {open && (
        <div className="mt-4 border-t border-line pt-3">
          <p className="mb-2 text-[11px] leading-relaxed text-muted">
            單場勝負的可預測性天花板約 6 成，產品價值在「把雙方數字攤開、讓你理解為何看好某隊」，
            而非擊敗賭盤。下表為 LightGBM 的特徵重要度（分裂增益），越高代表模型越倚重該變因。
          </p>
          <div className="grid grid-cols-2 gap-x-6 gap-y-1 sm:grid-cols-3">
            {(bt.importance ?? []).map((f) => (
              <div key={f.key} className="flex items-center justify-between text-[11px]">
                <span className="text-muted">{f.label}</span>
                <span className="font-mono tabular-nums text-faint">{f.gain}</span>
              </div>
            ))}
          </div>
          <p className="mt-3 text-[10px] text-faint">
            Brier / LogLoss（越低越準）：
            {models.map((m) => ` ${m.name} ${m.brier}/${m.log_loss}；`)}
          </p>
        </div>
      )}
    </section>
  );
}

function TeamSelect({
  label,
  teams,
  value,
  onChange,
}: {
  label: string;
  teams: Team[];
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <label className="flex items-center gap-2">
      <span className="text-faint">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-lg border border-line bg-surface-2 px-3 py-1.5 text-white"
      >
        {teams.map((t) => (
          <option key={t.code} value={t.code} className="bg-neutral-900">
            {t.name}
          </option>
        ))}
      </select>
    </label>
  );
}
