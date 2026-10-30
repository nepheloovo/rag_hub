// 后端 API 函数集
import { api, sseStream, uploadFile } from './client'
export { api } from './client'
import type {
  AppDoneData,
  AppGenerateDraft,
  AppReleases,
  AppReleaseCheck,
  AiDesignEvalInput,
  AiDesignEvalResponse,
  EvalRun,
  EvalDesignRulesResponse,
  MessageFeedbackInput,
  MessageFeedbackResult,
  Application,
  ChatDoneData,
  ChatMessage,
  ChunkPreview,
  Conversation,
  Doc,
  KnowledgeBase,
  LogItem,
  LogStats,
  ModelDefaults,
  ObsOverview,
  TraceRun,
  TraceDetail,
  BillingData,
  ModelPrice,
  EvalCase,
  EvalSetSummary,
  EvalSetDetail,
  EvalOverview,
  Provider,
  RetrievalChunk,
  StatsOverview,
  ToolItem
} from './types'

// ---------- 知识库 ----------
export const listKbs = () => api<KnowledgeBase[]>('/knowledge-bases')
export const createKb = (data: {
  name: string
  description?: string
  kb_type?: string
  chunk_strategy?: string
  embedding_ref?: string
}) => api<KnowledgeBase>('/knowledge-bases', { method: 'POST', body: JSON.stringify(data) })
export const getKb = (id: string) => api<KnowledgeBase>(`/knowledge-bases/${id}`)
export const updateKb = (id: string, data: Partial<KnowledgeBase>) =>
  api<KnowledgeBase>(`/knowledge-bases/${id}`, { method: 'PUT', body: JSON.stringify(data) })
export const deleteKb = (id: string) => api(`/knowledge-bases/${id}`, { method: 'DELETE' })

// ---------- 文档 ----------
export const listDocs = (kbId: string) => api<Doc[]>(`/knowledge-bases/${kbId}/documents`)
export const uploadDoc = (kbId: string, file: File, onProgress?: (p: number) => void, autoIndex = true) => {
  // auto_index=false：仅存储，预览分块后手动索引入库
  const wrapper = (path: string, f: File, cb?: (p: number) => void) =>
    uploadFile<Doc>(`${path}${path.includes('?') ? '&' : '?'}auto_index=${autoIndex}`, f, cb)
  return wrapper(`/knowledge-bases/${kbId}/documents`, file, onProgress)
}
export const deleteDoc = (docId: string) => api(`/documents/${docId}`, { method: 'DELETE' })
export const reparseDoc = (docId: string) =>
  api<Doc>(`/documents/${docId}/reparse`, { method: 'POST' })
export const indexDoc = (docId: string) => api<Doc>(`/documents/${docId}/index`, { method: 'POST' })
export const previewChunks = (docId: string, strategy?: string) =>
  api<{
    strategy: string
    strategy_label: string
    total: number
    chunks: { content: string; heading: string; page: number; kind: string }[]
    warnings: string[]
  }>(`/documents/${docId}/preview${strategy ? `?strategy=${strategy}` : ''}`, { method: 'POST' })
export const listChunks = (docId: string, limit = 20, offset = 0) =>
  api<ChunkPreview[]>(`/documents/${docId}/chunks?limit=${limit}&offset=${offset}`)
export const testRetrieval = (kbId: string, q: string) =>
  api<{ query: string; chunks: RetrievalChunk[]; models: Record<string, any> }>(
    `/knowledge-bases/${kbId}/test-retrieval?q=${encodeURIComponent(q)}`
  )

// ---------- 模型服务商 ----------
export const listProviders = () => api<Provider[]>('/providers')
export const updateProvider = (id: string, data: Partial<Provider>) =>
  api<Provider>(`/providers/${id}`, { method: 'PUT', body: JSON.stringify(data) })
