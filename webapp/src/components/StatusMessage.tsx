import type { ReactNode } from 'react'
import { CheckCircle2, Info, AlertTriangle } from 'lucide-react'
import styles from './StatusMessage.module.css'

interface StatusMessageProps {
  variant: 'info' | 'success' | 'warning'
  children: ReactNode
}

const ICONS = {
  info: Info,
  success: CheckCircle2,
  warning: AlertTriangle,
} as const

/** 상태를 색상+아이콘+문구 세 가지를 함께 사용해 표시한다 (색상만으로 구분하지 않음). */
export function StatusMessage({ variant, children }: StatusMessageProps) {
  const Icon = ICONS[variant]
  return (
    <div className={`${styles.status} ${styles[variant]}`} role="status">
      <Icon size={20} aria-hidden="true" />
      <span>{children}</span>
    </div>
  )
}
