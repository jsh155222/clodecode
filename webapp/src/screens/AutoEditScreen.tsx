import { useState } from 'react'
import { StepHeader } from '../components/StepHeader'
import { AUTO_EDIT_STEPS } from '../types'
import type { AutoEditStepNumber } from '../types'
import { useProject } from '../state/ProjectContext'
import { Step1UploadVideo } from './steps/Step1UploadVideo'
import { Step2SelectCategory } from './steps/Step2SelectCategory'
import { PlaceholderStep } from './steps/PlaceholderStep'

interface AutoEditScreenProps {
  onExitToStart: () => void
}

const PLACEHOLDER_DESCRIPTIONS: Partial<Record<AutoEditStepNumber, string>> = {
  3: '무음, 필러워드, 말더듬 구간을 자동으로 찾습니다.',
  4: '자동으로 찾은 컷 구간을 확인하고 조정합니다.',
  5: '밝기, 흔들림 등 화면을 자동으로 보정합니다.',
  6: '자동 생성된 자막과 훅 문구를 확인합니다.',
  7: '배경음, 효과음, 볼륨을 조정합니다.',
  8: '편집 결과를 최종 확인합니다.',
  9: 'CapCut 드래프트로 내보내거나 결과 파일을 저장합니다.',
}

/** MODE 1(AI 자동 편집)의 9단계 화면 뼈대. 이번 단계에서는 1·2단계 UI만 실제로 동작한다. */
export function AutoEditScreen({ onExitToStart }: AutoEditScreenProps) {
  const { category, setCategory } = useProject()
  const [step, setStep] = useState<AutoEditStepNumber>(1)
  const [videoFileName, setVideoFileName] = useState<string | null>(null)

  const stepMeta = AUTO_EDIT_STEPS[step - 1]

  const goToStep = (next: number) => {
    if (next < 1) {
      onExitToStart()
      return
    }
    if (next > AUTO_EDIT_STEPS.length) {
      onExitToStart()
      return
    }
    setStep(next as AutoEditStepNumber)
  }

  return (
    <div>
      <StepHeader
        currentStep={step}
        totalSteps={AUTO_EDIT_STEPS.length}
        stepLabel={stepMeta.label}
        onBack={() => goToStep(step - 1)}
      />
      <div style={{ marginTop: 24 }}>
        {step === 1 ? (
          <Step1UploadVideo fileName={videoFileName} onFileSelected={setVideoFileName} onNext={() => goToStep(2)} />
        ) : null}
        {step === 2 ? (
          <Step2SelectCategory category={category} onChange={setCategory} onNext={() => goToStep(3)} />
        ) : null}
        {step >= 3 ? (
          <PlaceholderStep
            description={PLACEHOLDER_DESCRIPTIONS[step] ?? ''}
            primaryLabel={step === AUTO_EDIT_STEPS.length ? '완료하고 처음으로' : '다음'}
            onPrimary={() => goToStep(step + 1)}
          />
        ) : null}
      </div>
    </div>
  )
}
