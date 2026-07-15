import { useId } from 'react'
import styles from './TextField.module.css'

interface SelectFieldProps {
  label: string
  value: string
  onChange: (value: string) => void
  options: { value: string; label: string }[]
  required?: boolean
}

/** TextField와 동일한 라벨/여백 규칙을 공유하는 선택형 필드. */
export function SelectField({ label, value, onChange, options, required = false }: SelectFieldProps) {
  const inputId = useId()
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
      <select id={inputId} className={styles.input} value={value} required={required} onChange={(e) => onChange(e.target.value)}>
        <option value="" disabled>
          선택해주세요
        </option>
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
    </div>
  )
}
