<template>
  <div class="app-eval-panel">
    <div class="panel-head">
      <div class="head-copy">
        <h3>应用评测</h3>
        <p>基于当前草稿验证回答质量。设为发布门禁的评测集，必须通过后才能发布。</p>
      </div>
      <div class="head-actions">
        <n-button size="small" :loading="loading" :disabled="anyRunning" @click="load">刷新</n-button>
        <n-button size="small" @click="$router.push('/app/eval')">管理评测集</n-button>
        <n-button size="small" type="primary" :disabled="anyRunning" @click="designing = true">
          <template #icon><n-icon><SparklesOutline /></n-icon></template>
          AI 设计评测集
        </n-button>
      </div>
    </div>

    <n-alert v-if="error" type="error" :show-icon="false" class="panel-error">{{ error }}</n-alert>
    <div v-if="loading && !sets.length" class="empty"><n-spin size="small" /><span>加载评测集…</span></div>
    <div v-else-if="!sets.length && !error" class="empty">
      <strong>还没有绑定本应用的评测集</strong>
      <p>使用 AI 设计 Case，或在评测集详情绑定本应用，建立可重复运行的质量基线。</p>
      <n-button size="small" type="primary" ghost @click="designing = true">AI 设计评测集</n-button>
    </div>
    <div v-for="set in sets" :key="set.id" class="set-section">
      <div class="set-head">
        <div class="set-copy">
          <n-button text type="primary" class="set-name" @click="$router.push(`/app/eval/${set.id}`)">{{ set.name }}</n-button>
          <span class="case-count">{{ set.case_count }} 条 Case</span>
          <p v-if="set.description">{{ set.description }}</p>
        </div>
        <div class="gate-control">
          <span>发布门禁</span>
          <n-switch :value="set.is_release_gate" :loading="gateBusy[set.id]" :disabled="!!runningSets[set.id] || !!gateBusy[set.id]" :aria-label="`${set.name}设为发布门禁`" @update:value="toggleGate(set, $event)" />
        </div>
      </div>
      <EvalRunPanel
        :ref="el => setRunner(set.id, el)"
        :set-id="set.id"
        :app-id="appId"
        :latest-run="set.latest_run"
        :disabled="!!gateBusy[set.id]"
        @running-change="runningSets[set.id] = $event"
        @completed="onCompleted(set.id, $event)"
      />
    </div>

    <AiDesignModal v-model:show="designing" :app-id="appId" :sets="sets" @generated="onGenerated" @run="runGenerated" />
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { useMessage } from 'naive-ui'
import { SparklesOutline } from '@vicons/ionicons5'
import { listEvalSets, updateEvalSet } from '@/api'
import type { AiDesignEvalResponse, EvalRunSummary, EvalSetSummary } from '@/api/types'
import AiDesignModal from './AiDesignModal.vue'
import EvalRunPanel from './EvalRunPanel.vue'

const props = defineProps<{ appId: string }>()
const emit = defineEmits<{ changed: [] }>()
const message = useMessage()
const sets = ref<EvalSetSummary[]>([])
const loading = ref(false)
const error = ref('')
const designing = ref(false)
const gateBusy = reactive<Record<string, boolean>>({})
const runningSets = reactive<Record<string, boolean>>({})
const runners = new Map<string, { start: () => Promise<void> }>()
const anyRunning = computed(() => Object.values(runningSets).some(Boolean))
let request = 0
let alive = true

function setRunner(id: string, el: any) {
  if (el) runners.set(id, el)
  else runners.delete(id)
}
async function load() {
  const token = ++request
  loading.value = true
  error.value = ''
  try {
    const all = await listEvalSets()
    if (token === request && alive) sets.value = all.filter(set => set.app_id === props.appId)
  } catch (caught: any) {
    if (token === request && alive) error.value = caught.message || '评测集加载失败，请刷新重试'
  } finally {
    if (token === request && alive) loading.value = false
  }
}
async function toggleGate(set: EvalSetSummary, value: boolean) {
  if (gateBusy[set.id] || runningSets[set.id]) return
  gateBusy[set.id] = true
  try {
    const updated = await updateEvalSet(set.id, { is_release_gate: value })
    const index = sets.value.findIndex(item => item.id === set.id)
    if (index >= 0) sets.value[index] = updated
    message.success(value ? '已设为发布门禁' : '已取消发布门禁')
    emit('changed')
  } catch (caught: any) {
    message.error(caught.message || '门禁设置失败')
  } finally {
    gateBusy[set.id] = false
  }
}
function onCompleted(setId: string, run: EvalRunSummary) {
  const set = sets.value.find(item => item.id === setId)
  if (set) set.latest_run = run
  emit('changed')
}
function onGenerated(response: AiDesignEvalResponse) {
  const index = sets.value.findIndex(set => set.id === response.set.id)
  if (index >= 0) sets.value[index] = response.set
  else sets.value.unshift(response.set)
  emit('changed')
}
async function runGenerated(setId: string) {
  await nextTick()
  const runner = runners.get(setId)
  if (runner) await runner.start()
  else message.error('运行入口尚未就绪，请在评测集中点击「运行评测」')
}
watch(() => props.appId, () => { sets.value = []; void load() }, { immediate: true })
onBeforeUnmount(() => { alive = false; request++ })
</script>

<style scoped>
.app-eval-panel { max-width: 1200px; padding: 12px 0; }
.panel-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; margin-bottom: 20px; }
.head-copy { min-width: 0; }
.head-copy h3 { margin: 0; font-size: 16px; font-weight: 600; color: #1f2329; }
.head-copy p, .set-copy p { margin: 6px 0 0; font-size: 12px; line-height: 1.7; color: #6b7280; overflow-wrap: anywhere; }
.head-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; flex-shrink: 0; }
.panel-error { margin-bottom: 14px; }
.set-section { padding: 18px 0 22px; border-bottom: 1px solid #e5e6eb; }
.set-section:first-of-type { padding-top: 0; }
.set-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; margin-bottom: 15px; }
.set-copy { min-width: 0; }
.set-name { font-size: 14px; font-weight: 600; max-width: 100%; height: auto; text-align: left; white-space: normal; overflow-wrap: anywhere; }
.case-count { font-size: 12px; color: #6b7280; margin-left: 10px; white-space: nowrap; }
.gate-control { display: flex; align-items: center; gap: 8px; color: #4e5969; font-size: 12px; white-space: nowrap; flex-shrink: 0; }
.empty { display: flex; align-items: center; flex-direction: column; gap: 10px; padding: 50px 16px; color: #6b7280; font-size: 12px; text-align: center; }
.empty strong { font-size: 14px; font-weight: 600; color: #3b4351; }
.empty p { margin: 0 0 5px; max-width: 460px; line-height: 1.7; }
@media (max-width: 780px) { .panel-head { flex-direction: column; gap: 12px; } .head-actions { flex-shrink: 1; } }
@media (max-width: 520px) { .set-head { flex-direction: column; gap: 10px; } }
</style>
