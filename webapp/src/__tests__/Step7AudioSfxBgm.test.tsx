import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

const { getBgmRecommendation, getSfxSuggestions, updateSfxDecision } = vi.hoisted(() => ({
  getBgmRecommendation: vi.fn(async () => ({
    mood: 'warm',
    moodLabel: '따뜻한',
    tempoRangeBpm: [85, 105] as [number, number],
    energy: 'MEDIUM' as const,
    energyLabel: '보통',
    hasVocals: false,
    searchKeywords: ['따뜻한 무드 배경음악', '음식 브이로그 배경음악'],
    duckDuringVoice: true,
    duckVolumeRatio: 0.35,
  })),
  getSfxSuggestions: vi.fn(async () => ({
    recommendations: [
      {
        time: 12.0,
        purpose: 'RESULT_REVEAL',
        purposeLabel: '결과 공개',
        candidates: [
          { assetId: 'soft_reveal_1', label: '부드러운 결과 공개음 1', reason: '변화가 처음 보이는 순간을 자연스럽게 강조합니다.', previewUrl: '/api/sfx-preview/soft_reveal_1' },
          { assetId: 'soft_reveal_2', label: '부드러운 결과 공개음 2', reason: '변화가 처음 보이는 순간을 자연스럽게 강조합니다.', previewUrl: '/api/sfx-preview/soft_reveal_2' },
        ],
        selectedAssetId: null,
        approved: false,
      },
    ],
  })),
  updateSfxDecision: vi.fn(async (_id: string, time: number, approved: boolean, selectedAssetId: string | null) => ({
    recommendations: [
      {
        time,
        purpose: 'RESULT_REVEAL',
        purposeLabel: '결과 공개',
        candidates: [
          { assetId: 'soft_reveal_1', label: '부드러운 결과 공개음 1', reason: '변화가 처음 보이는 순간을 자연스럽게 강조합니다.', previewUrl: '/api/sfx-preview/soft_reveal_1' },
          { assetId: 'soft_reveal_2', label: '부드러운 결과 공개음 2', reason: '변화가 처음 보이는 순간을 자연스럽게 강조합니다.', previewUrl: '/api/sfx-preview/soft_reveal_2' },
        ],
        selectedAssetId,
        approved,
      },
    ],
  })),
}))

vi.mock('../api/client', () => ({
  getBgmLibrary: vi.fn(async () => ({ tracks: [{ mood: 'warm', label: '따뜻한' }, { mood: 'upbeat', label: '경쾌한' }] })),
  getBgmRecommendation,
  getSfxSuggestions,
  updateSfxDecision,
  updateAudioSettings: vi.fn(async (_id: string, settings: unknown) => settings),
  startAudio: vi.fn(async () => ({ status: 'running' })),
  getAudioStatus: vi.fn(async () => ({ status: 'done', log: [], error: null })),
  sfxPreviewUrl: (url: string) => `http://127.0.0.1:8000${url}`,
}))

// eslint-disable-next-line import/first
import { Step7Audio } from '../screens/steps/Step7Audio'

describe('Step7Audio - SFX/BGM 추천', () => {
  it('BGM 추천 메타데이터(무드/템포/에너지/키워드)를 보여준다', async () => {
    render(<Step7Audio projectId="p1" onNext={vi.fn()} />)
    const recommendationText = await screen.findByText(/AI 추천/)
    expect(recommendationText.textContent).toContain('따뜻한')
    expect(recommendationText.textContent).toContain('85~105')
    expect(screen.getByText('따뜻한 무드 배경음악')).toBeInTheDocument()
  })

  it('BGM 추천에 곡 제목이나 아티스트 같은 지어낸 정보는 절대 없다', async () => {
    render(<Step7Audio projectId="p1" onNext={vi.fn()} />)
    await waitFor(() => expect(screen.getByText(/AI 추천/)).toBeInTheDocument())
    expect(screen.queryByText(/저작권|트렌딩|아티스트/)).not.toBeInTheDocument()
  })

  it('효과음 추천 후보와 미리듣기가 렌더링된다', async () => {
    render(<Step7Audio projectId="p1" onNext={vi.fn()} />)
    await waitFor(() => expect(screen.getByText(/결과 공개/)).toBeInTheDocument())
    const audios = document.querySelectorAll('audio')
    expect(audios.length).toBe(2)
    expect(audios[0].getAttribute('src')).toBe('http://127.0.0.1:8000/api/sfx-preview/soft_reveal_1')
  })

  it('효과음 후보를 선택하면 승인 상태로 업데이트된다', async () => {
    const user = userEvent.setup()
    render(<Step7Audio projectId="p1" onNext={vi.fn()} />)
    await waitFor(() => expect(screen.getByText(/결과 공개/)).toBeInTheDocument())

    const useButtons = screen.getAllByRole('button', { name: '이 소리 사용' })
    await user.click(useButtons[0])

    await waitFor(() => expect(updateSfxDecision).toHaveBeenCalledWith('p1', 12.0, true, 'soft_reveal_1'))
  })

  it('"사용 안 함"을 누르면 approved=false로 요청한다', async () => {
    const user = userEvent.setup()
    render(<Step7Audio projectId="p1" onNext={vi.fn()} />)
    await waitFor(() => expect(screen.getByText(/결과 공개/)).toBeInTheDocument())

    await user.click(screen.getByRole('button', { name: '사용 안 함' }))

    await waitFor(() => expect(updateSfxDecision).toHaveBeenCalledWith('p1', 12.0, false, null))
  })

  it('효과음 넣기 체크를 끄면 추천 목록이 숨겨진다', async () => {
    const user = userEvent.setup()
    render(<Step7Audio projectId="p1" onNext={vi.fn()} />)
    await waitFor(() => expect(screen.getByText(/결과 공개/)).toBeInTheDocument())

    await user.click(screen.getByRole('checkbox', { name: '장면에 맞는 효과음 넣기' }))

    expect(screen.queryByText(/결과 공개/)).not.toBeInTheDocument()
  })
})
