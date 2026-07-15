import { useId, type ReactNode } from 'react'
import { Button } from './Button'
import cardStyles from './Card.module.css'
import styles from './ModeCard.module.css'

interface ModeCardProps {
  icon: ReactNode
  title: string
  description: string
  buttonLabel: string
  onSelect: () => void
}

/** 앱 첫 화면의 두 개의 큰 모드 카드(AI 자동 편집 / AI 촬영 가이드) 중 하나. */
export function ModeCard({ icon, title, description, buttonLabel, onSelect }: ModeCardProps) {
  const titleId = useId()
  return (
    <section className={`${cardStyles.card} ${styles.modeCard}`} aria-labelledby={titleId}>
      <div className={styles.icon} aria-hidden="true">
        {icon}
      </div>
      <h2 id={titleId} className={styles.title}>
        {title}
      </h2>
      <p className={styles.description}>{description}</p>
      <Button onClick={onSelect} className={styles.actionButton}>
        {buttonLabel}
      </Button>
    </section>
  )
}