export const testProvider = (id: string, modelType?: string) =>
  api<{ ok: boolean; message: string; latency_ms: number | null }>(
    `/providers/${id}/test`,
    { method: 'POST', body: JSON.stringify({ model_type: modelType ?? null }) }
  )
export const getDefaults = () => api<ModelDefaults>('/providers/defaults/models')
export const updateDefaults = (data: Partial<ModelDefaults>) =>
  api<ModelDefaults>('/providers/defaults/models', { method: 'PUT', body: JSON.stringify(data) })

// ---------- 对话 ----------
export const listConversations = (kbId?: string, appId?: string) => {
  const params = new URLSearchParams()
  if (kbId) params.set('kb_id', kbId)
  if (appId) params.set('app_id', appId)
  const qs = params.toString()
  return api<Conversation[]>(`/conversations${qs ? `?${qs}` : ''}`)
}
export const getMessages = (convId: string) => api<ChatMessage[]>(`/conversations/${convId}/messages`)
export const deleteConversation = (convId: string) =>
  api(`/conversations/${convId}`, { method: 'DELETE' })
export const streamChat = (body: { kb_id: string; query: string; role: string; conversation_id?: string | null }) =>
  sseStream<ChatDoneData | { text: string } | { message: string }>('/chat', body)

// ---------- 日志 ----------
export const listLogs = (params: { role?: string; kb_id?: string; status?: string; q?: string; page?: number; page_size?: number }) => {
  const qs = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') qs.set(k, String(v))
  })
  return api<{ total: number; page: number; page_size: number; items: LogItem[] }>(`/logs?${qs.toString()}`)
}
export const getLogStats = () => api<LogStats>('/logs/stats')

// ---------- 应用 ----------
export const listApps = () => api<Application[]>('/apps')
export const createApp = (data: {
  name: string
  description?: string
  app_type: string
  app_kind?: string
  status?: string
  category?: string
  kb_ids: string[]
}) => api<Application>('/apps', { method: 'POST', body: JSON.stringify(data) })
export const getApp = (id: string) => api<Application>(`/apps/${id}`)
export const updateApp = (id: string, data: Partial<Application>) =>
  api<Application>(`/apps/${id}`, { method: 'PUT', body: JSON.stringify(data) })
export const deleteApp = (id: string) => api(`/apps/${id}`, { method: 'DELETE' })
export const streamAppChat = (appId: string, body: { query: string; role: string; conversation_id?: string | null; draft?: boolean }) =>
  sseStream<AppDoneData | { text: string } | { message: string }>(`/apps/${appId}/chat`, body)
export const listAppConversations = (appId: string) => listConversations(undefined, appId)
export const getAppReleases = (appId: string) => api<AppReleases>(`/apps/${appId}/releases`)
export const getAppReleaseCheck = (appId: string) => api<AppReleaseCheck>(`/apps/${appId}/release-check`)
export const releaseApp = (appId: string, releaseNotes: string) =>
  api<Application>(`/apps/${appId}/release`, { method: 'POST', body: JSON.stringify({ release_notes: releaseNotes }) })
export const rollbackApp = (appId: string, versionId: string) =>
  api<Application>(`/apps/${appId}/rollback`, { method: 'POST', body: JSON.stringify({ version_id: versionId }) })
export const unpublishApp = (appId: string) =>
  api<Application>(`/apps/${appId}/unpublish`, { method: 'POST' })
export const generateApp = (description: string) =>
  api<{ draft: AppGenerateDraft; models: { llm: string; fake: boolean } }>('/apps/generate', {
    method: 'POST',
    body: JSON.stringify({ description })
  })
export const getStatsOverview = () => api<StatsOverview>('/stats/overview')
export const getStatsTrend = (days = 14) =>
  api<{ dates: string[]; calls: number[]; docs: number[]; apps: number[] }>(`/stats/trend?days=${days}`)

// ---------- 工具 ----------
export const listTools = () =>
  api<ToolItem[]>('/tools')
