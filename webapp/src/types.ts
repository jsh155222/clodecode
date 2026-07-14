export type AppMode = 'AUTO_EDIT' | 'SHOOTING_GUIDE'

export type ContentCategory =
  | 'LIVING'
  | 'CLEANING'
  | 'FOOD'
  | 'PARENTING'
  | 'BEAUTY'
  | 'TRAVEL'
  | 'CAMPING'

export const CATEGORY_LABELS: Record<ContentCategory, string> = {
  LIVING: '살림',
  CLEANING: '청소',
  FOOD: '음식',
  PARENTING: '육아',
  BEAUTY: '뷰티',
  TRAVEL: '여행',
  CAMPING: '캠핑',
}

export const CATEGORY_ORDER: ContentCategory[] = [
  'LIVING',
  'CLEANING',
  'FOOD',
  'PARENTING',
  'BEAUTY',
  'TRAVEL',
  'CAMPING',
]

/** MODE 1(AI 자동 편집)의 9단계. */
export const AUTO_EDIT_STEPS = [
  { step: 1, label: '영상 불러오기' },
  { step: 2, label: '카테고리 선택' },
  { step: 3, label: '자동 분석' },
  { step: 4, label: '컷 검토' },
  { step: 5, label: '화면 보정' },
  { step: 6, label: '자막과 훅' },
  { step: 7, label: '소리' },
  { step: 8, label: '최종 확인' },
  { step: 9, label: '내보내기' },
] as const

export type AutoEditStepNumber = (typeof AUTO_EDIT_STEPS)[number]['step']

/** 현재 진행 중인 프로젝트 상태. 카테고리는 프로젝트에 저장되고 새로고침 후에도 복원된다. */
export interface ProjectState {
  mode: AppMode | null
  category: ContentCategory | null
}
