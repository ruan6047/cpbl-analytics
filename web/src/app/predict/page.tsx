"use client";

import { useEffect, useMemo, useState } from "react";
import { MatchupCard } from "@/components/matchup-card";
import {
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

  const label = useMemo(() => Object.fromEntries(feats.map((f) => [f.key, f.label])), [feats]);

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

      {/* 變因開關（滑鼠移過去看說明） */}
      <section className="mb-4 flex flex-wrap gap-2">
        {feats.map((f) => {
          const on = selected.includes(f.key);
          return (
            <div key={f.key} className="group relative">
              <button
                onClick={() => toggle(f.key)}
                className={`rounded-lg border px-3 py-1.5 text-sm transition ${
                  on
                    ? "border-accent bg-ink/15 text-accent"
                    : "border-line bg-surface-2 text-faint hover:border-line"
                }`}
              >
                {on ? "✓ " : ""}
                {f.label}
              </button>
              {f.desc && (
                <span
                  role="tooltip"
                  className="pointer-events-none absolute left-1/2 top-full z-10 mt-2 w-60 -translate-x-1/2 rounded-lg border border-line bg-neutral-900 px-3 py-2 text-xs leading-relaxed text-muted opacity-0 shadow-xl transition-opacity duration-150 group-hover:opacity-100"
                >
                  {f.desc}
                </span>
              )}
            </div>
          );
        })}
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
