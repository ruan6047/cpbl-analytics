/** 業務日固定台北，不隨SSR容器或瀏覽器的本機時區。 */
export function taipeiDate(now: Date | number = Date.now()): string {
  return new Intl.DateTimeFormat("sv-SE", {timeZone:"Asia/Taipei",year:"numeric",month:"2-digit",day:"2-digit"}).format(now);
}

export function nextTaipeiMidnight(now: number): number {
  const day=taipeiDate(now);
  return Date.parse(`${day}T00:00:00+08:00`)+24*60*60*1000;
}
