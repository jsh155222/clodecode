import { useState } from 'react'
import { Button } from '../components/Button'
import { CategorySelector } from '../components/CategorySelector'
import { CollapsibleSection } from '../components/CollapsibleSection'
import { SelectField } from '../components/SelectField'
import { StatusMessage } from '../components/StatusMessage'
import { TextField } from '../components/TextField'
import { useProject } from '../state/ProjectContext'
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

/**
 * MODE 2(AI 촬영 가이드) 입력 화면 + 빈 결과 화면.
 * 이번 단계에서는 실제 촬영 계획 생성 로직은 구현하지 않는다.
 */
export function ShootingGuideScreen({ onBack }: ShootingGuideScreenProps) {
  const { category, setCategory } = useProject()
  const [input, setInput] = useState<ShootingGuideInput>({ ...EMPTY_SHOOTING_GUIDE_INPUT, category })
  const [submitted, setSubmitted] = useState(false)

  const update = <K extends keyof ShootingGuideInput>(key: K, value: ShootingGuideInput[K]) => {
    setInput((prev) => ({ ...prev, [key]: value }))
  }

  const handleCategoryChange = (next: NonNullable<ShootingGuideInput['category']>) => {
    setCategory(next)
    update('category', next)
  }

  if (submitted) {
    return (
      <div>
        <h1 className="screen-title">촬영 계획</h1>
        <div className={styles.resultBox}>
          <StatusMessage variant="info">
            촬영 계획 자동 생성 기능은 다음 단계에서 연결될 예정입니다. 입력하신 내용은 저장되어 있어요.
          </StatusMessage>
        </div>
        <Button variant="secondary" onClick={() => setSubmitted(false)} className={styles.backToFormButton}>
          입력 내용 수정하기
        </Button>
        <Button onClick={onBack} className={styles.nextButton}>
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

      <Button
        onClick={() => setSubmitted(true)}
        disabled={!isShootingGuideInputComplete(input)}
        className={styles.nextButton}
      >
        촬영 계획 만들기
      </Button>
    </div>
  )
}
