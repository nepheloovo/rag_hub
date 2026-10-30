<template>
  <div class="eval-run-panel" :aria-busy="running">
    <div class="run-toolbar">
      <div class="run-summary">
        <template v-if="current">
          <n-tag size="small" :bordered="false" :type="current.status === 'running' ? 'info' : current.failed_count ? 'error' : 'success'">
            {{ current.status === 'running' ? (running ? '评测中' : '评测未完成') : `${current.passed_count} 通过 / ${current.failed_count} 未通过` }}
          </n-tag>
          <n-tag v-if="current.simulated" size="tiny" :bordered="false" type="warning">模拟运行</n-tag>
          <span class="run-time">{{ formatTime(current.created_at) }}</span>
        </template>
        <span v-else class="muted">尚未运行评测</span>
      </div>
      <div class="run-actions">
        <n-button v-if="current?.status === 'running' && current.matches_draft && !error" size="small" :disabled="running || !appId || disabled" @click="resume">
          继续评测
        </n-button>
        <n-button size="small" type="primary" ghost :loading="running" :disabled="!appId || loading || disabled" @click="start">
          <template #icon><n-icon><PlayOutline /></n-icon></template>
          {{ running ? '评测中…' : current ? '重新运行' : '运行评测' }}
        </n-button>
      </div>
    </div>

    <p v-if="!appId" class="run-hint">先绑定应用，再基于应用草稿运行评测。</p>
    <p v-else class="run-hint">按当前草稿逐条评测，待补标准的 Case 会跳过。运行期间请勿修改应用草稿或评测标准。</p>

    <n-alert v-if="error" type="error" :show-icon="false" class="run-alert">
      {{ error }}
      <div class="alert-hint">已停止后续评测，请确认问题后重新运行。</div>
    </n-alert>
    <n-alert v-if="current?.matches_draft === false" type="warning" :show-icon="false" class="run-alert">
      应用草稿已修改，本次结果不适用于当前草稿，请重新运行。
    </n-alert>
    <n-alert v-if="current?.simulated" type="warning" :show-icon="false" class="run-alert">
      当前结果来自模拟模型，可用于验证流程；配置真实模型后请重新评测。
    </n-alert>

    <div v-if="current" class="run-progress" aria-live="polite">
      <div class="progress-label">已完成 {{ current.done_count }} / {{ current.total_count }} 条</div>
      <n-progress type="line" :percentage="percentage" :show-indicator="false" :status="current.failed_count ? 'error' : current.status === 'success' ? 'success' : 'default'" :processing="running" />
    </div>

    <n-collapse v-if="current?.results?.length" class="results">
      <n-collapse-item :title="`逐条结果（${current.results.length}）`" name="results">
        <div v-for="result in current.results" :key="result.case_id" class="result-row">
          <div class="result-head">
            <n-tag size="tiny" :bordered="false" :type="result.passed ? 'success' : 'error'">{{ result.passed ? '通过' : '未通过' }}</n-tag>
            <span class="result-question">{{ result.question }}</span>
            <n-tag v-if="result.simulated" size="tiny" :bordered="false" type="warning">模拟</n-tag>
          </div>
          <ul v-if="result.reasons.length" class="result-reasons">
            <li v-for="(reason, index) in result.reasons" :key="index">{{ reason }}</li>
          </ul>
          <n-collapse class="output-collapse">
            <n-collapse-item :title="`查看输出 · ${result.refs_count} 条引用`" :name="result.case_id">
              <div class="result-output">{{ result.output || '（无输出）' }}</div>
            </n-collapse-item>
          </n-collapse>
        </div>
      </n-collapse-item>
    </n-collapse>
    <p v-else-if="current && current.done_count > 0" class="run-hint">历史接口未返回逐条明细，可重新运行查看完整输出。</p>

    <div v-if="history.length > 1" class="history-row">
      <span class="history-label">历史运行</span>
      <n-select v-model:value="selectedId" size="small" :options="historyOptions" :disabled="running" placeholder="选择运行记录" />
    </div>
    <div v-if="historyError" class="history-error">
      <span>{{ historyError }}</span>
      <n-button text size="tiny" type="primary" :loading="loading" :disabled="running" @click="loadHistory">重试</n-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useMessage } from 'naive-ui'
import { PlayOutline } from '@vicons/ionicons5'
import { createEvalRun, listEvalRuns, stepEvalRun } from '@/api'
import type { EvalRunSummary } from '@/api/types'

const props = defineProps<{ setId: string; appId?: string; latestRun?: EvalRunSummary | null; disabled?: boolean }>()
const emit = defineEmits<{
  completed: [run: EvalRunSummary]
  'running-change': [running: boolean]
}>()
const message = useMessage()
const running = ref(false)
const loading = ref(false)
const error = ref('')
const historyError = ref('')
const history = ref<EvalRunSummary[]>([])
const selectedId = ref('')
let generation = 0
let alive = true

