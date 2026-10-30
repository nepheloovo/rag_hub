// 切块配置：方式说明 + 按文件格式推荐默认值（导入、重新切块共用）
import type { ChunkConfig, ChunkStrategy } from '@/api/types'

export const STRATEGIES: { value: ChunkStrategy; label: string; desc: string; fit: string }[] = [
  { value: 'smart', label: '智能分块', desc: '识别标题和段落结构，自动递归切分到合适长度', fit: '大多数文档，推荐默认' },
  { value: 'heading', label: '按标题层级', desc: '按 H1–H3 切分，每块保留标题路径', fit: '手册、制度、规范' },
  { value: 'separator', label: '自定义分隔符', desc: '按指定符号切分，如空行、### 或「第X条」', fit: '格式规整的条款、清单' },
  { value: 'fixed', label: '固定长度', desc: '按字数和重叠量机械切分', fit: '无结构的长文本、转写稿' },
  { value: 'parent_child', label: '父子分块', desc: '小块精准召回，命中后返回所在大块作为上下文', fit: '长篇研报、技术文档' },
  { value: 'semantic', label: '语义分块', desc: '相邻段落语义突变处断开，按主题切分', fit: '主题跳跃的长文、访谈纪要' },
  { value: 'qa_split', label: '问答对拆分', desc: '由模型从文档中提取「问题-答案」，按问答对索引', fit: 'FAQ、客服、培训材料' },
  { value: 'page', label: '按页切分', desc: 'PDF 一页一块，保留页码', fit: '幻灯片、扫描件、图表多的报告' },
  { value: 'table_row', label: '表格按行', desc: 'Excel / CSV 每行一块，表头作为每行的上下文', fit: '参数表、价格表、FAQ 表格' }
]

export const STRATEGY_NAME: Record<string, string> = Object.fromEntries(STRATEGIES.map(s => [s.value, s.label]))

export const SEPARATOR_PRESETS = [
  { label: '空行', value: '\n\n' },
  { label: '换行', value: '\n' },
  { label: '「第X条」', value: 're:(?=第[一二三四五六七八九十百]+条)' },
  { label: '二级标题 ##', value: '\n## ' },
  { label: '分号 ；', value: '；' }
]

export function defaultChunkConfig(strategy: ChunkStrategy = 'smart'): ChunkConfig {
  return { strategy, chunk_size: 600, chunk_overlap: 80, separator: '', enhance_keywords: false, enhance_qa: false }
}

/** 按扩展名推荐切块方式：PDF 按页、Markdown/Word 按标题、表格按行 */
export function recommendStrategy(filename: string, fallback: ChunkStrategy = 'smart'): ChunkStrategy {
  const ext = filename.toLowerCase().split('.').pop() || ''
  if (ext === 'pdf') return 'page'
  if (['md', 'markdown', 'docx', 'doc'].includes(ext)) return 'heading'
  if (['xlsx', 'xls', 'csv'].includes(ext)) return 'table_row'
  return fallback
}

export function recommendedConfig(filename: string, base?: Partial<ChunkConfig>): ChunkConfig {
  return { ...defaultChunkConfig(recommendStrategy(filename)), ...(base || {}) }
}

export function fileExt(filename: string) {
  return filename.toLowerCase().split('.').pop() || ''
}
