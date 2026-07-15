import { Baby, Brush, CookingPot, Home, Map, Sparkles, TentTree } from 'lucide-react'
import type { ContentCategory } from '../types'
import { CATEGORY_LABELS, CATEGORY_ORDER } from '../types'
import { CategoryCard } from './CategoryCard'
import styles from './CategorySelector.module.css'

const CATEGORY_ICONS: Record<ContentCategory, typeof Home> = {
  LIVING: Home,
  CLEANING: Sparkles,
  FOOD: CookingPot,
  PARENTING: Baby,
  BEAUTY: Brush,
  TRAVEL: Map,
  CAMPING: TentTree,
}

interface CategorySelectorProps {
  value: ContentCategory | null
  onChange: (category: ContentCategory) => void
  title?: string | null
}

/**
 * 카테고리 카드형 선택 UI. 프로젝트당 주 카테고리 1개만 선택 가능(단일 선택).
 * MODE 1의 2단계와 MODE 2 입력 폼에서 공통으로 재사용한다.
 */
export function CategorySelector({ value, onChange, title = '카테고리 선택' }: CategorySelectorProps) {
  return (
    <div>
      {title ? <h2 className={styles.title}>{title}</h2> : null}
      <div className={`card-grid ${styles.grid}`} role="group" aria-label="콘텐츠 카테고리 (하나만 선택)">
        {CATEGORY_ORDER.map((category) => {
          const Icon = CATEGORY_ICONS[category]
          return (
            <CategoryCard
              key={category}
              icon={<Icon size={22} />}
              label={CATEGORY_LABELS[category]}
              selected={value === category}
              onSelect={() => onChange(category)}
            />
          )
        })}
      </div>
    </div>
  )
}
