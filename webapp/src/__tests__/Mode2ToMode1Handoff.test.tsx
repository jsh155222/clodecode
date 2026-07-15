import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

const { createShootingGuideMock } = vi.hoisted(() => ({
  createShootingGuideMock: vi.fn(async (body: { topic: string }) => ({
    topic: body.topic,
    category: 'CAMPING',
    categoryLabel: '캠핑',
    targetDurationLabel: 'OVER_5MIN',
    totalEstimatedSeconds: 360,
    equipmentTips: ['삼각대를 고정 샷에 활용하면 흔들림 없이 안정적인 화면을 만들 수 있어요.'],
    warnings: [],
    shots: [
      {
        order: 1,
        angle: 'WIDE',
        angleLabel: '와이드샷',
        title: '도착/셋업 샷',
        description: '캠핑장 도착과 사이트 전체를 와이드샷으로 시작하세요.',
        estimatedSeconds: 40,
        tip: null,
      },
      {
        order: 2,
        angle: 'HANDS',
        angleLabel: '손 클로즈업',
        title: '장비 소개',
        description: '텐트 등 주요 장비를 손으로 들고 소개하세요.',
        estimatedSeconds: 40,
        tip: '장비 브랜드를 잘 보이게 잡아주면 좋아요.',
      },
    ],
  })),
}))

vi.mock('../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/client')>()
  return {
    ...actual,
    createShootingGuide: createShootingGuideMock,
    createProject: vi.fn(async () => ({
      id: 'proj1',
      originalFilename: 'v.mp4',
      category: 'CAMPING',
      categoryLabel: '캠핑',
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
      cutCandidates: [],
      subtitleLines: [],
    })),
    getSubtitles: vi.fn(async () => ({ lines: [] })),
    startCorrection: vi.fn(async () => ({ status: 'running' })),
    getCorrectionStatus: vi.fn(async () => ({
      status: 'done',
      log: [],
      error: null,
      brightness: 0,
      contrast: 1,
      meanLuma: 90,
      stabilized: true,
    })),
  }
})

// eslint-disable-next-line import/first
import App from '../App'

beforeEach(() => {
  window.localStorage.clear()
  vi.clearAllMocks()
})

async function fillRequiredFields(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText(/촬영 주제/), '가을 캠핑 브이로그')
  await user.click(screen.getByRole('button', { name: '캠핑' }))
  await user.type(screen.getByLabelText(/제품 또는 상황/), '2박 3일 가을 캠핑')
  await user.selectOptions(screen.getByLabelText(/목표 영상 길이/), '5분 이상')
}

describe('MODE 2 -> MODE 1 인계', () => {
  it('촬영 계획 결과에서 "이 계획으로 영상 편집 시작"을 누르면 AUTO_EDIT 1단계로 이동한다', async () => {
    const user = userEvent.setup()
    render(<App />)

    await user.click(screen.getByRole('button', { name: '촬영 계획 만들기' }))
    await fillRequiredFields(user)
    await user.click(screen.getByRole('button', { name: '촬영 계획 만들기' }))

    await waitFor(() => expect(screen.getByText('도착/셋업 샷')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: '이 계획으로 영상 편집 시작' }))

    expect(screen.getByRole('heading', { name: '영상 불러오기' })).toBeInTheDocument()
    expect(screen.getByText('1 / 9')).toBeInTheDocument()
  })

  it('인계된 촬영 계획은 AUTO_EDIT 화면에서 접었다 펼 수 있는 참고 패널로 보인다', async () => {
    const user = userEvent.setup()
    render(<App />)

    await user.click(screen.getByRole('button', { name: '촬영 계획 만들기' }))
    await fillRequiredFields(user)
    await user.click(screen.getByRole('button', { name: '촬영 계획 만들기' }))
    await waitFor(() => expect(screen.getByText('도착/셋업 샷')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: '이 계획으로 영상 편집 시작' }))

    const trigger = screen.getByRole('button', { name: '촬영 계획 참고' })
    expect(screen.queryByText(/도착\/셋업 샷/)).not.toBeInTheDocument()

    await user.click(trigger)
    expect(screen.getByText(/도착\/셋업 샷/)).toBeInTheDocument()
    expect(screen.getByText(/장비 소개/)).toBeInTheDocument()
  })

  it('넘어온 주제는 카테고리 선택에도 반영되고, 6단계 주제 입력칸에 미리 채워진다', async () => {
    const user = userEvent.setup()
    render(<App />)

    await user.click(screen.getByRole('button', { name: '촬영 계획 만들기' }))
    await fillRequiredFields(user)
    await user.click(screen.getByRole('button', { name: '촬영 계획 만들기' }))
    await waitFor(() => expect(screen.getByText('도착/셋업 샷')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: '이 계획으로 영상 편집 시작' }))

    // 1단계: 영상 업로드
    await user.upload(screen.getByLabelText('영상 파일 선택'), new File(['x'], 'v.mp4', { type: 'video/mp4' }))
    await user.click(screen.getByRole('button', { name: '다음' }))

    // 2단계: MODE 2에서 고른 캠핑 카테고리가 이미 선택돼 있어야 한다
    await waitFor(() => expect(screen.getByText('2 / 9')).toBeInTheDocument())
    expect(screen.getByRole('button', { name: /캠핑/, pressed: true })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '다음' }))

    // 3단계 -> 4단계 (컷 없음) -> 5단계 -> 6단계로 이동
    await waitFor(() => expect(screen.getByText('3 / 9')).toBeInTheDocument())
    await waitFor(() => expect(screen.getByText(/분석 완료/)).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: '다음' }))

    await waitFor(() => expect(screen.getByText('4 / 9')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: '다음' }))

    await waitFor(() => expect(screen.getByText('5 / 9')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: '화면 보정 시작' }))
    await waitFor(() => expect(screen.getByText(/보정 완료/)).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: '다음' }))

    await waitFor(() => expect(screen.getByText('6 / 9')).toBeInTheDocument())
    expect(screen.getByLabelText(/영상 주제/)).toHaveValue('가을 캠핑 브이로그')
  })
})
