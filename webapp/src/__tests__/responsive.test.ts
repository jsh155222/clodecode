import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const currentDir = dirname(fileURLToPath(import.meta.url))

/**
 * jsdom은 실제 레이아웃(box model)을 계산하지 않으므로 픽셀 단위를 런타임에서
 * 직접 측정할 수 없다. 대신 UI 원칙에 명시된 수치가 CSS 소스에 실제로
 * 인코딩되어 있는지를 검증한다 (디자인 의도가 코드에 반영됐는지 확인).
 */
function readCss(relativePath: string): string {
  return readFileSync(join(currentDir, '..', relativePath), 'utf-8')
}

describe('11-12. 모바일/태블릿 레이아웃 - 디자인 토큰', () => {
  const tokens = readCss('styles/tokens.css')

  it('터치 영역 최소 44px가 정의되어 있다', () => {
    expect(tokens).toMatch(/--touch-target-min:\s*44px/)
  })

  it('주요 버튼 높이 최소 48px가 정의되어 있다', () => {
    expect(tokens).toMatch(/--button-height-min:\s*48px/)
  })

  it('본문 글자 크기가 15~17px 범위로 정의되어 있다', () => {
    expect(tokens).toMatch(/--font-body:\s*clamp\(15px,.*17px\)/)
  })

  it('화면 제목 글자 크기가 22~28px 범위로 정의되어 있다', () => {
    expect(tokens).toMatch(/--font-title:\s*clamp\(22px,.*28px\)/)
  })

  it('카드 내부 여백이 16px 이상이다', () => {
    const match = tokens.match(/--card-padding:\s*(\d+)px/)
    expect(match).not.toBeNull()
    expect(Number(match![1])).toBeGreaterThanOrEqual(16)
  })

  it('섹션 간격이 24px 이상이다', () => {
    const match = tokens.match(/--section-gap-min:\s*(\d+)px/)
    expect(match).not.toBeNull()
    expect(Number(match![1])).toBeGreaterThanOrEqual(24)
  })
})

describe('11-12. 모바일/태블릿 레이아웃 - 반응형 브레이크포인트', () => {
  const global = readCss('styles/global.css')

  it('모바일 브레이크포인트(최대 599px)에서 카드가 1열로 쌓인다', () => {
    expect(global).toMatch(/@media \(max-width: 599px\)/)
    expect(global).toMatch(/flex-direction:\s*column/)
  })

  it('태블릿 이상(최소 600px)에서 카드가 2열 그리드로 배치된다', () => {
    expect(global).toMatch(/@media \(min-width: 600px\)/)
    expect(global).toMatch(/grid-template-columns:\s*repeat\(2, 1fr\)/)
  })
})

describe('11-12. 모바일/태블릿 레이아웃 - 컴포넌트별 터치 영역 적용', () => {
  const components = [
    'components/Button.module.css',
    'components/CategoryCard.module.css',
    'components/CollapsibleSection.module.css',
    'components/StepHeader.module.css',
    'components/TextField.module.css',
  ]

  it.each(components)('%s가 --touch-target-min을 사용한다', (path) => {
    const css = readCss(path)
    expect(css).toMatch(/var\(--touch-target-min\)/)
  })
})
