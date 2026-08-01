import type { Metadata } from "next";
import { gameMetadata } from "@/lib/entity-metadata";
import GameLivePage from "./game-live-page";

export async function generateMetadata({
  params,
  searchParams,
}: {
  params: Promise<{ sno: string }>;
  searchParams: Promise<{ kind?: string; year?: string }>;
}): Promise<Metadata> {
  return gameMetadata((await params).sno, await searchParams);
}

export default function GamePage() {
  return <GameLivePage />;
}
