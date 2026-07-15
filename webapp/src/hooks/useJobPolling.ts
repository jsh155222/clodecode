import { useCallback, useEffect, useRef, useState } from 'react'
import type { JobStatus } from '../api/client'

interface UseJobPollingResult<T extends JobStatus> {
  data: T | null
  error: string | null
  isPolling: boolean
  start: () => Promise<void>
}

/**
 * "POST로 작업 시작 -> GET으로 상태 폴링" 패턴(analyze/correction/audio/export 공용)을
 * 감싸는 훅. startFn이 성공하면 pollFn을 일정 간격으로 호출하다가 status가
 * running이 아니게 되면 멈춘다.
 */
export function useJobPolling<T extends JobStatus>(
  startFn: () => Promise<unknown>,
  pollFn: () => Promise<T>,
  intervalMs = 700,
): UseJobPollingResult<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isPolling, setIsPolling] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  const poll = useCallback(async () => {
    try {
      const result = await pollFn();
      if (!mountedRef.current) return;
      setData(result);
      if (result.status === 'running') {
        timerRef.current = setTimeout(poll, intervalMs);
      } else {
        setIsPolling(false);
        if (result.status === 'error') {
          setError(result.error ?? '알 수 없는 오류가 발생했습니다.');
        }
      }
    } catch (err) {
      if (!mountedRef.current) return;
      setIsPolling(false);
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [pollFn, intervalMs]);

  const start = useCallback(async () => {
    setError(null);
    setIsPolling(true);
    try {
      await startFn();
      await poll();
    } catch (err) {
      if (!mountedRef.current) return;
      setIsPolling(false);
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [startFn, poll]);

  return { data, error, isPolling, start };
}
