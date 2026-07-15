/** 초 단위 시간을 "0:05" 같은 mm:ss 형태로 표시한다. */
export function formatTime(totalSeconds: number): string {
  const safe = Math.max(0, totalSeconds)
  const minutes = Math.floor(safe / 60)
  const seconds = Math.floor(safe % 60)
  return `${minutes}:${String(seconds).padStart(2, '0')}`
}

export const CUT_SOURCE_LABELS: Record<string, string> = {
  silence: '무음',
  filler: '필러워드',
  repetition: '반복(말더듬)',
}
