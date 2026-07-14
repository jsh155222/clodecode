import { useEffect, useState } from 'react'
import { Button } from '../../components/Button'
import { StatusMessage } from '../../components/StatusMessage'
import { TextField } from '../../components/TextField'
import {
  getHookSuggestions,
  getSubtitles,
  selectHook,
  updateSubtitles,
  type SubtitleLineDto,
} from '../../api/client'
import { formatTime } from '../../utils/formatTime'
import placeholderStyles from './StepCommon.module.css'
import styles from './Step6SubtitlesHook.module.css'

interface Step6SubtitlesHookProps {
  projectId: string
  onNext: () => void
}

/** 6단계: 자동 생성된 자막을 검토/수정하고, 도입부 훅 문구를 고른다. */
export function Step6SubtitlesHook({ projectId, onNext }: Step6SubtitlesHookProps) {
  const [lines, setLines] = useState<SubtitleLineDto[]>([])
  const [loading, setLoading] = useState(true)
  const [topic, setTopic] = useState('')
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [hookLoading, setHookLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getSubtitles(projectId)
      .then((res) => setLines(res.lines))
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false));
  }, [projectId]);

  const updateLineText = (index: number, text: string) => {
    setLines((prev) => prev.map((line, i) => (i === index ? { ...line, text } : line)));
  };

  const handleGenerateHooks = async () => {
    if (!topic.trim()) return;
    setHookLoading(true);
    setError(null);
    try {
      const res = await getHookSuggestions(projectId, topic, 3);
      setSuggestions(res.suggestions);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setHookLoading(false);
    }
  };

  const handleSelectHook = async (hook: string) => {
    setSelected(hook);
    try {
      await selectHook(projectId, hook);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const handleNext = async () => {
    try {
      await updateSubtitles(projectId, lines);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      return;
    }
    onNext();
  };

  return (
    <div>
      <p className="screen-description">자막을 확인하고, 영상 맨 앞에 넣을 훅 문구를 골라주세요.</p>

      {error ? (
        <div className={placeholderStyles.body}>
          <StatusMessage variant="warning">{error}</StatusMessage>
        </div>
      ) : null}

      <h2 className={styles.sectionTitle}>훅 문구</h2>
      <TextField label="영상 주제" value={topic} onChange={setTopic} placeholder="예: 원룸 정리 루틴" />
      <Button variant="secondary" onClick={handleGenerateHooks} disabled={!topic.trim() || hookLoading}>
        훅 문구 추천받기
      </Button>
      {suggestions.length > 0 ? (
        <ul className={styles.hookList}>
          {suggestions.map((s) => (
            <li key={s}>
              <button
                type="button"
                className={`${styles.hookOption} ${selected === s ? styles.hookSelected : ''}`}
                onClick={() => handleSelectHook(s)}
                aria-pressed={selected === s}
              >
                {s}
              </button>
            </li>
          ))}
        </ul>
      ) : null}

      <h2 className={styles.sectionTitle}>자막</h2>
      {loading ? (
        <StatusMessage variant="info">불러오는 중...</StatusMessage>
      ) : (
        <ul className={styles.subtitleList}>
          {lines.map((line, i) => (
            <li key={`${line.start}-${i}`} className={styles.subtitleRow}>
              <span className={styles.timeRange}>
                {formatTime(line.start)} - {formatTime(line.end)}
              </span>
              <textarea
                className={styles.subtitleInput}
                value={line.text}
                onChange={(e) => updateLineText(i, e.target.value)}
                aria-label={`${formatTime(line.start)} 자막`}
              />
            </li>
          ))}
          {lines.length === 0 ? <li className={styles.empty}>생성된 자막이 없어요.</li> : null}
        </ul>
      )}

      <Button onClick={handleNext} className={placeholderStyles.nextButton}>
        다음
      </Button>
    </div>
  )
}
