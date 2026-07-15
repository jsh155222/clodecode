import { useEffect, useState } from 'react'
import { Button } from '../../components/Button'
import { StatusMessage } from '../../components/StatusMessage'
import {
  getCorrectionStatus,
  getReframeSuggestion,
  reframePreviewUrl,
  startCorrection,
  updateReframeApproval,
  type ReframeSuggestionDto,
} from '../../api/client'
import { useJobPolling } from '../../hooks/useJobPolling'
import placeholderStyles from './StepCommon.module.css'
import styles from './Step5Correction.module.css'

interface Step5CorrectionProps {
  projectId: string
  onNext: () => void
}

/** 5단계: 밝기/대비 자동 보정 + 흔들림 안정화(ffmpeg 고전 영상처리) + 9:16 자동 리프레이밍. */
export function Step5Correction({ projectId, onNext }: Step5CorrectionProps) {
  const [stabilize, setStabilize] = useState(true)
  const [reframe, setReframe] = useState<ReframeSuggestionDto | null>(null)
  const [reframeLoading, setReframeLoading] = useState(true)
  const [reframeApproved, setReframeApproved] = useState(false)

  const { data, error, isPolling, start } = useJobPolling(
    () => startCorrection(projectId, stabilize),
    () => getCorrectionStatus(projectId),
  )

  useEffect(() => {
    getReframeSuggestion(projectId)
      .then((res) => {
        setReframe(res)
        setReframeApproved(res.approved)
      })
      .catch(() => setReframe(null))
      .finally(() => setReframeLoading(false))
  }, [projectId])

  async function handleToggleReframe(checked: boolean) {
    setReframeApproved(checked)
    await updateReframeApproval(projectId, checked)
  }

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

      <h2 className={styles.sectionTitle}>9:16 자동 리프레이밍</h2>
      {reframeLoading ? <StatusMessage variant="info">화면 구도를 분석하는 중입니다...</StatusMessage> : null}
      {!reframeLoading && reframe ? (
        <div className={styles.reframeBox}>
          <img
            src={reframePreviewUrl(reframe.previewUrl)}
            alt="9:16로 자른 미리보기"
            className={styles.reframePreviewImage}
          />
          <div className={styles.reframeInfo}>
            <p className={styles.reframeHint}>
              {reframe.faceDetected ? '얼굴을 감지해 화면에 맞게 확대/이동했어요.' : '피사체를 특정하지 못해 화면 중앙을 기준으로 잘랐어요.'}
              {' '}(확대 {reframe.crop.zoom.toFixed(2)}배)
            </p>
            {!reframe.crop.subjectFullyContained ? (
              <p className={styles.reframeWarning}>피사체가 커서 화면 안에 전부 담기지 않을 수 있어요.</p>
            ) : null}
            <label className={styles.checkboxRow}>
              <input
                type="checkbox"
                checked={reframeApproved}
                disabled={isPolling}
                onChange={(e) => handleToggleReframe(e.target.checked)}
              />
              이 구도로 9:16 리프레이밍 적용
            </label>
          </div>
        </div>
      ) : null}
      {!reframeLoading && !reframe ? (
        <StatusMessage variant="warning">화면 구도를 분석하지 못했어요. 원본 비율 그대로 진행됩니다.</StatusMessage>
      ) : null}

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
