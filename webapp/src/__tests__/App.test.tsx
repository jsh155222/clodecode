import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, within, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

vi.mock('../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/client')>()
  return {
    ...actual,
    createShootingGuide: vi.fn(async () => ({
      topic: '원룸 정리 브이로그',
      category: 'LIVING',
      categoryLabel: '살림',
      targetDurationLabel: '1_TO_3MIN',
      totalEstimatedSeconds: 120,
      equipmentTips: ['별도 장비가 없어도 괜찮아요.'],
      warnings: [],
      shots: [
        {
          order: 1,
          angle: 'WIDE',
          angleLabel: '와이드샷',
          title: '문제 상황 소개',
          description: '이사 후 정리 관련해서 불편했던 상황을 와이드샷으로 보여주며 시작하세요.',
          estimatedSeconds: 20,
          tip: null,
        },
      ],
    })),
  }
})

// eslint-disable-next-line import/first
import App from '../App'

beforeEach(() => {
  window.localStorage.clear()
})

describe('1. 앱 시작 화면', () => {
  it('두 개의 모드 카드만 보여준다', () => {
    render(<App />)
    expect(screen.getByRole('heading', { name: 'AI 자동 편집' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'AI 촬영 가이드' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '영상 편집 시작' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '촬영 계획 만들기' })).toBeInTheDocument()
  })
})

describe('2. AUTO_EDIT 진입', () => {
  it('"영상 편집 시작"을 누르면 1/9 영상 불러오기 단계로 이동한다', async () => {
    const user = userEvent.setup()
    render(<App />)
    await user.click(screen.getByRole('button', { name: '영상 편집 시작' }))

    expect(screen.getByText('1 / 9')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '영상 불러오기' })).toBeInTheDocument()
  })
})

describe('3. SHOOTING_GUIDE 진입', () => {
  it('"촬영 계획 만들기"를 누르면 촬영 가이드 입력 화면으로 이동한다', async () => {
    const user = userEvent.setup()
    render(<App />)
    await user.click(screen.getByRole('button', { name: '촬영 계획 만들기' }))

    expect(screen.getByRole('heading', { name: '촬영 계획 만들기' })).toBeInTheDocument()
    expect(screen.getByLabelText(/촬영 주제/)).toBeInTheDocument()
  })
})

describe('4. 시작 화면 복귀', () => {
  it('AUTO_EDIT에서 뒤로가기를 반복하면 시작 화면으로 돌아간다', async () => {
    const user = userEvent.setup()
    render(<App />)
    await user.click(screen.getByRole('button', { name: '영상 편집 시작' }))
    expect(screen.getByText('1 / 9')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '이전 화면으로' }))

    expect(screen.getByRole('heading', { name: 'AI 자동 편집' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'AI 촬영 가이드' })).toBeInTheDocument()
  })

  it('SHOOTING_GUIDE 결과 화면에서 "처음으로 돌아가기"를 누르면 시작 화면으로 돌아간다', async () => {
    const user = userEvent.setup()
    render(<App />)
    await user.click(screen.getByRole('button', { name: '촬영 계획 만들기' }))

    await user.type(screen.getByLabelText(/촬영 주제/), '원룸 정리 브이로그')
    await user.click(screen.getByRole('button', { name: '살림' }))
    await user.type(screen.getByLabelText(/제품 또는 상황/), '이사 후 정리')
    await user.selectOptions(screen.getByLabelText(/목표 영상 길이/), '1~3분')

    await user.click(screen.getByRole('button', { name: '촬영 계획 만들기' }))
    await waitFor(() => expect(screen.getByText('문제 상황 소개')).toBeInTheDocument())

    await user.click(screen.getByRole('button', { name: '처음으로 돌아가기' }))
    expect(screen.getByRole('heading', { name: 'AI 자동 편집' })).toBeInTheDocument()
  })
})

