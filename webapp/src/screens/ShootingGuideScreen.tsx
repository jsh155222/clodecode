import { useState } from 'react'
import { Button } from '../components/Button'
import { CategorySelector } from '../components/CategorySelector'
import { CollapsibleSection } from '../components/CollapsibleSection'
import { SelectField } from '../components/SelectField'
import { StatusMessage } from '../components/StatusMessage'
import { TextField } from '../components/TextField'
import { useProject } from '../state/ProjectContext'
import { createShootingGuide, createShootingGuideV2, type ShootingPlanDto, type ShootingPlanV2Dto } from '../api/client'
import { EMPTY_SHOOTING_GUIDE_INPUT, isShootingGuideInputComplete, type ShootingGuideInput } from './shootingGuideTypes'
import {
  EMPTY_SHOOTING_GUIDE_INPUT_V2,
  isShootingGuideInputV2Complete,
  parseEquipment,
  parseMustShowSteps,
  type ShootingGuideInputV2Form,
} from './shootingGuideV2Types'
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

/** MODE 2(AI 촬영 가이드) 입력 화면 + 촬영 계획(앵글/순서) 결과 화면.
 *
 * 기본 방식(v1)은 MODE 1 인계(continueToAutoEdit)까지 이어지는 기존 흐름을 그대로 유지하고,
 * "새 방식"(v2)은 카메라 세부정보/촬영 체크리스트가 필요한 사용자를 위한 별도 흐름이다.
 * v2 계획은 아직 MODE 1로 인계되지 않는다(알려진 범위 제한).
 */
