// 后端 API 函数集
import { api, sseStream, uploadFile } from './client'
import type {
  AppDoneData,
  AppGenerateDraft,
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
  Provider,
  RetrievalChunk,
  StatsOverview
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
export const streamAppChat = (appId: string, body: { query: string; role: string; conversation_id?: string | null }) =>
  sseStream<AppDoneData | { text: string } | { message: string }>(`/apps/${appId}/chat`, body)
export const listAppConversations = (appId: string) => listConversations(undefined, appId)
export const generateApp = (description: string) =>
  api<{ draft: AppGenerateDraft; models: { llm: string; fake: boolean } }>('/apps/generate', {
    method: 'POST',
    body: JSON.stringify({ description })
  })
export const getStatsOverview = () => api<StatsOverview>('/stats/overview')
