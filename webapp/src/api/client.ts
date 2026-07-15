/**
 * capcut_auto FastAPI 백엔드(server.py) 호출 클라이언트.
 * 백엔드는 로컬 프로세스로 기동되어 있어야 한다: `uvicorn capcut_auto.server:app --port 8000`
 */

const API_BASE = (import.meta as unknown as { env?: Record<string, string | undefined> }).env
  ?.VITE_API_BASE ?? 'http://127.0.0.1:8000'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {}
  if (init?.body && !(init.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json'
  }
  const res = await fetch(`${API_BASE}${path}`, { ...init, headers: { ...headers, ...(init?.headers as Record<string, string> | undefined) } })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const data = await res.json()
      detail = data.detail ?? detail
    } catch {
      // 응답 본문이 JSON이 아니면 상태 텍스트를 그대로 사용
    }
    throw new ApiError(res.status, detail)
  }
  return (await res.json()) as T
}

export interface CutCandidate {
  id: string
  start: number
  end: number
  source: 'silence' | 'filler' | 'repetition'
  enabled: boolean
}

export interface SubtitleLineDto {
  start: number
  end: number
  text: string
}

export interface ProjectSummary {
  id: string
  originalFilename: string
  category: string | null
  categoryLabel: string | null
  topic: string
  totalDuration: number | null
  keptDuration: number | null
  cutCount: number
  subtitleLineCount: number
  selectedHook: string | null
  stabilizeEnabled: boolean
  correctionApplied: boolean
  bgmMood: string | null
  bgmVolume: number
  sfxEnabled: boolean
  audioApplied: boolean
  draftName: string | null
}

export interface JobStatus {
  status: 'idle' | 'running' | 'done' | 'error'
  log: string[]
  error: string | null
}

export interface AnalyzeStatus extends JobStatus {
  totalDuration?: number
  cutCandidates?: CutCandidate[]
  keptDuration?: number
  subtitleLines?: SubtitleLineDto[]
}

export interface CorrectionStatus extends JobStatus {
  brightness?: number
  contrast?: number
  meanLuma?: number
  stabilized?: boolean
}

export interface CropWindowDto {
  x: number
  y: number
  width: number
  height: number
  zoom: number
  subjectFullyContained: boolean
}

export interface ReframeSuggestionDto {
  crop: CropWindowDto
  faceDetected: boolean
  previewUrl: string
  approved: boolean
}

export interface CutsResponse {
  cutCandidates: CutCandidate[]
  keptDuration: number
  totalDuration: number
}

export interface BgmTrackDto {
  mood: string
  label: string
}

export interface BgmRecommendationDto {
  mood: string
  moodLabel: string
  tempoRangeBpm: [number, number]
  energy: 'LOW' | 'MEDIUM' | 'HIGH'
  energyLabel: string
  hasVocals: boolean
  searchKeywords: string[]
  duckDuringVoice: boolean
  duckVolumeRatio: number
}

export interface SfxCandidateDto {
  assetId: string
  label: string
  reason: string
  previewUrl: string
}

export interface SfxRecommendationDto {
  time: number
  purpose: string
  purposeLabel: string
  candidates: SfxCandidateDto[]
  selectedAssetId: string | null
  approved: boolean
}

export interface ExportStatus extends JobStatus {
  draftName: string | null
}

export function createProject(video: File, category: string, topic = ''): Promise<ProjectSummary> {
  const form = new FormData()
  form.append('video', video)
  form.append('category', category)
  form.append('topic', topic)
  return request('/api/projects', { method: 'POST', body: form })
}

export function getProject(id: string): Promise<ProjectSummary> {
  return request(`/api/projects/${id}`)
}

export function startAnalyze(id: string): Promise<{ status: string }> {
  return request(`/api/projects/${id}/analyze`, { method: 'POST' })
}

export function getAnalyzeStatus(id: string): Promise<AnalyzeStatus> {
  return request(`/api/projects/${id}/analyze`)
}

export function getCuts(id: string): Promise<CutsResponse> {
  return request(`/api/projects/${id}/cuts`)
}

export function toggleCut(id: string, cutId: string, enabled: boolean): Promise<CutsResponse> {
  return request(`/api/projects/${id}/cuts`, { method: 'PATCH', body: JSON.stringify({ id: cutId, enabled }) })
}

export function startCorrection(id: string, stabilize: boolean): Promise<{ status: string }> {
  return request(`/api/projects/${id}/correction`, { method: 'POST', body: JSON.stringify({ stabilize }) })
}

export function getCorrectionStatus(id: string): Promise<CorrectionStatus> {
  return request(`/api/projects/${id}/correction`)
}

export function getReframeSuggestion(id: string): Promise<ReframeSuggestionDto> {
  return request(`/api/projects/${id}/reframe-suggestion`)
}

export function updateReframeApproval(id: string, approved: boolean): Promise<{ approved: boolean }> {
  return request(`/api/projects/${id}/reframe-approval`, { method: 'PATCH', body: JSON.stringify({ approved }) })
}

export function reframePreviewUrl(previewUrl: string): string {
  return `${API_BASE}${previewUrl}`
}

