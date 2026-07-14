import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import type { AppMode, ContentCategory, ProjectState } from '../types'

const STORAGE_KEY = 'capcut-auto:project-state:v1'

function loadInitialState(): ProjectState {
  if (typeof window === 'undefined') {
    return { mode: null, category: null }
  }
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return { mode: null, category: null }
    const parsed = JSON.parse(raw) as Partial<ProjectState>
    return {
      mode: parsed.mode ?? null,
      category: parsed.category ?? null,
    }
  } catch {
    // 저장된 값이 깨져 있으면 안전하게 초기 상태로 되돌린다
    return { mode: null, category: null }
  }
}

interface ProjectContextValue {
  mode: AppMode | null
  category: ContentCategory | null
  setMode: (mode: AppMode | null) => void
  setCategory: (category: ContentCategory) => void
  /** 시작 화면으로 돌아간다. 선택한 카테고리는 프로젝트에 남아있는다(다음에 재선택 안 해도 되도록). */
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
      setMode: (mode) => setState((prev) => ({ ...prev, mode })),
      setCategory: (category) => setState((prev) => ({ ...prev, category })),
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
