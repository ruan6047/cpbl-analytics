"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

type Point = { year: number; avg: number | null };

export function OpsChart({ data }: { data: Point[] }) {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <LineChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: -8 }}>
        <CartesianGrid stroke="#ffffff10" />
        <XAxis dataKey="year" stroke="#ffffff40" fontSize={12} />
        <YAxis stroke="#ffffff40" fontSize={12} domain={["auto", "auto"]} />
        <Tooltip
          contentStyle={{ background: "#18181b", border: "1px solid #ffffff20", borderRadius: 8 }}
          labelStyle={{ color: "#a1a1aa" }}
        />
        <Line type="monotone" dataKey="avg" stroke="#34d399" strokeWidth={2} dot={{ r: 3 }} />
      </LineChart>
    </ResponsiveContainer>
  );
}
