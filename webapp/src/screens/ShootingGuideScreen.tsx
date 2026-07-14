import { useState } from 'react'
import { Button } from '../components/Button'
import { CategorySelector } from '../components/CategorySelector'
import { CollapsibleSection } from '../components/CollapsibleSection'
import { SelectField } from '../components/SelectField'
import { StatusMessage } from '../components/StatusMessage'
import { TextField } from '../components/TextField'
import { useProject } from '../state/ProjectContext'
import { createShootingGuide, type ShootingPlanDto } from '../api/client'
import { EMPTY_SHOOTING_GUIDE_INPUT, isShootingGuideInputComplete, type ShootingGuideInput } from './shootingGuideTypes'
import styles from './ShootingGuideScreen.module.css'

const TARGET_DURATION_OPTIONS = [
  { value: 'UNDER_1MIN', label: '1분 이내' },
  { value: '1_TO_3MIN', label: '1~3분' },
  { value: '3_TO_5MIN', label: '3~5분' },
  { value: 'OVER_5MIN', label: '5분 이상' },
]

interface ShootingGuideScreenProps {
  onBack: () => void
}

/** MODE 2(AI 촬영 가이드) 입력 화면 + 촬영 계획(앵글/순서) 결과 화면. */
export function ShootingGuideScreen({ onBack }: ShootingGuideScreenProps) {
  const { category, setCategory, continueToAutoEdit } = useProject()
  const [input, setInput] = useState<ShootingGuideInput>({ ...EMPTY_SHOOTING_GUIDE_INPUT, category })
  const [plan, setPlan] = useState<ShootingPlanDto | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const update = <K extends keyof ShootingGuideInput>(key: K, value: ShootingGuideInput[K]) => {
    setInput((prev) => ({ ...prev, [key]: value }))
  }

  const handleCategoryChange = (next: NonNullable<ShootingGuideInput['category']>) => {
    setCategory(next)
    update('category', next)
  }

  const handleSubmit = async () => {
    if (!input.category) return
    setLoading(true)
    setError(null)
    try {
      const result = await createShootingGuide({
        topic: input.topic,
        category: input.category,
        productOrSituation: input.productOrSituation,
        targetDuration: input.targetDuration,
        location: input.location,
        equipment: input.equipment,
        faceOnCamera: input.faceOnCamera,
        mustShowScenes: input.mustShowScenes,
        availableTime: input.availableTime,
        notes: input.notes,
      })
      setPlan(result)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
    }
  }

  if (plan) {
    return (
      <div>
        <h1 className="screen-title">촬영 계획</h1>
        <p className="screen-description">
          {plan.categoryLabel} · 예상 촬영 분량 약 {Math.round(plan.totalEstimatedSeconds / 60)}분
        </p>

        {plan.warnings.map((w) => (
          <div key={w} className={styles.resultBox}>
            <StatusMessage variant="warning">{w}</StatusMessage>
          </div>
        ))}

        <ol className={styles.shotList}>
          {plan.shots.map((shot) => (
            <li key={shot.order} className={styles.shotCard}>
              <div className={styles.shotHeader}>
                <span className={styles.shotOrder}>{shot.order}</span>
                <span className={styles.angleBadge}>{shot.angleLabel}</span>
                <span className={styles.shotSeconds}>약 {shot.estimatedSeconds}초</span>
              </div>
              <h2 className={styles.shotTitle}>{shot.title}</h2>
              <p className={styles.shotDescription}>{shot.description}</p>
              {shot.tip ? <p className={styles.shotTip}>💡 {shot.tip}</p> : null}
            </li>
          ))}
        </ol>

        <h2 className={styles.sectionTitle}>장비 팁</h2>
        <ul className={styles.tipList}>
          {plan.equipmentTips.map((tip) => (
            <li key={tip}>{tip}</li>
          ))}
        </ul>

        <Button variant="secondary" onClick={() => setPlan(null)} className={styles.backToFormButton}>
          입력 내용 수정하기
        </Button>
        <Button onClick={() => continueToAutoEdit(plan)} className={styles.nextButton}>
          이 계획으로 영상 편집 시작
        </Button>
        <Button variant="secondary" onClick={onBack} className={styles.backToFormButton}>
          처음으로 돌아가기
        </Button>
      </div>
    )
  }

  return (
    <div>
      <h1 className="screen-title">촬영 계획 만들기</h1>
      <p className="screen-description">촬영 전에 필요한 정보를 입력하면 앵글과 촬영 순서를 안내해드려요.</p>

      <div className={styles.form}>
        <TextField
          label="촬영 주제"
          required
          value={input.topic}
          placeholder="예: 원룸 정리 루틴 브이로그"
          onChange={(v) => update('topic', v)}
        />

        <div className={styles.categoryBlock}>
          <CategorySelector value={input.category} onChange={handleCategoryChange} title="카테고리 *" />
        </div>

        <TextField
          label="제품 또는 상황"
          required
          value={input.productOrSituation}
          placeholder="예: 신제품 무선 청소기 리뷰"
          onChange={(v) => update('productOrSituation', v)}
        />

        <SelectField
          label="목표 영상 길이"
          required
          value={input.targetDuration}
          options={TARGET_DURATION_OPTIONS}
          onChange={(v) => update('targetDuration', v)}
        />

        <CollapsibleSection title="추가 정보 입력 (선택)">
          <TextField label="촬영 장소" value={input.location} onChange={(v) => update('location', v)} />
          <TextField label="보유 장비" value={input.equipment} onChange={(v) => update('equipment', v)} />
          <label className={styles.checkboxRow}>
            <input
              type="checkbox"
              checked={input.faceOnCamera}
              onChange={(e) => update('faceOnCamera', e.target.checked)}
            />
            얼굴이 화면에 나와요
          </label>
          <TextField
            label="반드시 보여줄 장면"
            value={input.mustShowScenes}
            multiline
            onChange={(v) => update('mustShowScenes', v)}
          />
          <TextField label="촬영 가능 시간" value={input.availableTime} onChange={(v) => update('availableTime', v)} />
          <TextField label="추가 메모" value={input.notes} multiline onChange={(v) => update('notes', v)} />
        </CollapsibleSection>
      </div>

      {error ? (
        <div className={styles.resultBox}>
          <StatusMessage variant="warning">{error}</StatusMessage>
        </div>
      ) : null}

      <Button
        onClick={handleSubmit}
        disabled={!isShootingGuideInputComplete(input) || loading}
        className={styles.nextButton}
      >
        {loading ? '촬영 계획 만드는 중...' : '촬영 계획 만들기'}
      </Button>
    </div>
  )
}
