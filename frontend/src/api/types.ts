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
  /** 逐文件切块配置，空对象 = 知识库默认 */
  chunk_config: Partial<ChunkConfig>
  created_at: string
  updated_at: string
}

export type ChunkStrategy = 'smart' | 'heading' | 'separator' | 'fixed' | 'parent_child' | 'semantic' | 'qa_split' | 'page' | 'table_row'

export interface ChunkConfig {
  strategy: ChunkStrategy
  chunk_size: number
  chunk_overlap: number
  separator: string
  enhance_keywords: boolean
  enhance_qa: boolean
}

export interface QaPair {
  q: string
  a: string
}

export interface ChunkPreview {
  id: string
  content: string
  source: string
  page: number
  heading: string
  kind?: string
  keywords?: string[]
  qa_pairs?: QaPair[]
}

export interface RetrievalChunk extends ChunkPreview {
  doc_id: string
  score: number
}

export type RetrievalMode = 'semantic' | 'fulltext' | 'hybrid'

export interface RetrievalOptions {
  mode: RetrievalMode
  top_k: number
  top_n: number
  score_threshold: number
  rerank: boolean
}

export interface ChunkPreviewResult {
  strategy: string
  strategy_label: string
  config: ChunkConfig
  total: number
  avg_chars: number
  max_chars: number
  chunks: { content: string; heading: string; page: number; kind: string }[]
  warnings: string[]
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
  feedback: FeedbackRating
}

export type FeedbackRating = 1 | -1 | 0
export interface MessageFeedbackInput {
  rating: FeedbackRating
  comment?: string
}
export interface MessageFeedbackResult {
  ok: boolean
  rating: FeedbackRating
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
  /** 回答反馈：-1 点踩 / 1 点赞 / 0 无 */
  feedback?: -1 | 0 | 1
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
export type AppStatus = 'draft' | 'published' | 'offline'

export interface Application {
  id: string
  name: string
  description: string
  app_type: AppType
  app_kind: AppKind
  status: AppStatus
  published_version_id: string | null
  published_version: number | null
  draft_dirty: boolean
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
  /** 检索参数，空对象 = 全局默认 */
  retrieval: Partial<RetrievalOptions>
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

export interface AppReleaseVersion {
  id: string
  version: number
  release_notes: string
  fingerprint: string
  created_by: string
  created_at: string
  is_published: boolean
}

export interface AppReleases {
  published_version_id: string | null
  status: AppStatus
  draft_fingerprint: string
  draft_dirty: boolean
  versions: AppReleaseVersion[]
}

export interface AppReleaseGate {
  set_id: string
  set_name: string
  passed: boolean
  reason: string
  latest_run: EvalRunSummary | null
}

export interface AppReleaseCheck {
  issues: string[]
  gates: AppReleaseGate[]
  can_release: boolean
  draft_dirty: boolean
}

export interface StatsOverview {
  month_app_calls: number
  month_new_docs: number
  month_new_apps: number
  kb_count: number
  app_count: number
  published_count: number
  /** 近 30 天满意度（%），无反馈为 null */
  satisfaction: number | null
  like_count: number
  dislike_count: number
  /** 近 30 天知识命中率（%），无数据为 null */
  hit_rate: number | null
  miss_count: number
}

export interface KnowledgeGap {
  key: string
  question: string
  count: number
  dislike_count: number
  miss_count: number
  apps: string[]
  kb_names: string[]
  kb_ids: string[]
  sample_questions: string[]
  last_time: string
}

export interface BadFeedbackItem {
  message_id: string
  trace_id: string
  app_id: string
  app_name: string
  question: string
  answer: string
  comment: string
  user_id: string
  time: string
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
  expected_keywords: string[]
  forbidden_keywords: string[]
  require_citations: boolean
  readiness: 'ready' | 'needs_standard'
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
  app_id: string
  app_name: string
  is_release_gate: boolean
  latest_run: EvalRunSummary | null
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

export interface EvalRunResult {
  case_id: string
  question: string
  passed: boolean
  reasons: string[]
  output: string
  refs_count: number
  simulated: boolean
}

export interface EvalRunSummary {
  id: string
  status: 'running' | 'success' | 'failed'
  passed_count: number
  failed_count: number
  total_count: number
  done_count: number
  simulated: boolean
  created_at: string
  matches_draft: boolean
  results: EvalRunResult[]
}

export type EvalRun = EvalRunSummary

export interface EvalDesignRule {
  key: string
  name: string
  description: string
  scenes: string[]
}

export interface EvalDesignRulesResponse {
  rules: EvalDesignRule[]
  default_keys: string[]
}

export interface AiDesignEvalInput {
  app_id: string
  set_id?: string
  set_name?: string
  rule_keys: string[]
  directions: string
  count: number
}

export interface AiDesignEvalResponse {
  set: EvalSetSummary
  cases: EvalCase[]
  simulated: boolean
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
