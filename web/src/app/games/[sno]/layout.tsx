import type { Metadata } from "next";
import { gameMetadata } from "@/lib/entity-metadata";

export async function generateMetadata({ params }: { params: Promise<{ sno: string }> }): Promise<Metadata> {
  return gameMetadata((await params).sno);
}

export default function GameLayout({ children }: { children: React.ReactNode }) {
  return children;
}
