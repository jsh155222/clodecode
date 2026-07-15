import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

vi.mock('../api/client', () => ({
  createProject: vi.fn(async () => ({
    id: 'proj1',
    originalFilename: 'v.mp4',
    category: 'FOOD',
    categoryLabel: '음식',
    topic: '',
    totalDuration: null,
    keptDuration: null,
    cutCount: 0,
    subtitleLineCount: 0,
    selectedHook: null,
    stabilizeEnabled: true,
    correctionApplied: false,
    bgmMood: null,
    bgmVolume: 0.18,
    sfxEnabled: true,
    audioApplied: false,
    draftName: null,
  })),
  startAnalyze: vi.fn(async () => ({ status: 'running' })),
  getAnalyzeStatus: vi.fn(async () => ({
    status: 'done',
    log: ['완료'],
    error: null,
    totalDuration: 10,
    keptDuration: 7,
    cutCandidates: [
      { id: 'c1', start: 2, end: 5, source: 'silence', enabled: true },
      { id: 'c2', start: 6, end: 6.5, source: 'filler', enabled: true },
    ],
    subtitleLines: [{ start: 0, end: 1, text: '안녕하세요' }],
  })),
  getCuts: vi.fn(async () => ({
    cutCandidates: [
      { id: 'c1', start: 2, end: 5, source: 'silence', enabled: true },
      { id: 'c2', start: 6, end: 6.5, source: 'filler', enabled: true },
    ],
    keptDuration: 7,
    totalDuration: 10,
  })),
  toggleCut: vi.fn(async (_id: string, cutId: string, enabled: boolean) => ({
    cutCandidates: [
      { id: 'c1', start: 2, end: 5, source: 'silence', enabled: cutId === 'c1' ? enabled : true },
      { id: 'c2', start: 6, end: 6.5, source: 'filler', enabled: cutId === 'c2' ? enabled : true },
    ],
    keptDuration: cutId === 'c1' && !enabled ? 10 : 7,
    totalDuration: 10,
  })),
  startCorrection: vi.fn(async () => ({ status: 'running' })),
  getCorrectionStatus: vi.fn(async () => ({
    status: 'done',
    log: [],
    error: null,
    brightness: 0.1,
    contrast: 1.05,
    meanLuma: 90,
    stabilized: true,
  })),
  getSubtitles: vi.fn(async () => ({ lines: [{ start: 0, end: 1, text: '안녕하세요' }] })),
  updateSubtitles: vi.fn(async (_id: string, lines: unknown) => ({ lines })),
  getHookSuggestions: vi.fn(async (_id: string, topic: string) => ({
    suggestions: [`${topic} 훅1`, `${topic} 훅2`],
    topic,
  })),
  selectHook: vi.fn(async (_id: string, hook: string) => ({ selectedHook: hook })),
  getBgmLibrary: vi.fn(async () => ({ tracks: [{ mood: 'warm', label: '따뜻한' }] })),
  getBgmRecommendation: vi.fn(async () => ({
    mood: 'warm',
    moodLabel: '따뜻한',
    tempoRangeBpm: [85, 105],
    energy: 'MEDIUM',
    energyLabel: '보통',
    hasVocals: false,
    searchKeywords: ['따뜻한 무드 배경음악'],
    duckDuringVoice: true,
    duckVolumeRatio: 0.35,
  })),
  getSfxSuggestions: vi.fn(async () => ({ recommendations: [] })),
  updateSfxDecision: vi.fn(async () => ({ recommendations: [] })),
  updateAudioSettings: vi.fn(async (_id: string, settings: unknown) => settings),
  startAudio: vi.fn(async () => ({ status: 'running' })),
  getAudioStatus: vi.fn(async () => ({ status: 'done', log: [], error: null })),
  getSummary: vi.fn(async () => ({
    id: 'proj1',
    originalFilename: 'v.mp4',
    category: 'FOOD',
    categoryLabel: '음식',
    topic: '원룸 정리',
    totalDuration: 10,
    keptDuration: 7,
    cutCount: 2,
    subtitleLineCount: 1,
    selectedHook: '원룸 정리 훅1',
    stabilizeEnabled: true,
    correctionApplied: true,
    bgmMood: 'warm',
    bgmVolume: 0.18,
    sfxEnabled: true,
    audioApplied: true,
    draftName: null,
  })),
  startExport: vi.fn(async () => ({ status: 'running' })),
  getExportStatus: vi.fn(async () => ({ status: 'done', log: [], error: null, draftName: 'my_draft' })),
}))

