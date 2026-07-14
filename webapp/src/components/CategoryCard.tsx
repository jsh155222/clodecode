import type { ReactNode } from 'react'
import styles from './CategoryCard.module.css'

interface CategoryCardProps {
  icon: ReactNode
  label: string
  selected: boolean
  onSelect: () => void
}

/** 카테고리 카드 하나. 아이콘과 이름을 함께 표시하고, 선택 상태를 색+아이콘+문구로 나타낸다. */
export function CategoryCard({ icon, label, selected, onSelect }: CategoryCardProps) {
  return (
    <button
      type="button"
      className={`${styles.card} ${selected ? styles.selected : ''}`}
      onClick={onSelect}
      aria-pressed={selected}
    >
      <span className={styles.icon} aria-hidden="true">
        {icon}
      </span>
      <span className={styles.label}>{label}</span>
      {selected ? <span className={styles.selectedBadge}>선택됨</span> : null}
    </button>
  )
}
