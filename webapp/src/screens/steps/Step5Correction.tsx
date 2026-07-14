import { useState } from 'react'
import { Button } from '../../components/Button'
import { StatusMessage } from '../../components/StatusMessage'
import { getCorrectionStatus, startCorrection } from '../../api/client'
import { useJobPolling } from '../../hooks/useJobPolling'
import placeholderStyles from './StepCommon.module.css'
import styles from './Step5Correction.module.css'

interface Step5CorrectionProps {
  projectId: string
  onNext: () => void
}

/** 5단계: 밝기/대비 자동 보정 + 흔들림 안정화 (ffmpeg 고전 영상처리, AI 색보정 아님). */
export function Step5Correction({ projectId, onNext }: Step5CorrectionProps) {
  const [stabilize, setStabilize] = useState(true)
  const { data, error, isPolling, start } = useJobPolling(
    () => startCorrection(projectId, stabilize),
    () => getCorrectionStatus(projectId),
  )

  return (
    <div>
      <p className="screen-description">밝기/대비를 자동으로 맞추고, 필요하면 흔들림을 줄여드려요.</p>

      <label className={styles.checkboxRow}>
        <input
          type="checkbox"
          checked={stabilize}
          disabled={isPolling}
          onChange={(e) => setStabilize(e.target.checked)}
        />
        흔들림 안정화도 함께 적용
      </label>

      {!data && !isPolling ? (
        <Button onClick={start} className={placeholderStyles.nextButton}>
          화면 보정 시작
        </Button>
      ) : null}

      {isPolling ? (
        <div className={placeholderStyles.body}>
          <StatusMessage variant="info">보정 처리 중입니다...</StatusMessage>
        </div>
      ) : null}

      {error ? (
        <div className={placeholderStyles.body}>
          <StatusMessage variant="warning">{error}</StatusMessage>
          <Button variant="secondary" onClick={start}>
            다시 시도
          </Button>
        </div>
      ) : null}

      {data?.status === 'done' ? (
        <div className={placeholderStyles.body}>
          <StatusMessage variant="success">
            보정 완료 — 밝기 {data.brightness && data.brightness > 0 ? '+' : ''}
            {data.brightness?.toFixed(2)}, 대비 {data.contrast?.toFixed(2)}배
            {data.stabilized ? ', 흔들림 안정화 적용됨' : ''}
          </StatusMessage>
        </div>
      ) : null}

      <Button onClick={onNext} disabled={data?.status !== 'done'} className={placeholderStyles.nextButton}>
        다음
      </Button>
    </div>
  )
}
