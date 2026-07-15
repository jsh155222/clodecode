import { useEffect, useState } from 'react'
import { Button } from '../../components/Button'
import { StatusMessage } from '../../components/StatusMessage'
import {
  getAudioStatus,
  getBgmLibrary,
  startAudio,
  updateAudioSettings,
  type BgmTrackDto,
  type JobStatus,
} from '../../api/client'
import { useJobPolling } from '../../hooks/useJobPolling'
import placeholderStyles from './StepCommon.module.css'
import styles from './Step7Audio.module.css'

interface Step7AudioProps {
  projectId: string
  onNext: () => void
}

/** 7단계: 배경음(무드 선택) + 효과음 + 볼륨을 설정하고 실제로 믹싱한다. */
export function Step7Audio({ projectId, onNext }: Step7AudioProps) {
  const [tracks, setTracks] = useState<BgmTrackDto[]>([])
  const [mood, setMood] = useState<string | null>(null)
  const [volume, setVolume] = useState(0.18)
  const [sfxEnabled, setSfxEnabled] = useState(true)
  const [loading, setLoading] = useState(true)

  const { data, error, isPolling, start } = useJobPolling<JobStatus>(
    async () => {
      await updateAudioSettings(projectId, { bgmMood: mood, bgmVolume: volume, sfxEnabled })
      return startAudio(projectId)
    },
    () => getAudioStatus(projectId),
  )

  useEffect(() => {
    getBgmLibrary(projectId)
      .then((res) => {
        setTracks(res.tracks)
        setMood((prev) => prev ?? res.tracks[0]?.mood ?? null)
      })
      .finally(() => setLoading(false))
  }, [projectId])

  return (
    <div>
      <p className="screen-description">배경음과 효과음, 볼륨을 정해주세요.</p>

      {loading ? <StatusMessage variant="info">불러오는 중...</StatusMessage> : null}

      {!loading ? (
        <>
          <h2 className={styles.sectionTitle}>배경음 분위기</h2>
          <div className={styles.moodList}>
            {tracks.map((t) => (
              <button
                key={t.mood}
                type="button"
                className={`${styles.moodOption} ${mood === t.mood ? styles.moodSelected : ''}`}
                onClick={() => setMood(t.mood)}
                aria-pressed={mood === t.mood}
                disabled={isPolling}
              >
                {t.label}
              </button>
            ))}
          </div>

          <label className={styles.sliderRow}>
            배경음 크기: {Math.round(volume * 100)}%
            <input
              type="range"
              min={0}
              max={0.6}
              step={0.02}
              value={volume}
              disabled={isPolling}
              onChange={(e) => setVolume(Number(e.target.value))}
            />
          </label>

          <label className={styles.checkboxRow}>
            <input
              type="checkbox"
              checked={sfxEnabled}
              disabled={isPolling}
              onChange={(e) => setSfxEnabled(e.target.checked)}
            />
            컷 전환마다 효과음 넣기
          </label>
        </>
      ) : null}

      {!data && !isPolling ? (
        <Button onClick={start} disabled={loading} className={placeholderStyles.nextButton}>
          소리 적용하기
        </Button>
      ) : null}

      {isPolling ? (
        <div className={placeholderStyles.body}>
          <StatusMessage variant="info">배경음/효과음을 합성하는 중입니다...</StatusMessage>
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
          <StatusMessage variant="success">소리 적용 완료</StatusMessage>
        </div>
      ) : null}

      <Button onClick={onNext} disabled={data?.status !== 'done'} className={placeholderStyles.nextButton}>
        다음
      </Button>
    </div>
  )
}
