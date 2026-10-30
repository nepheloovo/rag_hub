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
  trace_id?: string
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
  app_id?: string
  app_name?: string
  query: string
  answer: string
  llm_model: string
  embedding_model: string
  rerank_model: string
  tokens: { embedding: number; rerank: number; llm: number; total: number }
  duration_ms: number
  status: 'success' | 'error'
  trace_id?: string
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
  flow: { nodes: any[]; edges: any[] } | null
  flow_history: Record<string, any>
  publish_enabled: boolean
  visitor_daily_limit: number
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

// ---------- 工具 ----------
export interface ToolItem {
  id: string
  name: string
  description: string
  tool_type: string
  status: string
  enabled: boolean
  call_count: number
  last_called_at: string | null
  used_by_apps: string[]
  created_at: string
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
  trace_id?: string
}

// ---------- 可观测 ----------
export interface TraceTokens {
  input?: number
  output?: number
  total?: number
  embedding?: number
  rerank?: number
  llm?: number
}

export interface TraceRun {
  id: string
  trace_type: 'chat' | 'agent' | 'chatflow' | 'kb_build'
  title: string
  query: string
  answer: string
  status: 'running' | 'success' | 'error' | 'degraded'
  app_id: string
  app_name: string
  app_kind: string
  kb_id: string
  kb_name: string
  conversation_id: string
  message_id: string
  role: string
  source: string
  model: string
  models: Record<string, string>
  tokens: TraceTokens
  cost_cny: number
  duration_ms: number
  span_count: number
  started_at: string
  error: string
  metadata: Record<string, any>
  cases?: { id: string; label: string }[]
  context?: Record<string, any>
  stages?: TraceSpan[]
}

export interface CodeExplainBlock {
  lines: number[]
  title: string
  text: string
}

export interface TraceSpan {
  id: string
  trace_id: string
  parent_id: string
  seq: number
  depth: number
  span_type: string
  name: string
  status: 'running' | 'success' | 'error' | 'skipped' | 'degraded'
  started_offset_ms: number
  duration_ms: number
  input: any
  output: any
  tokens: Record<string, any>
  cost_cny: number
  context: Record<string, any>
  error: string
  error_hint: string
  code_key: string
  code: string
  code_explain: CodeExplainBlock[]
  metadata: Record<string, any>
}

export interface TraceDetail extends TraceRun {
  spans: TraceSpan[]
  cases: { id: string; label: string; note: string; tags: string[]; created_at: string }[]
  metrics: { llm_tokens: number; embedding_tokens: number; rerank_tokens: number }
}

export interface ObsOverview {
  days: number
  total: number
  success: number
  error: number
  degraded: number
  success_rate: number
  p95_duration_ms: number
  avg_duration_ms: number
  tokens: number
  cost_cny: number
  agent_runs: number
  tool_calls: number
  tool_errors: number
  trend: { date: string; total: number; success: number; error: number; tokens: number; cost_cny: number }[]
  types: { type: string; count: number }[]
  top_apps: { app_name: string; count: number; cost_cny: number }[]
  skills: { name: string; count: number }[]
}

export interface BillingData {
  days: number
  total_cost_cny: number
  total_tokens: number
  calls: number
  by_day: { date: string; cost_cny: number; input: number; output: number; calls: number }[]
  by_app: { app_name: string; calls: number; cost_cny: number; tokens: number }[]
  by_model: { model: string; cost_cny: number; input: number; output: number; spans: number }[]
  by_purpose: { type: string; calls: number; cost_cny: number; tokens: number }[]
}

export interface ModelPrice {
  model: string
  input_price: number
  output_price: number
  currency: string
  updated_at: string
}

// ---------- 评测集 ----------
export interface EvalCase {
  id: string
  question: string
  answer: string
  reference_answer: string
  contexts: any[]
  label: 'good' | 'bad'
  status: string
  app_id: string
  app_name: string
  source: string
  trace_id: string
  tags: string[]
  note: string
  created_by: string
  created_at: string
  updated_at: string
  sets?: { id: string; name: string }[]
}

export interface EvalSetSummary {
  id: string
  name: string
  description: string
  created_by: string
  created_at: string
  updated_at: string
  case_count: number
  good_count: number
  bad_count: number
  apps: string[]
  tags: string[]
}

export interface EvalSetDetail extends EvalSetSummary {
  cases: EvalCase[]
}

export interface EvalOverview {
  case_count: number
  good_count: number
  bad_count: number
  set_count: number
  new_this_week: number
  unassigned: number
  top_tags: { tag: string; count: number }[]
  top_apps: { app_name: string; count: number }[]
}
