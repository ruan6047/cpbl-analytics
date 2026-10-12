"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { detail } from "@/lib/client";
import type { GameStatusResponse } from "@/lib/live-game";
import type { PostseasonJourney } from "@/lib/postseason-journey";
import { taipeiDate } from "@/lib/taipei-date";

export type FinalProbe = {year:number;kind:"E"|"C";sno:number;away:string;home:string};
export function confirmedFinal(status:GameStatusResponse, probe:FinalProbe):boolean {
  const s=status.live_snapshot;
  return !!s && s.game_id===`${probe.year}-${probe.kind}-${probe.sno}` && s.kind_code===probe.kind && s.game_sno===probe.sno
    && s.away.team.code===probe.away && s.home.team.code===probe.home && s.phase==="final" && status.canonical_phase==="final" && s.source_status==="ok";
}

/** 即時final只揭露正式統計延遲，絕不拿cache灌勝場或PA。 */
export function PostseasonRefreshHint({journey}:{journey:PostseasonJourney}) {
  const router=useRouter();const [lag,setLag]=useState(false);
  const asOf=[...journey.series.E.games,...journey.series.C.games].map(g=>g.date).filter((d):d is string=>!!d).sort().at(-1);
  const probes=journey.slots.filter(s=>s.status!=="final"&&s.status!=="not_needed"&&s.date<=taipeiDate()).flatMap(s=>{
    const sno=s.row?.game_sno??journey.announcement.slots.find(a=>a.key===s.key)?.officialSno;
    return sno&&s.awayCode&&s.homeCode?[{year:journey.year,kind:s.kind,sno,away:s.awayCode,home:s.homeCode}]:[];
  }).slice(-2);
  const signature=JSON.stringify(probes)+asOf;
  useEffect(()=>{
    let disposed=false;let timer:ReturnType<typeof setTimeout>|undefined;
    const check=async()=>{
      clearTimeout(timer);
      if(document.visibilityState!=="visible")return;
      const values=await Promise.allSettled(probes.map(p=>detail.gameStatus(p.sno,p.kind,p.year)));
      const positive=values.some((v,i)=>v.status==="fulfilled"&&confirmedFinal(v.value,probes[i]));
      if(disposed)return;
      setLag(positive);
      // 沿普通SSR重新取得；每頁最多兩status probes，非官源HTTP或API寫入。
      if(positive)timer=setTimeout(()=>{router.refresh();void check();},60000);
    };
    void check();document.addEventListener("visibilitychange",check);
    return()=>{disposed=true;clearTimeout(timer);document.removeEventListener("visibilitychange",check);};
  },[signature,router]); // probes身分由signature固定，不因新物件重複輪詢。
  if(!lag)return null;
  return <p role="status" className="my-3 text-sm text-muted">本系列統計{asOf?`截至 ${asOf}`:"來源時點未取得"}；最新完賽資料更新中。<button className="ml-2 inline-flex min-h-11 items-center text-accent underline" onClick={()=>router.refresh()}>重新取得正式資料</button></p>;
}
