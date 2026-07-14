import { Button } from '../../components/Button'
import { StatusMessage } from '../../components/StatusMessage'
import styles from './PlaceholderStep.module.css'

interface PlaceholderStepProps {
  description: string
  primaryLabel: string
  onPrimary: () => void
}

/**
 * 3~9단계 공용 뼈대 화면. 이번 단계(앱 구조/카테고리/UI 개선)에서는
 * AI 편집 로직을 새로 구현하지 않으므로, 다음 단계 예고만 보여준다.
 */
export function PlaceholderStep({ description, primaryLabel, onPrimary }: PlaceholderStepProps) {
  return (
    <div>
      <p className="screen-description">{description}</p>
      <div className={styles.body}>
        <StatusMessage variant="info">이 단계의 자동 편집 기능은 다음 단계에서 연결될 예정입니다.</StatusMessage>
      </div>
      <Button onClick={onPrimary} className={styles.nextButton}>
        {primaryLabel}
      </Button>
    </div>
  )
}
