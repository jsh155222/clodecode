import { useEffect, useState } from 'react'
import { Button } from '../../components/Button'
import { StatusMessage } from '../../components/StatusMessage'
import { getSummary, type ProjectSummary } from '../../api/client'
import { formatTime } from '../../utils/formatTime'
import placeholderStyles from './StepCommon.module.css'
import styles from './Step8Confirm.module.css'

interface Step8ConfirmProps {
  projectId: string
  onNext: () => void
}

/** 8단계: 지금까지의 편집 선택을 한 번에 확인한다. */
export function Step8Confirm({ projectId, onNext }: Step8ConfirmProps) {
  const [summary, setSummary] = useState<ProjectSummary | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getSummary(projectId)
      .then(setSummary)
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
  }, [projectId])

  if (error) {
    return (
      <div>
        <StatusMessage variant="warning">{error}</StatusMessage>
      </div>
    )
  }

  if (!summary) {
    return <StatusMessage variant="info">불러오는 중...</StatusMessage>
  }

  const rows: [string, string][] = [
    ['카테고리', summary.categoryLabel ?? '미선택'],
    [
      '길이',
      summary.totalDuration != null && summary.keptDuration != null
        ? `${formatTime(summary.keptDuration)} / 원본 ${formatTime(summary.totalDuration)}`
        : '분석 전',
    ],
    ['컷 적용 개수', `${summary.cutCount}개`],
    ['자막', `${summary.subtitleLineCount}줄`],
    ['훅 문구', summary.selectedHook ?? '선택 안 함'],
    ['화면 보정', summary.correctionApplied ? '적용됨' : '적용 안 함'],
    ['배경음', summary.bgmMood ? `${summary.bgmMood} (${Math.round(summary.bgmVolume * 100)}%)` : '없음'],
    ['효과음', summary.sfxEnabled ? '켜짐' : '꺼짐'],
  ]

  return (
    <div>
      <p className="screen-description">내보내기 전에 마지막으로 확인해주세요.</p>
      <dl className={styles.summaryList}>
        {rows.map(([label, value]) => (
          <div key={label} className={styles.row}>
            <dt className={styles.label}>{label}</dt>
            <dd className={styles.value}>{value}</dd>
          </div>
        ))}
      </dl>
      <Button onClick={onNext} className={placeholderStyles.nextButton}>
        내보내기로 이동
      </Button>
    </div>
  )
}
