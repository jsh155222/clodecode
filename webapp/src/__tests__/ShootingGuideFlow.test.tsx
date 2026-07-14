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
    warnings: ['촬영 가능 시간(10분)이 넉넉하지 않을 수 있어요. 리테이크를 고려하면 약 36분 정도를 권장해요.'],
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
  return { ...actual, createShootingGuide: createShootingGuideMock }
})

// eslint-disable-next-line import/first
import App from '../App'

beforeEach(() => {
  window.localStorage.clear()
  createShootingGuideMock.mockClear()
})

async function fillRequiredFields(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText(/촬영 주제/), '1박 2일 캠핑 브이로그')
  await user.click(screen.getByRole('button', { name: '캠핑' }))
  await user.type(screen.getByLabelText(/제품 또는 상황/), '가을 캠핑')
  await user.selectOptions(screen.getByLabelText(/목표 영상 길이/), '5분 이상')
}

describe('MODE 2 촬영 계획 결과 화면', () => {
  it('필수 입력 후 제출하면 실제 촬영 순서가 표시된다', async () => {
    const user = userEvent.setup()
    render(<App />)
    await user.click(screen.getByRole('button', { name: '촬영 계획 만들기' }))
    await fillRequiredFields(user)

    await user.click(screen.getByRole('button', { name: '촬영 계획 만들기' }))

    await waitFor(() => expect(screen.getByText('도착/셋업 샷')).toBeInTheDocument())
    expect(screen.getByText('장비 소개')).toBeInTheDocument()
    expect(screen.getByText('와이드샷')).toBeInTheDocument()
    expect(screen.getByText('손 클로즈업')).toBeInTheDocument()
    expect(createShootingGuideMock).toHaveBeenCalledTimes(1)
  })

  it('경고와 장비 팁이 결과 화면에 표시된다', async () => {
    const user = userEvent.setup()
    render(<App />)
    await user.click(screen.getByRole('button', { name: '촬영 계획 만들기' }))
    await fillRequiredFields(user)
    await user.click(screen.getByRole('button', { name: '촬영 계획 만들기' }))

    await waitFor(() => expect(screen.getByText(/촬영 가능 시간\(10분\)/)).toBeInTheDocument())
    expect(screen.getByText(/삼각대를 고정 샷에/)).toBeInTheDocument()
  })

  it('팁이 없는 샷은 팁 문구를 표시하지 않는다', async () => {
    const user = userEvent.setup()
    render(<App />)
    await user.click(screen.getByRole('button', { name: '촬영 계획 만들기' }))
    await fillRequiredFields(user)
    await user.click(screen.getByRole('button', { name: '촬영 계획 만들기' }))

    await waitFor(() => expect(screen.getByText('도착/셋업 샷')).toBeInTheDocument())
    expect(screen.getByText(/장비 브랜드를 잘 보이게/)).toBeInTheDocument()
  })

  it('"입력 내용 수정하기"를 누르면 이전 입력값이 유지된 채 폼으로 돌아간다', async () => {
    const user = userEvent.setup()
    render(<App />)
    await user.click(screen.getByRole('button', { name: '촬영 계획 만들기' }))
    await fillRequiredFields(user)
    await user.click(screen.getByRole('button', { name: '촬영 계획 만들기' }))

    await waitFor(() => expect(screen.getByText('도착/셋업 샷')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: '입력 내용 수정하기' }))

    expect(screen.getByRole('heading', { name: '촬영 계획 만들기' })).toBeInTheDocument()
    expect(screen.getByLabelText(/촬영 주제/)).toHaveValue('1박 2일 캠핑 브이로그')
  })

  it('제출 버튼은 필수 항목이 채워지기 전까지 비활성화된다', async () => {
    const user = userEvent.setup()
    render(<App />)
    await user.click(screen.getByRole('button', { name: '촬영 계획 만들기' }))

    expect(screen.getByRole('button', { name: '촬영 계획 만들기' })).toBeDisabled()

    await user.type(screen.getByLabelText(/촬영 주제/), '주제')
    expect(screen.getByRole('button', { name: '촬영 계획 만들기' })).toBeDisabled()

    await fillRequiredFields(user)
    expect(screen.getByRole('button', { name: '촬영 계획 만들기' })).toBeEnabled()
  })

  it('API 호출이 실패하면 오류 메시지를 보여주고 폼에 그대로 남는다', async () => {
    createShootingGuideMock.mockRejectedValueOnce(new Error('서버 오류'))
    const user = userEvent.setup()
    render(<App />)
    await user.click(screen.getByRole('button', { name: '촬영 계획 만들기' }))
    await fillRequiredFields(user)
    await user.click(screen.getByRole('button', { name: '촬영 계획 만들기' }))

    await waitFor(() => expect(screen.getByText('서버 오류')).toBeInTheDocument())
    expect(screen.getByRole('heading', { name: '촬영 계획 만들기' })).toBeInTheDocument()
  })
})
