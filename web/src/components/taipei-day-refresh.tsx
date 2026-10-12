"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { nextTaipeiMidnight, taipeiDate } from "@/lib/taipei-date";

/** 只在台北換日或背景頁重新可見時刷新SSR，不增加官源採集頻率。 */
export function TaipeiDayRefresh({ day }: { day: string }) {
  const router=useRouter();
  useEffect(()=>{
    let timer:ReturnType<typeof setTimeout>;
    const check=()=>{
      const now=Date.now();
      if(taipeiDate(now)!==day) router.refresh();
      clearTimeout(timer);
      timer=setTimeout(check,nextTaipeiMidnight(now)-now+1000);
    };
    const visible=()=>{if(document.visibilityState==="visible")check();};
    check();document.addEventListener("visibilitychange",visible);
    return()=>{clearTimeout(timer);document.removeEventListener("visibilitychange",visible);};
  },[day,router]);
  return null;
}
