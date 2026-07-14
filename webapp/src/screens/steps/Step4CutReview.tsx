import { useEffect, useState } from 'react'
import { Button } from '../../components/Button'
import { StatusMessage } from '../../components/StatusMessage'
import { getCuts, toggleCut, type CutCandidate } from '../../api/client'
import { CUT_SOURCE_LABELS, formatTime } from '../../utils/formatTime'
import styles from './Step4CutReview.module.css'

interface Step4CutReviewProps {
  projectId: string
  onNext: () => void
}

/** 4단계: 자동으로 찾은 컷 후보를 검토하고, 원치 않는 컷은 켜고 끌 수 있다. */
export function Step4CutReview({ projectId, onNext }: Step4CutReviewProps) {
  const [candidates, setCandidates] = useState<CutCandidate[]>([])
  const [keptDuration, setKeptDuration] = useState(0)
  const [totalDuration, setTotalDuration] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [pendingId, setPendingId] = useState<string | null>(null)

  useEffect(() => {
    getCuts(projectId)
      .then((res) => {
        setCandidates(res.cutCandidates)
        setKeptDuration(res.keptDuration)
        setTotalDuration(res.totalDuration)
      })
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false))
  }, [projectId])

  const handleToggle = async (candidate: CutCandidate) => {
    setPendingId(candidate.id)
    try {
      const res = await toggleCut(projectId, candidate.id, !candidate.enabled)
      setCandidates(res.cutCandidates)
      setKeptDuration(res.keptDuration)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setPendingId(null)
    }
  }

  const removedPct = totalDuration > 0 ? Math.round((1 - keptDuration / totalDuration) * 100) : 0

  return (
    <div>
      <p className="screen-description">
        컷 후보 {candidates.length}개를 찾았어요. 남기고 싶은 구간은 꺼주세요.
      </p>

      {loading ? <StatusMessage variant="info">불러오는 중...</StatusMessage> : null}
      {error ? <StatusMessage variant="warning">{error}</StatusMessage> : null}

      {!loading && !error ? (
        <>
          <div className={styles.statsRow}>
            <StatusMessage variant="success">
              편집 후 {formatTime(keptDuration)} / 원본 {formatTime(totalDuration)} ({removedPct}% 제거)
            </StatusMessage>
          </div>

          <ul className={styles.list}>
            {candidates.map((c) => (
              <li key={c.id} className={styles.row}>
                <div>
                  <span className={styles.sourceTag}>{CUT_SOURCE_LABELS[c.source] ?? c.source}</span>
                  <span className={styles.timeRange}>
                    {formatTime(c.start)} - {formatTime(c.end)}
                    {c.end - c.start < 1 ? ` (${(c.end - c.start).toFixed(1)}초)` : ''}
                  </span>
                </div>
                <label className={styles.toggle}>
                  <input
                    type="checkbox"
                    checked={c.enabled}
                    disabled={pendingId === c.id}
                    onChange={() => handleToggle(c)}
                    aria-label={`${formatTime(c.start)}부터 ${formatTime(c.end)}까지 컷 ${c.enabled ? '끄기' : '켜기'}`}
                  />
                  <span>{c.enabled ? '컷함' : '유지'}</span>
                </label>
              </li>
            ))}
            {candidates.length === 0 ? <li className={styles.empty}>찾은 컷 후보가 없어요.</li> : null}
          </ul>
        </>
      ) : null}

      <Button onClick={onNext} className={styles.nextButton}>
        다음
      </Button>
    </div>
  )
}
