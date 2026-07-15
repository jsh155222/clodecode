import { Clapperboard, Compass } from 'lucide-react'
import { ModeCard } from '../components/ModeCard'
import type { AppMode } from '../types'

interface StartScreenProps {
  onSelectMode: (mode: AppMode) => void
}

/** 앱 첫 화면: 두 개의 큰 모드 카드만 보여준다. */
export function StartScreen({ onSelectMode }: StartScreenProps) {
  return (
    <div>
      <h1 className="screen-title">어떤 작업을 하시겠어요?</h1>
      <div className="card-grid" style={{ marginTop: 20 }}>
        <ModeCard
          icon={<Clapperboard size={24} />}
          title="AI 자동 편집"
          description="영상을 불러오면 무음, 말실수, 자막과 화면을 자동으로 정리합니다."
          buttonLabel="영상 편집 시작"
          onSelect={() => onSelectMode('AUTO_EDIT')}
        />
        <ModeCard
          icon={<Compass size={24} />}
          title="AI 촬영 가이드"
          description="촬영 주제를 입력하면 필요한 앵글과 촬영 순서를 알려드립니다."
          buttonLabel="촬영 계획 만들기"
          onSelect={() => onSelectMode('SHOOTING_GUIDE')}
        />
      </div>
    </div>
  )
}
