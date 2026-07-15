import { Button } from '../../components/Button'
import { CategorySelector } from '../../components/CategorySelector'
import type { ContentCategory } from '../../types'
import styles from './Step2SelectCategory.module.css'

interface Step2SelectCategoryProps {
  category: ContentCategory | null
  onChange: (category: ContentCategory) => void
  onNext: () => void
}

/** 2단계: 이 영상의 주 카테고리를 하나 선택한다. 선택 결과는 프로젝트에 저장된다. */
export function Step2SelectCategory({ category, onChange, onNext }: Step2SelectCategoryProps) {
  return (
    <div>
      <p className="screen-description">이 영상에 가장 잘 맞는 카테고리를 하나 선택해주세요.</p>
      <div className={styles.selectorWrap}>
        <CategorySelector value={category} onChange={onChange} title={null} />
      </div>
      <Button onClick={onNext} disabled={!category} className={styles.nextButton}>
        다음
      </Button>
    </div>
  )
}
