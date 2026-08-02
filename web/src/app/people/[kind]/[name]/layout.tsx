import type { Metadata } from "next";

export async function generateMetadata({ params }: { params: Promise<{ kind: string; name: string }> }): Promise<Metadata> {
  const { kind, name } = await params;
  const role = kind === "coach" ? "教練" : kind === "umpire" ? "裁判" : "人物";
  return { title: `${decodeURIComponent(name)}｜${role}` };
}

export default function PersonLayout({ children }: { children: React.ReactNode }) {
  return children;
}