export function ShootingGuideScreen({ onBack }: ShootingGuideScreenProps) {
  const { category, setCategory, continueToAutoEdit } = useProject()
  const [formMode, setFormMode] = useState<'v1' | 'v2'>('v1')
  const [input, setInput] = useState<ShootingGuideInput>({ ...EMPTY_SHOOTING_GUIDE_INPUT, category })
  const [plan, setPlan] = useState<ShootingPlanDto | null>(null)
  const [inputV2, setInputV2] = useState<ShootingGuideInputV2Form>({ ...EMPTY_SHOOTING_GUIDE_INPUT_V2, category })
  const [planV2, setPlanV2] = useState<ShootingPlanV2Dto | null>(null)
  const [checklist, setChecklist] = useState<Record<number, boolean>>({})
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const update = <K extends keyof ShootingGuideInput>(key: K, value: ShootingGuideInput[K]) => {
    setInput((prev) => ({ ...prev, [key]: value }))
  }

  const updateV2 = <K extends keyof ShootingGuideInputV2Form>(key: K, value: ShootingGuideInputV2Form[K]) => {
    setInputV2((prev) => ({ ...prev, [key]: value }))
  }

  const handleCategoryChange = (next: NonNullable<ShootingGuideInput['category']>) => {
    setCategory(next)
    update('category', next)
    updateV2('category', next)
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

  const handleSubmitV2 = async () => {
    if (!inputV2.category) return
    setLoading(true)
    setError(null)
    try {
      const result = await createShootingGuideV2({
        topic: inputV2.topic,
        category: inputV2.category,
        subject: inputV2.subject,
        targetDurationSeconds: Number(inputV2.targetDurationSeconds),
        location: inputV2.location || undefined,
        equipment: parseEquipment(inputV2.equipment),
        showFace: inputV2.showFace,
        availableShootingMinutes: inputV2.availableShootingMinutes ? Number(inputV2.availableShootingMinutes) : undefined,
        mustShowSteps: parseMustShowSteps(inputV2.mustShowSteps),
        additionalNotes: inputV2.additionalNotes || undefined,
      })
      setPlanV2(result)
      setChecklist({})
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
    }
  }

  if (planV2) {
    const doneCount = planV2.shots.filter((s) => checklist[s.order]).length
    const mandatoryShots = planV2.shots.filter((s) => s.mandatory)
    const mandatoryDoneCount = mandatoryShots.filter((s) => checklist[s.order]).length

    return (
      <div>
        <h1 className="screen-title">촬영 계획 (체크리스트)</h1>
        <p className="screen-description">
          {planV2.categoryLabel} · {planV2.subject} · 컷 {planV2.shotCount}개(권장 {planV2.cutCountRange[0]}~
          {planV2.cutCountRange[1]}개) · 총 촬영 권장 약 {Math.round(planV2.totalRecommendedShootingSeconds / 60)}분
        </p>

        {planV2.warnings.map((w) => (
          <div key={w} className={styles.resultBox}>
            <StatusMessage variant="warning">{w}</StatusMessage>
          </div>
        ))}

        <div className={styles.progressRow}>
          <span>
            촬영 진행률 {doneCount}/{planV2.shots.length} (필수 {mandatoryDoneCount}/{mandatoryShots.length})
          </span>
          <div className={styles.progressBarTrack}>
            <div
              className={styles.progressBarFill}
              style={{ width: `${planV2.shots.length ? (doneCount / planV2.shots.length) * 100 : 0}%` }}
            />
          </div>
        </div>

        <ol className={styles.shotList}>
          {planV2.shots.map((shot) => (
            <li key={shot.order} className={styles.shotCard}>
              <div className={styles.shotHeader}>
                <span className={styles.shotOrder}>{shot.order}</span>
                <span className={styles.angleBadge}>{shot.roleLabel}</span>
                {shot.mandatory ? <span className={styles.mandatoryBadge}>필수</span> : null}
                <span className={styles.shotSeconds}>촬영 권장 약 {shot.recommendedShootingSeconds}초</span>
              </div>
              <p className={styles.shotDescription}>{shot.description}</p>
              <ul className={styles.cameraList}>
                <li>앵글: {shot.camera.angle}</li>
                <li>거리: {shot.camera.distance}</li>
                <li>높이: {shot.camera.height}</li>
                <li>방향: {shot.camera.direction}</li>
                <li>움직임: {shot.camera.movement}</li>
              </ul>
              <p className={styles.shotTip}>자막 안전 영역: {shot.subtitleSafeZoneHint}</p>
              <label className={styles.checkboxRow}>
                <input
                  type="checkbox"
                  checked={!!checklist[shot.order]}
                  onChange={(e) => setChecklist((prev) => ({ ...prev, [shot.order]: e.target.checked }))}
                />
                촬영 완료
              </label>
            </li>
          ))}
        </ol>

        {planV2.equipment.length > 0 ? (
          <>
            <h2 className={styles.sectionTitle}>준비할 장비</h2>
            <ul className={styles.tipList}>
              {planV2.equipment.map((eq) => (
                <li key={eq}>{eq}</li>
              ))}
            </ul>
          </>
        ) : null}

        <Button variant="secondary" onClick={() => setPlanV2(null)} className={styles.backToFormButton}>
          입력 내용 수정하기
        </Button>
        <Button variant="secondary" onClick={onBack} className={styles.backToFormButton}>
          처음으로 돌아가기
        </Button>
      </div>
    )
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

      <div className={styles.modeToggle} role="group" aria-label="촬영 가이드 방식 선택">
        <button
          type="button"
          className={`${styles.modeButton} ${formMode === 'v1' ? styles.modeButtonSelected : ''}`}
          aria-pressed={formMode === 'v1'}
          onClick={() => setFormMode('v1')}
        >
          기본 방식
        </button>
        <button
          type="button"
          className={`${styles.modeButton} ${formMode === 'v2' ? styles.modeButtonSelected : ''}`}
          aria-pressed={formMode === 'v2'}
          onClick={() => setFormMode('v2')}
        >
          새 방식 (카메라 세부정보 + 체크리스트)
        </button>
      </div>

      {formMode === 'v1' ? (
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
      ) : (
        <div className={styles.form}>
          <TextField
            label="촬영 주제"
            required
            value={inputV2.topic}
            placeholder="예: 원룸 정리 루틴 브이로그"
            onChange={(v) => updateV2('topic', v)}
          />

          <div className={styles.categoryBlock}>
            <CategorySelector value={inputV2.category} onChange={handleCategoryChange} title="카테고리 *" />
          </div>

          <TextField
            label="촬영 대상"
            required
            value={inputV2.subject}
            placeholder="예: 무선 청소기"
            onChange={(v) => updateV2('subject', v)}
          />

          <label className={styles.numberField}>
            목표 영상 길이(초) *
            <input
              type="number"
              min={1}
              className={styles.numberInput}
              value={inputV2.targetDurationSeconds}
              onChange={(e) => updateV2('targetDurationSeconds', e.target.value)}
            />
          </label>

          <CollapsibleSection title="추가 정보 입력 (선택)">
            <TextField label="촬영 장소" value={inputV2.location} onChange={(v) => updateV2('location', v)} />
            <TextField
              label="보유 장비 (쉼표로 구분)"
              value={inputV2.equipment}
              placeholder="예: 삼각대, 짐벌"
              onChange={(v) => updateV2('equipment', v)}
            />
            <label className={styles.checkboxRow}>
              <input
                type="checkbox"
                checked={inputV2.showFace}
                onChange={(e) => updateV2('showFace', e.target.checked)}
              />
              얼굴이 화면에 나와요
            </label>
            <TextField
              label="꼭 촬영해야 할 장면 (쉼표 또는 줄바꿈으로 구분)"
              value={inputV2.mustShowSteps}
              multiline
              onChange={(v) => updateV2('mustShowSteps', v)}
            />
            <label className={styles.numberField}>
              촬영 가능 시간(분)
              <input
                type="number"
                min={0}
                className={styles.numberInput}
                value={inputV2.availableShootingMinutes}
                onChange={(e) => updateV2('availableShootingMinutes', e.target.value)}
              />
            </label>
            <TextField label="추가 메모" value={inputV2.additionalNotes} multiline onChange={(v) => updateV2('additionalNotes', v)} />
          </CollapsibleSection>
        </div>
      )}

      {error ? (
        <div className={styles.resultBox}>
          <StatusMessage variant="warning">{error}</StatusMessage>
        </div>
      ) : null}

      {formMode === 'v1' ? (
        <Button
          onClick={handleSubmit}
          disabled={!isShootingGuideInputComplete(input) || loading}
          className={styles.nextButton}
        >
          {loading ? '촬영 계획 만드는 중...' : '촬영 계획 만들기'}
        </Button>
      ) : (
        <Button
          onClick={handleSubmitV2}
          disabled={!isShootingGuideInputV2Complete(inputV2) || loading}
          className={styles.nextButton}
        >
          {loading ? '촬영 계획 만드는 중...' : '촬영 계획 만들기'}
        </Button>
      )}
    </div>
  )
}