export function getSubtitles(id: string): Promise<{ lines: SubtitleLineDto[] }> {
  return request(`/api/projects/${id}/subtitles`)
}

export function updateSubtitles(id: string, lines: SubtitleLineDto[]): Promise<{ lines: SubtitleLineDto[] }> {
  return request(`/api/projects/${id}/subtitles`, { method: 'PATCH', body: JSON.stringify({ lines }) })
}

export function getHookSuggestions(id: string, topic: string, max = 3): Promise<{ suggestions: string[]; topic: string }> {
  const params = new URLSearchParams({ topic, max: String(max) })
  return request(`/api/projects/${id}/hooks?${params.toString()}`)
}

export function selectHook(id: string, hook: string): Promise<{ selectedHook: string }> {
  return request(`/api/projects/${id}/hook`, { method: 'PATCH', body: JSON.stringify({ hook }) })
}

export function getBgmLibrary(id: string): Promise<{ tracks: BgmTrackDto[] }> {
  return request(`/api/projects/${id}/bgm-library`)
}

export function getBgmRecommendation(id: string): Promise<BgmRecommendationDto> {
  return request(`/api/projects/${id}/bgm-recommendation`)
}

export function getSfxSuggestions(id: string): Promise<{ recommendations: SfxRecommendationDto[] }> {
  return request(`/api/projects/${id}/sfx-suggestions`)
}

export function updateSfxDecision(
  id: string,
  time: number,
  approved: boolean,
  selectedAssetId: string | null,
): Promise<{ recommendations: SfxRecommendationDto[] }> {
  return request(`/api/projects/${id}/sfx-suggestions`, {
    method: 'PATCH',
    body: JSON.stringify({ time, approved, selectedAssetId }),
  })
}

export function sfxPreviewUrl(previewUrl: string): string {
  return `${API_BASE}${previewUrl}`
}

export function updateAudioSettings(
  id: string,
  settings: { bgmMood: string | null; bgmVolume: number; sfxEnabled: boolean },
): Promise<{ bgmMood: string | null; bgmVolume: number; sfxEnabled: boolean }> {
  return request(`/api/projects/${id}/audio-settings`, { method: 'PATCH', body: JSON.stringify(settings) })
}

export function startAudio(id: string): Promise<{ status: string }> {
  return request(`/api/projects/${id}/audio`, { method: 'POST' })
}

export function getAudioStatus(id: string): Promise<JobStatus> {
  return request(`/api/projects/${id}/audio`)
}

export function getSummary(id: string): Promise<ProjectSummary> {
  return request(`/api/projects/${id}/summary`)
}

export function startExport(
  id: string,
  draftName: string,
  capcutDraftsDir?: string,
  width = 1080,
  height = 1920,
): Promise<{ status: string }> {
  return request(`/api/projects/${id}/export`, {
    method: 'POST',
    body: JSON.stringify({ draftName, capcutDraftsDir: capcutDraftsDir || null, width, height }),
  })
}

export function getExportStatus(id: string): Promise<ExportStatus> {
  return request(`/api/projects/${id}/export`)
}

export interface ShootingGuideRequest {
  topic: string
  category: string
  productOrSituation: string
  targetDuration: string
  location?: string
  equipment?: string
  faceOnCamera?: boolean
  mustShowScenes?: string
  availableTime?: string
  notes?: string
}

export interface ShotPlanDto {
  order: number
  angle: string
  angleLabel: string
  title: string
  description: string
  estimatedSeconds: number
  tip: string | null
}

export interface ShootingPlanDto {
  topic: string
  category: string
  categoryLabel: string
  targetDurationLabel: string
  totalEstimatedSeconds: number
  equipmentTips: string[]
  warnings: string[]
  shots: ShotPlanDto[]
}

export function createShootingGuide(body: ShootingGuideRequest): Promise<ShootingPlanDto> {
  return request('/api/shooting-guide', { method: 'POST', body: JSON.stringify(body) })
}

export interface ShootingGuideRequestV2 {
  topic: string
  category: string
  subject: string
  targetDurationSeconds: number
  location?: string
  equipment?: string[]
  showFace?: boolean
  availableShootingMinutes?: number
  mustShowSteps?: string[]
  additionalNotes?: string
}

export interface CameraSpecDto {
  angle: string
  distance: string
  height: string
  direction: string
  movement: string
}

export interface ShotSpecV2Dto {
  order: number
  role: string
  roleLabel: string
  description: string
  camera: CameraSpecDto
  recommendedShootingSeconds: number
  subtitleSafeZoneHint: string
  mandatory: boolean
}

export interface ShootingPlanV2Dto {
  topic: string
  category: string
  categoryLabel: string
  subject: string
  targetDurationSeconds: number
  cutCountRange: [number, number]
  shotCount: number
  equipment: string[]
  totalRecommendedShootingSeconds: number
  warnings: string[]
  shots: ShotSpecV2Dto[]
}

export function createShootingGuideV2(body: ShootingGuideRequestV2): Promise<ShootingPlanV2Dto> {
  return request('/api/shooting-guide-v2', { method: 'POST', body: JSON.stringify(body) })
}
