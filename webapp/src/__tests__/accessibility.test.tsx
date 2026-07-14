import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { axe } from 'jest-axe'
import App from '../App'

beforeEach(() => {
  window.localStorage.clear()
})

describe('13. 접근성', () => {
  it('시작 화면에 접근성 위반이 없다', async () => {
    const { container } = render(<App />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('AUTO_EDIT 1단계(영상 불러오기) 화면에 접근성 위반이 없다', async () => {
    const user = userEvent.setup()
    const { container } = render(<App />)
    await user.click(screen.getByRole('button', { name: '영상 편집 시작' }))

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('AUTO_EDIT 2단계(카테고리 선택) 화면에 접근성 위반이 없다', async () => {
    const user = userEvent.setup()
    const { container } = render(<App />)
    await user.click(screen.getByRole('button', { name: '영상 편집 시작' }))
    await user.upload(screen.getByLabelText('영상 파일 선택'), new File(['d'], 'v.mp4', { type: 'video/mp4' }))
    await user.click(screen.getByRole('button', { name: '다음' }))

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('SHOOTING_GUIDE 입력 화면에 접근성 위반이 없다', async () => {
    const user = userEvent.setup()
    const { container } = render(<App />)
    await user.click(screen.getByRole('button', { name: '촬영 계획 만들기' }))

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('SHOOTING_GUIDE 빈 결과 화면에 접근성 위반이 없다', async () => {
    const user = userEvent.setup()
    const { container } = render(<App />)
    await user.click(screen.getByRole('button', { name: '촬영 계획 만들기' }))
    await user.type(screen.getByLabelText(/촬영 주제/), '주제')
    await user.click(screen.getByRole('button', { name: '살림' }))
    await user.type(screen.getByLabelText(/제품 또는 상황/), '상황')
    await user.selectOptions(screen.getByLabelText(/목표 영상 길이/), '1분 이내')
    await user.click(screen.getByRole('button', { name: '촬영 계획 만들기' }))

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('고급 설정(선택 입력) 펼침 상태에도 접근성 위반이 없다', async () => {
    const user = userEvent.setup()
    const { container } = render(<App />)
    await user.click(screen.getByRole('button', { name: '촬영 계획 만들기' }))
    await user.click(screen.getByRole('button', { name: /추가 정보 입력/ }))

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
