import { useEffect, useState } from 'react'
import { Button } from '../../components/Button'
import { StatusMessage } from '../../components/StatusMessage'
import {
  getAudioStatus,
  getBgmLibrary,
  getBgmRecommendation,
  getSfxSuggestions,
  sfxPreviewUrl,
  startAudio,
  updateAudioSettings,
  updateSfxDecision,
  type BgmRecommendationDto,
  type BgmTrackDto,
  type JobStatus,
  type SfxRecommendationDto,
} from '../../api/client'
import { useJobPolling } from '../../hooks/useJobPolling'
import { formatTime } from '../../utils/formatTime'
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
  const [bgmRec, setBgmRec] = useState<BgmRecommendationDto | null>(null)
  const [sfxRecs, setSfxRecs] = useState<SfxRecommendationDto[]>([])
  const [sfxLoading, setSfxLoading] = useState(true)

  const { data, error, isPolling, start } = useJobPolling<JobStatus>(
    async () => {
      await updateAudioSettings(projectId, { bgmMood: mood, bgmVolume: volume, sfxEnabled })
      return startAudio(projectId)
    },
    () => getAudioStatus(projectId),
  )

  useEffect(() => {
    Promise.all([getBgmLibrary(projectId), getBgmRecommendation(projectId)])
      .then(([libRes, recRes]) => {
        setTracks(libRes.tracks)
        setBgmRec(recRes)
        setMood((prev) => prev ?? (libRes.tracks.some((t) => t.mood === recRes.mood) ? recRes.mood : libRes.tracks[0]?.mood ?? null))
      })
      .finally(() => setLoading(false))

    getSfxSuggestions(projectId)
      .then((res) => setSfxRecs(res.recommendations))
      .catch(() => setSfxRecs([]))
      .finally(() => setSfxLoading(false))
  }, [projectId])

  async function handleSelectSfx(time: number, assetId: string) {
    const res = await updateSfxDecision(projectId, time, true, assetId)
    setSfxRecs(res.recommendations)
  }

  async function handleRejectSfx(time: number) {
    const res = await updateSfxDecision(projectId, time, false, null)
    setSfxRecs(res.recommendations)
  }

  return (
    <div>
      <p className="screen-description">배경음과 효과음, 볼륨을 정해주세요.</p>

      {loading ? <StatusMessage variant="info">불러오는 중...</StatusMessage> : null}

      {!loading ? (
        <>
          <h2 className={styles.sectionTitle}>배경음 분위기</h2>

          {bgmRec ? (
            <div className={styles.recommendationBox}>
              <p className={styles.recommendationTitle}>
                AI 추천: {bgmRec.moodLabel} · {bgmRec.energyLabel} · {bgmRec.tempoRangeBpm[0]}~{bgmRec.tempoRangeBpm[1]}{' '}
                BPM · {bgmRec.hasVocals ? '보컬 포함' : '보컬 없는 트랙'}
              </p>
              <p className={styles.recommendationHint}>
                실제 음원은 아래 키워드로 무료 음원 사이트에서 검색해 CapCut에 직접 추가해보세요.
              </p>
              <div className={styles.keywordList}>
                {bgmRec.searchKeywords.map((kw) => (
                  <span key={kw} className={styles.keywordChip}>
                    {kw}
                  </span>
                ))}
              </div>
              {bgmRec.duckDuringVoice ? (
                <p className={styles.recommendationHint}>목소리가 나오는 구간에서는 배경음 볼륨이 자동으로 줄어듭니다.</p>
              ) : null}
            </div>
          ) : null}

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
            장면에 맞는 효과음 넣기
          </label>

          {sfxEnabled ? (
            <div className={styles.sfxSection}>
              <h2 className={styles.sectionTitle}>효과음 추천</h2>
              {sfxLoading ? <StatusMessage variant="info">효과음을 분석하는 중입니다...</StatusMessage> : null}
              {!sfxLoading && sfxRecs.length === 0 ? (
                <p className={styles.recommendationHint}>이 영상에는 추천할 효과음이 없어요.</p>
              ) : null}
              {sfxRecs.map((rec) => (
                <div key={rec.time} className={styles.sfxRecommendation}>
                  <p className={styles.sfxRecommendationTitle}>
                    {formatTime(rec.time)} · {rec.purposeLabel}
                  </p>
                  <div className={styles.sfxCandidates}>
                    {rec.candidates.map((c) => (
                      <div key={c.assetId} className={styles.sfxCandidateCard}>
                        <audio controls src={sfxPreviewUrl(c.previewUrl)} className={styles.sfxAudio} />
                        <p className={styles.sfxReason}>{c.reason}</p>
                        <button
                          type="button"
                          className={`${styles.sfxSelectButton} ${
                            rec.approved && rec.selectedAssetId === c.assetId ? styles.sfxSelected : ''
                          }`}
                          onClick={() => handleSelectSfx(rec.time, c.assetId)}
                          disabled={isPolling}
                        >
                          이 소리 사용
                        </button>
                      </div>
                    ))}
                    <button
                      type="button"
                      className={`${styles.sfxRejectButton} ${!rec.approved ? styles.sfxSelected : ''}`}
                      onClick={() => handleRejectSfx(rec.time)}
                      disabled={isPolling}
                    >
                      사용 안 함
                    </button>
                  </div>
                </div>
              ))}
            </div>
          ) : null}
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
