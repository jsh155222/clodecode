import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

const { getReframeSuggestion, updateReframeApproval } = vi.hoisted(() => ({
  getReframeSuggestion: vi.fn(async () => ({
    crop: { x: 100, y: 0, width: 600, height: 1080, zoom: 1.2, subjectFullyContained: true },
    faceDetected: true,
    previewUrl: '/api/projects/p1/reframe-preview',
    approved: false,
  })),
  updateReframeApproval: vi.fn(async (_id: string, approved: boolean) => ({ approved })),
}))

vi.mock('../api/client', () => ({
  getReframeSuggestion,
  updateReframeApproval,
  reframePreviewUrl: (url: string) => `http://127.0.0.1:8000${url}`,
  startCorrection: vi.fn(async () => ({ status: 'running' })),
  getCorrectionStatus: vi.fn(async () => ({ status: 'idle', log: [], error: null })),
}))

// eslint-disable-next-line import/first
import { Step5Correction } from '../screens/steps/Step5Correction'

describe('Step5Correction - 9:16 자동 리프레이밍', () => {
  it('얼굴 감지 결과와 확대 배율, 미리보기 이미지를 보여준다', async () => {
    render(<Step5Correction projectId="p1" onNext={vi.fn()} />)
    await waitFor(() => expect(screen.getByText(/얼굴을 감지해/)).toBeInTheDocument())
    expect(screen.getByText(/1.20배/)).toBeInTheDocument()
    const img = screen.getByAltText('9:16로 자른 미리보기') as HTMLImageElement
    expect(img.src).toBe('http://127.0.0.1:8000/api/projects/p1/reframe-preview')
  })

  it('체크박스는 기본적으로 꺼져 있다(사용자 승인 전에는 미적용)', async () => {
    render(<Step5Correction projectId="p1" onNext={vi.fn()} />)
    await waitFor(() => expect(screen.getByText(/얼굴을 감지해/)).toBeInTheDocument())
    const checkbox = screen.getByRole('checkbox', { name: '이 구도로 9:16 리프레이밍 적용' })
    expect(checkbox).not.toBeChecked()
  })

  it('체크박스를 켜면 승인 API를 호출한다', async () => {
    const user = userEvent.setup()
    render(<Step5Correction projectId="p1" onNext={vi.fn()} />)
    await waitFor(() => expect(screen.getByText(/얼굴을 감지해/)).toBeInTheDocument())

    const checkbox = screen.getByRole('checkbox', { name: '이 구도로 9:16 리프레이밍 적용' })
    await user.click(checkbox)

    expect(checkbox).toBeChecked()
    await waitFor(() => expect(updateReframeApproval).toHaveBeenCalledWith('p1', true))
  })
})