// eslint-disable-next-line import/first
import App from '../App'

beforeEach(() => {
  window.localStorage.clear()
  vi.clearAllMocks()
})

describe('AUTO_EDIT 9단계 전체 흐름 (백엔드 API mock)', () => {
  it('1단계부터 9단계 내보내기까지 끝까지 진행할 수 있다', async () => {
    const user = userEvent.setup()
    render(<App />)

    // 시작 -> 1단계
    await user.click(screen.getByRole('button', { name: '영상 편집 시작' }))
    await user.upload(screen.getByLabelText('영상 파일 선택'), new File(['x'], 'v.mp4', { type: 'video/mp4' }))
    await user.click(screen.getByRole('button', { name: '다음' }))

    // 2단계: 카테고리 선택 -> 프로젝트 생성(mock) -> 3단계
    expect(screen.getByText('2 / 9')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /음식/ }))
    await user.click(screen.getByRole('button', { name: '다음' }))

    await waitFor(() => expect(screen.getByText('3 / 9')).toBeInTheDocument())

    // 3단계: 분석 완료 후 다음
    await waitFor(() => expect(screen.getByText(/분석 완료/)).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: '다음' }))

    // 4단계: 컷 검토
    await waitFor(() => expect(screen.getByText('4 / 9')).toBeInTheDocument())
    await waitFor(() => expect(screen.getAllByRole('checkbox').length).toBeGreaterThan(0))
    const firstToggle = screen.getAllByRole('checkbox')[0]
    await user.click(firstToggle) // 컷 하나를 꺼본다
    await user.click(screen.getByRole('button', { name: '다음' }))

    // 5단계: 화면 보정
    await waitFor(() => expect(screen.getByText('5 / 9')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: '화면 보정 시작' }))
    await waitFor(() => expect(screen.getByText(/보정 완료/)).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: '다음' }))

    // 6단계: 자막과 훅
    await waitFor(() => expect(screen.getByText('6 / 9')).toBeInTheDocument())
    await user.type(screen.getByLabelText(/영상 주제/), '원룸 정리')
    await user.click(screen.getByRole('button', { name: '훅 문구 추천받기' }))
    await waitFor(() => expect(screen.getByText('원룸 정리 훅1')).toBeInTheDocument())
    await user.click(screen.getByText('원룸 정리 훅1'))
    await user.click(screen.getByRole('button', { name: '다음' }))

    // 7단계: 소리
    await waitFor(() => expect(screen.getByText('7 / 9')).toBeInTheDocument())
    await waitFor(() => expect(screen.getByRole('button', { name: '따뜻한' })).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: '따뜻한' }))
    await user.click(screen.getByRole('button', { name: '소리 적용하기' }))
    await waitFor(() => expect(screen.getByText('소리 적용 완료')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: '다음' }))

    // 8단계: 최종 확인
    await waitFor(() => expect(screen.getByText('8 / 9')).toBeInTheDocument())
    await waitFor(() => expect(screen.getByText('음식')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: '내보내기로 이동' }))

    // 9단계: 내보내기
    await waitFor(() => expect(screen.getByText('9 / 9')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: '내보내기' }))
    await waitFor(() => expect(screen.getByText(/내보내기 완료/)).toBeInTheDocument())

    // 완료하고 처음으로 -> 시작 화면 복귀
    await user.click(screen.getByRole('button', { name: '완료하고 처음으로' }))
    expect(screen.getByRole('heading', { name: 'AI 자동 편집' })).toBeInTheDocument()
  })

  it('컷을 끄면 유지 시간이 늘어난 것을 화면에서 확인할 수 있다', async () => {
    const user = userEvent.setup()
    render(<App />)
    await user.click(screen.getByRole('button', { name: '영상 편집 시작' }))
    await user.upload(screen.getByLabelText('영상 파일 선택'), new File(['x'], 'v.mp4', { type: 'video/mp4' }))
    await user.click(screen.getByRole('button', { name: '다음' }))
    await user.click(screen.getByRole('button', { name: /음식/ }))
    await user.click(screen.getByRole('button', { name: '다음' }))
    await waitFor(() => expect(screen.getByText(/분석 완료/)).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: '다음' }))

    await waitFor(() => expect(screen.getByText(/0:07 \/ 원본 0:10/)).toBeInTheDocument())

    const toggles = screen.getAllByRole('checkbox')
    await user.click(toggles[0])

    await waitFor(() => expect(screen.getByText(/0:10 \/ 원본 0:10/)).toBeInTheDocument())
  })
})
