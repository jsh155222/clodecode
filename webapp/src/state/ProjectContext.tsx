import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import type { AppMode, ContentCategory, ProjectState } from '../types'
import type { ShootingPlanDto } from '../api/client'

const STORAGE_KEY = 'capcut-auto:project-state:v1'

const EMPTY_STATE: ProjectState = { mode: null, category: null, topic: '', shootingPlan: null }

function loadInitialState(): ProjectState {
  if (typeof window === 'undefined') {
    return EMPTY_STATE
  }
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return EMPTY_STATE
    const parsed = JSON.parse(raw) as Partial<ProjectState>
    return {
      mode: parsed.mode ?? null,
      category: parsed.category ?? null,
      topic: parsed.topic ?? '',
      shootingPlan: parsed.shootingPlan ?? null,
    }
  } catch {
    // 저장된 값이 깨져 있으면 안전하게 초기 상태로 되돌린다
    return EMPTY_STATE
  }
}

interface ProjectContextValue {
  mode: AppMode | null
  category: ContentCategory | null
  topic: string
  shootingPlan: ShootingPlanDto | null
  setMode: (mode: AppMode | null) => void
  setCategory: (category: ContentCategory) => void
  setTopic: (topic: string) => void
  setShootingPlan: (plan: ShootingPlanDto | null) => void
  /**
   * MODE 2(촬영 가이드)에서 세운 계획을 들고 MODE 1(자동 편집)로 넘어간다.
   * 카테고리/주제를 그대로 유지해 다시 입력하지 않아도 되게 한다.
   */
  continueToAutoEdit: (plan: ShootingPlanDto) => void
  /** 시작 화면으로 돌아간다. 선택한 카테고리/주제는 프로젝트에 남아있는다(다음에 재입력 안 해도 되도록). */
  returnToStart: () => void
}

const ProjectContext = createContext<ProjectContextValue | null>(null)

export function ProjectProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<ProjectState>(loadInitialState)

  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
    } catch {
      // 저장 실패(예: 프라이빗 모드)해도 앱 동작에는 지장 없어야 하므로 무시한다
    }
  }, [state])

  const value = useMemo<ProjectContextValue>(
    () => ({
      mode: state.mode,
      category: state.category,
      topic: state.topic,
      shootingPlan: state.shootingPlan,
      setMode: (mode) => setState((prev) => ({ ...prev, mode })),
      setCategory: (category) => setState((prev) => ({ ...prev, category })),
      setTopic: (topic) => setState((prev) => ({ ...prev, topic })),
      setShootingPlan: (shootingPlan) => setState((prev) => ({ ...prev, shootingPlan })),
      continueToAutoEdit: (plan) =>
        setState((prev) => ({
          ...prev,
          mode: 'AUTO_EDIT',
          topic: plan.topic,
          shootingPlan: plan,
        })),
      returnToStart: () => setState((prev) => ({ ...prev, mode: null })),
    }),
    [state],
  )

  return <ProjectContext.Provider value={value}>{children}</ProjectContext.Provider>
}

export function useProject(): ProjectContextValue {
  const ctx = useContext(ProjectContext)
  if (!ctx) {
    throw new Error('useProject는 ProjectProvider 내부에서만 사용할 수 있습니다.')
  }
  return ctx
}