describe('5. 카테고리 선택', () => {
  it('카테고리 카드를 누르면 선택 상태(aria-pressed)로 바뀐다', async () => {
    const user = userEvent.setup()
    render(<App />)
    await user.click(screen.getByRole('button', { name: '영상 편집 시작' }))

    // 1단계: 영상 선택 (다음 버튼 활성화를 위해 파일 선택을 흉내)
    const fileInput = screen.getByLabelText('영상 파일 선택') as HTMLInputElement
    const file = new File(['dummy'], 'my-video.mp4', { type: 'video/mp4' })
    await user.upload(fileInput, file)
    await user.click(screen.getByRole('button', { name: '다음' }))

    // 2단계: 카테고리 선택
    expect(screen.getByText('2 / 9')).toBeInTheDocument()
    const foodCard = screen.getByRole('button', { name: /음식/ })
    expect(foodCard).toHaveAttribute('aria-pressed', 'false')

    await user.click(foodCard)
    expect(foodCard).toHaveAttribute('aria-pressed', 'true')
  })

  it('한 번에 하나의 카테고리만 선택된다', async () => {
    const user = userEvent.setup()
    render(<App />)
    await user.click(screen.getByRole('button', { name: '촬영 계획 만들기' }))

    const livingCard = screen.getByRole('button', { name: '살림' })
    const travelCard = screen.getByRole('button', { name: '여행' })

    await user.click(livingCard)
    expect(livingCard).toHaveAttribute('aria-pressed', 'true')

    await user.click(travelCard)
    expect(travelCard).toHaveAttribute('aria-pressed', 'true')
    expect(livingCard).toHaveAttribute('aria-pressed', 'false')
  })
})

describe('6. 카테고리 저장과 복원', () => {
  it('카테고리 선택 후 새로고침(재마운트)해도 선택이 복원된다', async () => {
    const user = userEvent.setup()
    const { unmount } = render(<App />)
    await user.click(screen.getByRole('button', { name: '촬영 계획 만들기' }))
    await user.click(screen.getByRole('button', { name: '캠핑' }))

    expect(window.localStorage.getItem('capcut-auto:project-state:v1')).toContain('CAMPING')

    unmount()

    render(<App />)
    await user.click(screen.getByRole('button', { name: '촬영 계획 만들기' }))
    // 복원된 카드는 이미 선택된 상태라 접근성 이름에 "선택됨"이 포함되므로 부분일치로 조회한다
    const campingCard = screen.getByRole('button', { name: /캠핑/ })
    expect(campingCard).toHaveAttribute('aria-pressed', 'true')
  })

  it('AUTO_EDIT에서 선택한 카테고리도 새로고침 후 유지된다', async () => {
    const user = userEvent.setup()
    const { unmount } = render(<App />)
    await user.click(screen.getByRole('button', { name: '영상 편집 시작' }))
    const fileInput = screen.getByLabelText('영상 파일 선택') as HTMLInputElement
    await user.upload(fileInput, new File(['dummy'], 'v.mp4', { type: 'video/mp4' }))
    await user.click(screen.getByRole('button', { name: '다음' }))
    await user.click(screen.getByRole('button', { name: /뷰티/ }))

    unmount()

    // mode/category 모두 프로젝트 상태로 저장되므로, 새로고침 후에도 AUTO_EDIT 1단계로 바로 복귀한다
    // (videoFileName은 세션 상태라 저장되지 않으므로 파일은 다시 선택해야 한다)
    const { container } = render(<App />)
    expect(screen.getByText('1 / 9')).toBeInTheDocument()
    await user.upload(screen.getByLabelText('영상 파일 선택'), new File(['dummy'], 'v2.mp4', { type: 'video/mp4' }))
    await user.click(screen.getByRole('button', { name: '다음' }))

    const beautyCard = within(container).getByRole('button', { name: /뷰티/ })
    expect(beautyCard).toHaveAttribute('aria-pressed', 'true')
  })
})