export const createTool = (data: { name: string; description?: string; tool_type?: string; config?: Record<string, any> }) =>
  api<ToolItem>('/tools', { method: 'POST', body: JSON.stringify(data) })
export const updateTool = (id: string, data: Partial<ToolItem>) =>
  api<ToolItem>(`/tools/${id}`, { method: 'PUT', body: JSON.stringify(data) })
export const deleteTool = (id: string) => api(`/tools/${id}`, { method: 'DELETE' })
export const testTool = (id: string, input: string) =>
  api<{ result: string }>(`/tools/${id}/test`, { method: 'POST', body: JSON.stringify({ input }) })
export const toolLogs = (id: string, limit = 20) =>
  api<any[]>(`/tools/${id}/logs?limit=${limit}`)

// ---------- 公开访问 ----------
export const getPublicApp = (id: string) =>
  api<{ id: string; name: string; description: string; app_type: string; app_kind: string; opening: string; suggested_questions: string[]; show_refs: boolean }>(`/public/apps/${id}`)
export const streamPublicChat = (appId: string, body: { query: string }) =>
  sseStream<AppDoneData | { text: string } | { message: string }>(`/public/apps/${appId}/chat`, { ...body, role: '访客' })

export const submitMessageFeedback = (messageId: string, data: MessageFeedbackInput) =>
  api<MessageFeedbackResult>(`/chat/messages/${messageId}/feedback`, { method: 'POST', body: JSON.stringify(data) })
export const submitPublicMessageFeedback = (appId: string, messageId: string, data: MessageFeedbackInput) =>
  api<MessageFeedbackResult>(`/public/apps/${appId}/messages/${messageId}/feedback`, { method: 'POST', body: JSON.stringify(data) })

// ---------- 成员与审计 ----------
export const listUsers = () => api<any[]>('/users')
export const createUser = (data: { username: string; display_name?: string; department?: string; role: string; password: string }) =>
  api('/users', { method: 'POST', body: JSON.stringify(data) })
export const updateUser = (id: string, data: Record<string, any>) =>
  api(`/users/${id}`, { method: 'PUT', body: JSON.stringify(data) })
export const listAudit = (params: { action?: string; actor?: string; page?: number; page_size?: number }) => {
  const qs = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') qs.set(k, String(v))
  })
  return api<{ total: number; items: any[] }>(`/audit?${qs.toString()}`)
}


// ---------- 可观测 ----------
export const getObsOverview = (days = 7) =>
  api<ObsOverview>(`/observability/overview?days=${days}`)

export const listTraces = (params: {
  trace_type?: string
  status?: string
  app_id?: string
  kb_id?: string
  source?: string
  q?: string
  page?: number
  page_size?: number
}) => {
  const qs = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') qs.set(k, String(v))
  })
  return api<{ total: number; page: number; page_size: number; items: TraceRun[] }>(
    `/observability/traces?${qs.toString()}`
  )
}

export const getTrace = (id: string) => api<TraceDetail>(`/observability/traces/${id}`)

export const listBuilds = (params: { kb_id?: string; status?: string; page?: number; page_size?: number }) => {
  const qs = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') qs.set(k, String(v))
  })
  return api<{ total: number; page: number; page_size: number; items: TraceRun[] }>(
    `/observability/builds?${qs.toString()}`
  )
}

export const getBilling = (days = 14) => api<BillingData>(`/observability/billing?days=${days}`)

export const listPrices = () => api<ModelPrice[]>('/observability/prices')
export const updatePrice = (model: string, data: { input_price: number; output_price: number }) =>
  api(`/observability/prices/${encodeURIComponent(model)}`, {
    method: 'PUT',
    body: JSON.stringify(data)
  })

