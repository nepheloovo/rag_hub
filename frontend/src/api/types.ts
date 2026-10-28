// 与后端 API 对齐的类型定义

export interface KnowledgeBase {
  id: string
  name: string
  description: string
  kb_type: string
  chunk_strategy: string
  status: string
  embedding_ref: string
  doc_count: number
  chunk_count: number
  used_by_apps: string[]
  created_at: string
  updated_at: string
}

export interface Doc {
  id: string
  kb_id: string
  filename: string
  file_type: string
  file_size: number
  status: 'pending' | 'parsing' | 'done' | 'failed'
  error: string
  chunk_count: number
  created_at: string
  updated_at: string
}

export interface ChunkPreview {
  id: string
  content: string
  source: string
  page: number
  heading: string
}

export interface RetrievalChunk extends ChunkPreview {
  doc_id: string
  score: number
}

export interface Provider {
  id: string
  name: string
  provider_type: string
  base_url: string
  api_key: string
  enabled: boolean
  models: { embedding: string[]; rerank: string[]; llm: string[] }
  created_at?: string
  updated_at?: string
}

export interface ModelDefaults {
  default_embedding: string
  default_rerank: string
  default_llm: string
}

export interface RefItem {
  doc_id: string
  title: string
  page: number
  snippet: string
  score: number | null
}

export interface ChatDoneData {
  refs: RefItem[]
  tokens: { embedding: number; rerank: number; llm: number; total: number }
  duration_ms: number
  message_id: string
  conversation_id: string
  answer: string
  models: { llm: string; embedding: string; rerank: string; fake: boolean }
}

export interface Conversation {
  id: string
  kb_id: string
  app_id?: string | null
  role: string
  title: string
  created_at: string
}

export interface ChatMessage {
  id: string
  conv_id: string
  role: 'user' | 'assistant'
  content: string
  refs: RefItem[]
  created_at: string
}

export interface LogItem {
  id: string
  time: string
  role: string
  kb_id: string
  kb_name: string
  query: string
  answer: string
  llm_model: string
  embedding_model: string
  rerank_model: string
  tokens: { embedding: number; rerank: number; llm: number; total: number }
  duration_ms: number
  status: 'success' | 'error'
}

export interface LogStats {
  today_count: number
  today_tokens: number
  avg_duration_ms: number
  success_rate: number
  trend: { date: string; count: number }[]
}

// ---------- 应用 ----------
export type AppType = 'qa' | 'service' | 'report'
export type AppKind = 'simple' | 'chatflow' | 'agent'
export type AppStatus = 'draft' | 'reviewing' | 'published'

export interface Application {
  id: string
  name: string
  description: string
  app_type: AppType
  app_kind: AppKind
  status: AppStatus
  version: number
  category: string
  kb_ids: string[]
  llm_ref: string
  system_prompt: string
  temperature: number
  show_refs: boolean
  opening: string
  suggested_questions: string[]
  fallback_reply: string
  transfer_hint: string
  call_count_7d: number
  created_at: string
  updated_at: string
}

export interface AppGenerateDraft {
  name: string
  app_type: AppType
  category: string
  description: string
  system_prompt: string
  opening: string
  suggested_questions: string[]
}

export interface StatsOverview {
  month_app_calls: number
  month_new_docs: number
  month_new_apps: number
  kb_count: number
  app_count: number
  published_count: number
}

export interface AppDoneData {
  refs: RefItem[]
  tokens: { embedding: number; rerank: number; llm: number; total: number }
  duration_ms: number
  message_id: string
  conversation_id: string
  answer: string
  app: Record<string, any>
  models: { llm: string; embedding: string; rerank: string; fake: boolean }
}
