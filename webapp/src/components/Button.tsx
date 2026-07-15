import type { ButtonHTMLAttributes, ReactNode } from 'react'
import styles from './Button.module.css'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary'
  children: ReactNode
}

/** 주요 버튼 높이 최소 48px, 터치 영역 최소 44x44px을 보장하는 공용 버튼. */
export function Button({ variant = 'primary', className, children, ...rest }: ButtonProps) {
  const variantClass = variant === 'primary' ? styles.primary : styles.secondary
  const classes = className ? `${styles.button} ${variantClass} ${className}` : `${styles.button} ${variantClass}`
  return (
    <button className={classes} {...rest}>
      {children}
    </button>
  )
}
