import { useState } from 'react'
import { Button } from '../../components/Button'
import { CollapsibleSection } from '../../components/CollapsibleSection'
import { StatusMessage } from '../../components/StatusMessage'
import { TextField } from '../../components/TextField'
import { getExportStatus, startExport } from '../../api/client'
import { useJobPolling } from '../../hooks/useJobPolling'
import placeholderStyles from './StepCommon.module.css'

interface Step9ExportProps {
  projectId: string
  onFinished: () => void
}

/** 9단계: CapCut 드래프트로 내보낸다. */
export function Step9Export({ projectId, onFinished }: Step9ExportProps) {
  const [draftName, setDraftName] = useState('내_영상_편집본')
  const [draftsDir, setDraftsDir] = useState('')

  const { data, error, isPolling, start } = useJobPolling(
    () => startExport(projectId, draftName, draftsDir || undefined),
    () => getExportStatus(projectId),
  )

  return (
    <div>
      <p className="screen-description">CapCut에서 바로 열어볼 수 있는 드래프트로 내보내요.</p>

      <TextField label="드래프트 이름" required value={draftName} onChange={setDraftName} />

      <CollapsibleSection title="고급 설정 (선택)">
        <TextField
          label="CapCut 드래프트 폴더 경로"
          value={draftsDir}
          onChange={setDraftsDir}
          placeholder="비워두면 자동으로 찾습니다"
          helpText="이 서버가 실행 중인 PC의 CapCut 드래프트 폴더 경로입니다."
        />
      </CollapsibleSection>

      {!data && !isPolling ? (
        <Button onClick={start} disabled={!draftName.trim()} className={placeholderStyles.nextButton}>
          내보내기
        </Button>
      ) : null}

      {isPolling ? (
        <div className={placeholderStyles.body}>
          <StatusMessage variant="info">CapCut 드래프트를 만드는 중입니다...</StatusMessage>
        </div>
      ) : null}

      {error ? (
        <div className={placeholderStyles.body}>
          <StatusMessage variant="warning">{error}</StatusMessage>
          <Button variant="secondary" onClick={start}>
            다시 시도
          </Button>
        </div>
      ) : null}

      {data?.status === 'done' ? (
        <div className={placeholderStyles.body}>
          <StatusMessage variant="success">
            내보내기 완료! CapCut에서 "{data.draftName}" 드래프트를 열어보세요.
          </StatusMessage>
        </div>
      ) : null}

      <Button onClick={onFinished} disabled={data?.status !== 'done'} className={placeholderStyles.nextButton}>
        완료하고 처음으로
      </Button>
    </div>
  )
}
