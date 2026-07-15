import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

const { createShootingGuideV2 } = vi.hoisted(() => ({
  createShootingGuideV2: vi.fn(async () => ({
    topic: '캠핑 요리',
    category: 'CAMPING',
    categoryLabel: '캠핑',
    subject: '더치오븐 요리',
    targetDurationSeconds: 30,
    cutCountRange: [6, 12] as [number, number],
    shotCount: 6,
    equipment: ['삼각대'],
    totalRecommendedShootingSeconds: 300,
    warnings: ['이 촬영 계획은 참고용 제안입니다. 실제 업로드한 영상은 MODE 1에서 이 계획과 무관하게 처음부터 다시 분석됩니다.'],
    shots: [
      {
        order: 1,
        role: 'HOOK',
        roleLabel: '초반 훅 장면',
        description: '더치오븐 요리의 가장 흥미로운 순간을 3초 안에 보여주며 시작하세요.',
        camera: { angle: '정면', distance: '클로즈업', height: '아이레벨', direction: '피사체 정면', movement: '고정' },
        recommendedShootingSeconds: 20,
        subtitleSafeZoneHint: '화면 하단 25%는 자막 영역으로 비워두세요.',
        mandatory: true,
      },
      {
        order: 2,
        role: 'RESULT',
        roleLabel: '결과',
        description: '더치오븐 요리의 최종 결과를 보여주며 마무리하세요.',
        camera: { angle: '정면 또는 45도', distance: '와이드~미디엄', height: '아이레벨', direction: '결과물 정면', movement: '고정 또는 천천히 줌인' },
        recommendedShootingSeconds: 20,
        subtitleSafeZoneHint: '결과물이 화면 중앙~상단에 오도록 구도를 잡아 하단 자막 영역을 확보하세요.',
        mandatory: true,
      },
    ],
  })),
}))

vi.mock('../api/client', () => ({
  createShootingGuide: vi.fn(),
  createShootingGuideV2,
}))

// eslint-disable-next-line import/first
import { ShootingGuideScreen } from '../screens/ShootingGuideScreen'
// eslint-disable-next-line import/first
import { ProjectProvider } from '../state/ProjectContext'

function renderScreen() {
  return render(
    <ProjectProvider>
      <ShootingGuideScreen onBack={vi.fn()} />
    </ProjectProvider>,
  )
}

beforeEach(() => {
  window.localStorage.clear()
  vi.clearAllMocks()
})

describe('ShootingGuideScreen - 새 방식(v2)', () => {
  it('기본적으로는 기본 방식(v1) 폼이 보인다', () => {
    renderScreen()
    expect(screen.getByLabelText(/제품 또는 상황/)).toBeInTheDocument()
  })

  it('"새 방식" 버튼을 누르면 v2 폼으로 전환된다', async () => {
    const user = userEvent.setup()
    renderScreen()
    await user.click(screen.getByRole('button', { name: /새 방식/ }))
    expect(screen.getByLabelText(/촬영 대상/)).toBeInTheDocument()
    expect(screen.queryByLabelText(/제품 또는 상황/)).not.toBeInTheDocument()
  })

  it('v2 폼 제출 시 새 스키마로 요청하고 체크리스트 결과 화면을 보여준다', async () => {
    const user = userEvent.setup()
    renderScreen()

    await user.click(screen.getByRole('button', { name: /새 방식/ }))
    await user.type(screen.getByLabelText(/촬영 주제/), '캠핑 요리')
    await user.click(screen.getByRole('button', { name: /캠핑/ }))
    await user.type(screen.getByLabelText(/촬영 대상/), '더치오븐 요리')

    await user.click(screen.getByRole('button', { name: '촬영 계획 만들기' }))

    await waitFor(() =>
      expect(createShootingGuideV2).toHaveBeenCalledWith(
        expect.objectContaining({
          topic: '캠핑 요리',
          subject: '더치오븐 요리',
          category: 'CAMPING',
          targetDurationSeconds: 30,
        }),
      ),
    )

    await waitFor(() => expect(screen.getByText('촬영 계획 (체크리스트)')).toBeInTheDocument())
    expect(screen.getByText(/컷 6개/)).toBeInTheDocument()
    expect(screen.getAllByText('필수').length).toBe(2)
    expect(screen.getByText(/MODE 1/)).toBeInTheDocument()
  })

  it('체크리스트 항목을 체크하면 진행률이 올라간다', async () => {
    const user = userEvent.setup()
    renderScreen()
    await user.click(screen.getByRole('button', { name: /새 방식/ }))
    await user.type(screen.getByLabelText(/촬영 주제/), '캠핑 요리')
    await user.click(screen.getByRole('button', { name: /캠핑/ }))
    await user.type(screen.getByLabelText(/촬영 대상/), '더치오븐 요리')
    await user.click(screen.getByRole('button', { name: '촬영 계획 만들기' }))
    await waitFor(() => expect(screen.getByText('촬영 계획 (체크리스트)')).toBeInTheDocument())

    expect(screen.getByText(/촬영 진행률 0\/2/)).toBeInTheDocument()

    const checkboxes = screen.getAllByRole('checkbox', { name: '촬영 완료' })
    await user.click(checkboxes[0])

    expect(screen.getByText(/촬영 진행률 1\/2/)).toBeInTheDocument()
  })
})
