import { useEffect, useRef } from 'react'
import { Button } from '../../components/Button'
import { StatusMessage } from '../../components/StatusMessage'
import { getAnalyzeStatus, startAnalyze, type AnalyzeStatus } from '../../api/client'
import { useJobPolling } from '../../hooks/useJobPolling'
import styles from './StepCommon.module.css'

interface Step3AnalyzeProps {
  projectId: string
  onNext: (result: AnalyzeStatus) => void
}

/** 3단계: 무음/필러워드/말더듬 구간을 실제 백엔드에서 자동 분석한다. */
export function Step3Analyze({ projectId, onNext }: Step3AnalyzeProps) {
  const { data, error, isPolling, start } = useJobPolling(
    () => startAnalyze(projectId),
    () => getAnalyzeStatus(projectId),
  )
  const startedRef = useRef(false)

  useEffect(() => {
    if (startedRef.current) return
    startedRef.current = true
    start()
  }, [start])

  const removedPct =
    data?.status === 'done' && data.totalDuration
      ? Math.round((1 - (data.keptDuration ?? data.totalDuration) / data.totalDuration) * 100)
      : null

  return (
    <div>
      <p className="screen-description">무음, 필러워드, 말더듬 구간을 자동으로 찾고 있어요.</p>

      {isPolling && data?.status !== 'done' ? (
        <div className={styles.body}>
          <StatusMessage variant="info">
            {data?.log?.[data.log.length - 1] ?? '분석을 준비하고 있습니다...'}
          </StatusMessage>
        </div>
      ) : null}

      {error ? (
        <div className={styles.body}>
          <StatusMessage variant="warning">{error}</StatusMessage>
          <Button variant="secondary" onClick={start} style={{ marginTop: 12 }}>
            다시 시도
          </Button>
        </div>
      ) : null}

      {data?.status === 'done' ? (
        <div className={styles.body}>
          <StatusMessage variant="success">
            분석 완료 — 컷 후보 {data.cutCandidates?.length ?? 0}개, 자막 {data.subtitleLines?.length ?? 0}줄
            {removedPct !== null ? ` (전체의 약 ${removedPct}% 제거 예정)` : ''}
          </StatusMessage>
        </div>
      ) : null}

      <Button onClick={() => data && onNext(data)} disabled={data?.status !== 'done'} className={styles.nextButton}>
        다음
      </Button>
    </div>
  )
}
