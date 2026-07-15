import type { ContentCategory } from '../types'

export interface ShootingGuideInput {
  // 필수 입력
  topic: string
  category: ContentCategory | null
  productOrSituation: string
  targetDuration: string

  // 선택 입력
  location: string
  equipment: string
  faceOnCamera: boolean
  mustShowScenes: string
  availableTime: string
  notes: string
}

export const EMPTY_SHOOTING_GUIDE_INPUT: ShootingGuideInput = {
  topic: '',
  category: null,
  productOrSituation: '',
  targetDuration: '',
  location: '',
  equipment: '',
  faceOnCamera: false,
  mustShowScenes: '',
  availableTime: '',
  notes: '',
}

export function isShootingGuideInputComplete(input: ShootingGuideInput): boolean {
  return (
    input.topic.trim().length > 0 &&
    input.category !== null &&
    input.productOrSituation.trim().length > 0 &&
    input.targetDuration.trim().length > 0
  )
}
