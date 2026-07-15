import type { ContentCategory } from '../types'

export interface ShootingGuideInputV2Form {
  topic: string
  category: ContentCategory | null
  subject: string
  targetDurationSeconds: string
  location: string
  equipment: string
  showFace: boolean
  availableShootingMinutes: string
  mustShowSteps: string
  additionalNotes: string
}

export const EMPTY_SHOOTING_GUIDE_INPUT_V2: ShootingGuideInputV2Form = {
  topic: '',
  category: null,
  subject: '',
  targetDurationSeconds: '30',
  location: '',
  equipment: '',
  showFace: false,
  availableShootingMinutes: '',
  mustShowSteps: '',
  additionalNotes: '',
}

export function isShootingGuideInputV2Complete(input: ShootingGuideInputV2Form): boolean {
  return (
    input.topic.trim().length > 0 &&
    input.category !== null &&
    input.subject.trim().length > 0 &&
    Number(input.targetDurationSeconds) > 0
  )
}

function splitList(text: string): string[] {
  return text
    .split(/[,\n]/)
    .map((s) => s.trim())
    .filter((s) => s.length > 0)
}

export function parseEquipment(text: string): string[] | undefined {
  const list = splitList(text)
  return list.length > 0 ? list : undefined
}

export function parseMustShowSteps(text: string): string[] | undefined {
  const list = splitList(text)
  return list.length > 0 ? list : undefined
}
