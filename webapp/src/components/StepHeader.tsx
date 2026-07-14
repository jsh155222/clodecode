import styles from './StepHeader.module.css'

interface StepHeaderProps {
  currentStep: number
  totalSteps: number
  stepLabel: string
  onBack?: () => void
}

/** MODE 1 상단에 현재 단계를 "3 / 9 자동 분석" 형태로 표시한다. */
export function StepHeader({ currentStep, totalSteps, stepLabel, onBack }: StepHeaderProps) {
  const progressPercent = Math.round((currentStep / totalSteps) * 100)
  return (
    <header className={styles.header}>
      {onBack ? (
        <button type="button" className={styles.backButton} onClick={onBack} aria-label="이전 화면으로">
          ←
        </button>
      ) : null}
      <div className={styles.textGroup}>
        <p className={styles.stepCount} aria-hidden="true">
          {currentStep} / {totalSteps}
        </p>
        <h1 className={styles.stepLabel}>{stepLabel}</h1>
      </div>
      <div
        className={styles.progressTrack}
        role="progressbar"
        aria-valuenow={currentStep}
        aria-valuemin={1}
        aria-valuemax={totalSteps}
        aria-label={`전체 ${totalSteps}단계 중 ${currentStep}단계: ${stepLabel}`}
      >
        <div className={styles.progressFill} style={{ width: `${progressPercent}%` }} />
      </div>
    </header>
  )
}
