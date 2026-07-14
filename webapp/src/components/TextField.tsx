import { useId } from 'react'
import styles from './TextField.module.css'

interface TextFieldProps {
  label: string
  value: string
  onChange: (value: string) => void
  required?: boolean
  placeholder?: string
  multiline?: boolean
  helpText?: string
}

/** 라벨과 입력을 항상 함께 표시하는 공용 텍스트 필드 (단일 행 또는 여러 행). */
export function TextField({
  label,
  value,
  onChange,
  required = false,
  placeholder,
  multiline = false,
  helpText,
}: TextFieldProps) {
  const inputId = useId()
  const helpId = useId()

  return (
    <div className={styles.field}>
      <label htmlFor={inputId} className={styles.label}>
        {label}
        {required ? (
          <span className={styles.requiredMark} aria-hidden="true">
            {' '}
            *
          </span>
        ) : (
          <span className={styles.optionalMark}> (선택)</span>
        )}
      </label>
      {multiline ? (
        <textarea
          id={inputId}
          className={styles.textarea}
          value={value}
          placeholder={placeholder}
          required={required}
          aria-describedby={helpText ? helpId : undefined}
          onChange={(e) => onChange(e.target.value)}
        />
      ) : (
        <input
          id={inputId}
          type="text"
          className={styles.input}
          value={value}
          placeholder={placeholder}
          required={required}
          aria-describedby={helpText ? helpId : undefined}
          onChange={(e) => onChange(e.target.value)}
        />
      )}
      {helpText ? (
        <p id={helpId} className={styles.helpText}>
          {helpText}
        </p>
      ) : null}
    </div>
  )
}
