import { useState } from 'react'
import { StepHeader } from '../components/StepHeader'
import { StatusMessage } from '../components/StatusMessage'
import { CollapsibleSection } from '../components/CollapsibleSection'
import { AUTO_EDIT_STEPS } from '../types'
import type { AutoEditStepNumber } from '../types'
import { useProject } from '../state/ProjectContext'
import { createProject } from '../api/client'
import { Step1UploadVideo } from './steps/Step1UploadVideo'
import { Step2SelectCategory } from './steps/Step2SelectCategory'
import { Step3Analyze } from './steps/Step3Analyze'
import { Step4CutReview } from './steps/Step4CutReview'
import { Step5Correction } from './steps/Step5Correction'
import { Step6SubtitlesHook } from './steps/Step6SubtitlesHook'
import { Step7Audio } from './steps/Step7Audio'
import { Step8Confirm } from './steps/Step8Confirm'
import { Step9Export } from './steps/Step9Export'
import placeholderStyles from './steps/StepCommon.module.css'

interface AutoEditScreenProps {
  onExitToStart: () => void
}

/** MODE 1(AI 자동 편집)의 9단계. 1~2단계 이후 백엔드에 프로젝트를 생성해 3~9단계를 실제로 처리한다. */
export function AutoEditScreen({ onExitToStart }: AutoEditScreenProps) {
  const { category, setCategory, shootingPlan } = useProject()
  const [step, setStep] = useState<AutoEditStepNumber>(1)
  const [videoFile, setVideoFile] = useState<File | null>(null)
  const [projectId, setProjectId] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)

  const stepMeta = AUTO_EDIT_STEPS[step - 1]

  const goToStep = (next: number) => {
    if (next < 1 || next > AUTO_EDIT_STEPS.length) {
      onExitToStart()
      return
    }
    setStep(next as AutoEditStepNumber)
  }

  const handleCategoryNext = async () => {
    if (!videoFile || !category) return
    setCreating(true)
    setCreateError(null)
    try {
      const project = await createProject(videoFile, category)
      setProjectId(project.id)
      goToStep(3)
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : String(err))
    } finally {
      setCreating(false)
    }
  }

  return (
    <div>
      <StepHeader
        currentStep={step}
        totalSteps={AUTO_EDIT_STEPS.length}
        stepLabel={stepMeta.label}
        onBack={() => goToStep(step - 1)}
      />
      {shootingPlan ? (
        <div style={{ marginTop: 16 }}>
          <CollapsibleSection title="촬영 계획 참고">
            <p className={placeholderStyles.hint}>
              {shootingPlan.categoryLabel} · {shootingPlan.topic}
            </p>
            <ol className={placeholderStyles.shootingPlanList}>
              {shootingPlan.shots.map((shot) => (
                <li key={shot.order}>
                  {shot.order}. [{shot.angleLabel}] {shot.title}
                </li>
              ))}
            </ol>
          </CollapsibleSection>
        </div>
      ) : null}
      <div style={{ marginTop: 24 }}>
        {step === 1 ? <Step1UploadVideo file={videoFile} onFileSelected={setVideoFile} onNext={() => goToStep(2)} /> : null}

        {step === 2 ? (
          <div>
            <Step2SelectCategory category={category} onChange={setCategory} onNext={handleCategoryNext} />
            {creating ? (
              <div className={placeholderStyles.body}>
                <StatusMessage variant="info">프로젝트를 준비하는 중입니다...</StatusMessage>
              </div>
            ) : null}
            {createError ? (
              <div className={placeholderStyles.body}>
                <StatusMessage variant="warning">{createError}</StatusMessage>
              </div>
            ) : null}
          </div>
        ) : null}

        {step >= 3 && !projectId ? (
          <StatusMessage variant="warning">
            프로젝트가 아직 준비되지 않았어요. 1~2단계를 먼저 완료해주세요.
          </StatusMessage>
        ) : null}

        {step === 3 && projectId ? <Step3Analyze projectId={projectId} onNext={() => goToStep(4)} /> : null}
        {step === 4 && projectId ? <Step4CutReview projectId={projectId} onNext={() => goToStep(5)} /> : null}
        {step === 5 && projectId ? <Step5Correction projectId={projectId} onNext={() => goToStep(6)} /> : null}
        {step === 6 && projectId ? <Step6SubtitlesHook projectId={projectId} onNext={() => goToStep(7)} /> : null}
        {step === 7 && projectId ? <Step7Audio projectId={projectId} onNext={() => goToStep(8)} /> : null}
        {step === 8 && projectId ? <Step8Confirm projectId={projectId} onNext={() => goToStep(9)} /> : null}
        {step === 9 && projectId ? <Step9Export projectId={projectId} onFinished={onExitToStart} /> : null}
      </div>
    </div>
  )
}
