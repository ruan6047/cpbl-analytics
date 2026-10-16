import { legacyPlayoffsLocation } from "@/lib/playoffs-selection";

export const dynamic = "force-dynamic";

export async function GET(request: Request, { params }: { params: Promise<{ sno: string }> }) {
  const { sno } = await params;
  return new Response(null, { status: 307, headers: {
    Location: legacyPlayoffsLocation(sno, new URL(request.url).searchParams),
    "Cache-Control": "no-store",
  } });
}
