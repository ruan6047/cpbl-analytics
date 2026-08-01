import type { Metadata } from "next";
import { playerMetadata } from "@/lib/entity-metadata";

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }): Promise<Metadata> {
  return playerMetadata((await params).id);
}

export default function PlayerLayout({ children }: { children: React.ReactNode }) {
  return children;
}