export const traceToCase = (
  traceId: string,
  data: { label: 'good' | 'bad'; note?: string; tags?: string[]; reference_answer?: string; set_id?: string }
) =>
  api<{ case_id: string; label: string; added_to_set: boolean }>(
    `/observability/traces/${traceId}/to-case`,
    { method: 'POST', body: JSON.stringify(data) }
  )

export const loadDemoObservability = () =>
  api<{ created: boolean; message: string; traces?: number; cases?: number; sets?: number }>(
    '/observability/demo',
    { method: 'POST' }
  )

// ---------- 评测集 ----------
export const getEvalOverview = () => api<EvalOverview>('/eval/overview')

export const listCases = (params: {
  label?: string
  status?: string
  source?: string
  app_id?: string
  q?: string
  page?: number
  page_size?: number
}) => {
  const qs = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') qs.set(k, String(v))
  })
  return api<{ total: number; page: number; page_size: number; items: EvalCase[] }>(
    `/eval/cases?${qs.toString()}`
  )
}

export const createCase = (data: {
  trace_id?: string
  question?: string
  answer?: string
  reference_answer?: string
  expected_keywords?: string[]
  forbidden_keywords?: string[]
  require_citations?: boolean
  contexts?: any[]
  label?: string
  status?: string
  app_id?: string
  app_name?: string
  source?: string
  tags?: string[]
  note?: string
  set_id?: string
}) => api<{ case: EvalCase; created: boolean; added_to_set: boolean }>('/eval/cases', {
  method: 'POST',
  body: JSON.stringify(data)
})

export const updateCase = (id: string, data: Record<string, any>) =>
  api<EvalCase>(`/eval/cases/${id}`, { method: 'PATCH', body: JSON.stringify(data) })

export const deleteCase = (id: string) => api(`/eval/cases/${id}`, { method: 'DELETE' })

export const listEvalSets = () => api<EvalSetSummary[]>('/eval/sets')
export const createEvalSet = (data: { name: string; description?: string; case_ids?: string[]; app_id?: string; is_release_gate?: boolean }) =>
  api<EvalSetSummary>('/eval/sets', { method: 'POST', body: JSON.stringify(data) })
export const getEvalSet = (id: string) => api<EvalSetDetail>(`/eval/sets/${id}`)
export const updateEvalSet = (id: string, data: { name?: string; description?: string; app_id?: string; is_release_gate?: boolean }) =>
  api<EvalSetSummary>(`/eval/sets/${id}`, { method: 'PATCH', body: JSON.stringify(data) })
export const deleteEvalSet = (id: string) => api(`/eval/sets/${id}`, { method: 'DELETE' })
export const addCasesToSet = (setId: string, caseIds: string[]) =>
  api<{ added: number; set: EvalSetSummary }>(`/eval/sets/${setId}/cases`, {
    method: 'POST',
    body: JSON.stringify({ case_ids: caseIds })
  })
export const removeCaseFromSet = (setId: string, caseId: string) =>
  api(`/eval/sets/${setId}/cases/${caseId}`, { method: 'DELETE' })

export const createEvalRun = (setId: string) =>
  api<EvalRun>(`/eval/sets/${setId}/runs`, { method: 'POST' })
export const stepEvalRun = (setId: string, runId: string) =>
  api<EvalRun>(`/eval/sets/${setId}/runs/${runId}/step`, { method: 'POST' })
export const runEvalSet = (setId: string) =>
  api<EvalRun>(`/eval/sets/${setId}/run`, { method: 'POST' })
export const listEvalRuns = (setId: string, limit = 10) =>
  api<EvalRun[]>(`/eval/sets/${setId}/runs?limit=${limit}`)
export const getEvalDesignRules = (appId: string) =>
  api<EvalDesignRulesResponse>(`/eval/design-rules?app_id=${encodeURIComponent(appId)}`)
export const aiDesignEval = (data: AiDesignEvalInput) =>
  api<AiDesignEvalResponse>('/eval/ai-design', { method: 'POST', body: JSON.stringify(data) })
