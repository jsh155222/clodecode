import { useRef, useState } from 'react'
import { FileVideo, Upload } from 'lucide-react'
import { Button } from '../../components/Button'
import cardStyles from '../../components/Card.module.css'
import styles from './Step1UploadVideo.module.css'

interface Step1UploadVideoProps {
  fileName: string | null
  onFileSelected: (fileName: string) => void
  onNext: () => void
}

/**
 * 1단계: 영상 불러오기.
 * 이번 단계에서는 실제 업로드/처리 로직은 연결하지 않고, 파일 선택 UI만 제공한다.
 */
export function Step1UploadVideo({ fileName, onFileSelected, onNext }: Step1UploadVideoProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragOver, setDragOver] = useState(false)

  const handleFiles = (files: FileList | null) => {
    const file = files?.[0]
    if (file) onFileSelected(file.name)
  }

  return (
    <div>
      <p className="screen-description">편집할 영상 파일을 선택해주세요.</p>
      <div
        className={`${cardStyles.card} ${styles.dropzone} ${dragOver ? styles.dragOver : ''}`}
        onDragOver={(e) => {
          e.preventDefault()
          setDragOver(true)
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault()
          setDragOver(false)
          handleFiles(e.dataTransfer.files)
        }}
      >
        {fileName ? (
          <>
            <FileVideo size={32} aria-hidden="true" />
            <p className={styles.fileName}>{fileName}</p>
          </>
        ) : (
          <>
            <Upload size={32} aria-hidden="true" />
            <p>여기로 영상을 끌어다 놓거나</p>
          </>
        )}
        <Button variant="secondary" onClick={() => inputRef.current?.click()}>
          {fileName ? '다른 영상 선택' : '영상 파일 선택'}
        </Button>
        <input
          ref={inputRef}
          type="file"
          accept="video/*"
          className="visually-hidden"
          aria-label="영상 파일 선택"
          onChange={(e) => handleFiles(e.target.files)}
        />
      </div>
      <Button onClick={onNext} disabled={!fileName} className={styles.nextButton}>
        다음
      </Button>
    </div>
  )
}