const current = computed(() => history.value.find(run => run.id === selectedId.value) || history.value[0] || null)
const percentage = computed(() => current.value?.total_count ? Math.min(100, Math.round(current.value.done_count / current.value.total_count * 100)) : 0)
const historyOptions = computed(() => history.value.map(run => ({
  value: run.id,
  label: `${formatTime(run.created_at)} · ${run.status === 'running' ? '未完成' : `${run.passed_count} 通过 / ${run.failed_count} 未通过`}`
})))

function formatTime(value: string) {
  return value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '—'
}
function remember(run: EvalRunSummary) {
  history.value = [run, ...history.value.filter(item => item.id !== run.id)].slice(0, 10)
  selectedId.value = run.id
}
function setRunning(value: boolean) {
  running.value = value
  emit('running-change', value)
}
async function loadHistory() {
  if (running.value) return
  const token = generation
  loading.value = true
  historyError.value = ''
  try {
    const runs = await listEvalRuns(props.setId)
    if (!alive || token !== generation) return
    const local = new Map(history.value.map(run => [run.id, run]))
    history.value = runs.map(run => ({ ...run, results: run.results?.length ? run.results : local.get(run.id)?.results || [] }))
    if (!history.value.some(run => run.id === selectedId.value)) selectedId.value = history.value[0]?.id || ''
  } catch (caught: any) {
    if (alive && token === generation) historyError.value = caught.message || '运行记录加载失败'
  } finally {
    if (alive && token === generation) loading.value = false
  }
}
async function execute(resumeRun?: EvalRunSummary) {
  if (running.value || !props.appId || props.disabled) return
  const token = ++generation
  const setId = props.setId
  setRunning(true)
  loading.value = false
  error.value = ''
  try {
    let run = resumeRun || await createEvalRun(setId)
    if (!alive || token !== generation) return
    remember(run)
    while (run.status === 'running') {
      const previousDone = run.done_count
      run = await stepEvalRun(setId, run.id)
      if (!alive || token !== generation) return
      remember(run)
      if (run.status === 'running' && run.done_count <= previousDone) throw new Error('本次评测未推进，请重新运行')
    }
    emit('completed', run)
    message[run.failed_count ? 'warning' : 'success'](`评测完成：${run.passed_count} 通过，${run.failed_count} 未通过`)
  } catch (caught: any) {
    if (alive && token === generation) error.value = caught.message || '评测运行失败'
  } finally {
    if (alive && token === generation) setRunning(false)
  }
}
async function start() { await execute() }
async function resume() {
  const run = current.value
  if (run?.status === 'running' && run.matches_draft) await execute(run)
}

watch(() => [props.setId, props.appId] as const, () => {
  generation++
  if (running.value) setRunning(false)
  history.value = props.latestRun ? [props.latestRun] : []
  selectedId.value = props.latestRun?.id || ''
  error.value = ''
  void loadHistory()
}, { immediate: true })
watch(() => props.latestRun, run => {
  if (run && !running.value) {
    const local = history.value.find(item => item.id === run.id)
    remember({ ...run, results: run.results?.length ? run.results : local?.results || [] })
  }
})
onBeforeUnmount(() => {
  alive = false
  generation++
  if (running.value) setRunning(false)
})
defineExpose({ start })
</script>

<style scoped>
.eval-run-panel { min-width: 0; }
.run-toolbar, .run-summary, .run-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.run-toolbar { justify-content: space-between; }
.run-time, .muted, .run-hint, .history-label { color: #6b7280; font-size: 12px; }
.run-hint { margin: 9px 0; line-height: 1.6; }
.run-alert { margin-top: 10px; }
.alert-hint { margin-top: 3px; }
.run-progress { margin: 12px 0; }
.progress-label { font-size: 12px; color: #4e5969; margin-bottom: 6px; font-variant-numeric: tabular-nums; }
.results { margin-top: 12px; }
.result-row { padding: 10px 0; border-bottom: 1px dashed #e5e6eb; }
.result-row:last-child { border-bottom: 0; }
.result-head { display: flex; align-items: flex-start; gap: 8px; }
.result-question { flex: 1; min-width: 0; font-size: 12px; line-height: 1.7; color: #1f2329; overflow-wrap: anywhere; }
.result-reasons { padding-left: 20px; margin: 7px 0; color: #c42b3a; font-size: 12px; line-height: 1.7; overflow-wrap: anywhere; }
.output-collapse { margin-top: 8px; }
.result-output { max-height: 280px; overflow: auto; padding: 10px 12px; border-radius: 7px; background: #f5f6f8; white-space: pre-wrap; overflow-wrap: anywhere; color: #333b48; font-size: 12px; line-height: 1.75; }
.history-row { display: flex; align-items: center; gap: 10px; max-width: 560px; margin-top: 12px; }
.history-label { flex-shrink: 0; }
.history-error { display: flex; gap: 8px; align-items: center; color: #c42b3a; font-size: 12px; margin-top: 10px; }
@media (max-width: 640px) { .run-toolbar { align-items: flex-start; flex-direction: column; } .history-row { align-items: flex-start; flex-direction: column; } }
</style>
