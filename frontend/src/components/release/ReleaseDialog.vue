<template>
  <n-modal :show="show" preset="card" title="发布应用" class="release-dialog"
    style="width: 640px; max-width: calc(100vw - 32px)" :mask-closable="!publishing"
    :closable="!publishing" :close-on-esc="!publishing" @update:show="emit('update:show', $event)">
    <n-spin :show="checking">
      <div class="release-content">
        <n-alert v-if="error" type="error" :bordered="false" title="发布未完成">
          <div class="error-text">{{ error }}</div>
        </n-alert>
        <template v-if="check">
          <section>
            <h3>草稿校验</h3>
            <n-alert :type="check.issues.length ? 'error' : 'success'" :bordered="false">
              <ul v-if="check.issues.length" class="issue-list"><li v-for="issue in check.issues" :key="issue">{{ issue }}</li></ul>
              <span v-else>草稿校验通过</span>
            </n-alert>
          </section>
          <section>
            <div class="section-head"><h3>发布质量门禁</h3><n-button text size="small" type="primary" @click="goEval">去评测</n-button></div>
            <div v-if="!check.gates.length" class="hint">尚未设置发布门禁，可在「评测」中将评测集设为门禁。</div>
            <div v-for="gate in check.gates" :key="gate.set_id" class="gate-row">
              <div class="gate-head"><strong>{{ gate.set_name }}</strong><n-tag size="small" :bordered="false" :type="gate.passed ? 'success' : 'error'">{{ gate.passed ? '通过' : '未通过' }}</n-tag></div>
              <div class="hint">{{ gate.reason }}</div>
              <div v-if="gate.latest_run" class="hint">最近一次：{{ gate.latest_run.passed_count }} 条通过，{{ gate.latest_run.failed_count }} 条未通过<span v-if="gate.latest_run.simulated"> · 模拟模型</span></div>
            </div>
          </section>
          <section>
            <h3>版本说明</h3>
            <n-input v-model:value="notes" type="textarea" placeholder="说明本次发布的改动（可选）" :disabled="publishing" :autosize="{ minRows: 3, maxRows: 6 }" />
            <p class="hint">发布会固化当前已保存的草稿，工作台与公开链接使用同一线上版本。草稿与最新版本相同时，将直接发布该版本。</p>
          </section>
        </template>
        <div v-else-if="!checking && !error" class="hint">正在获取发布校验结果…</div>
      </div>
    </n-spin>
    <template #footer>
      <div class="footer-actions">
        <n-button size="small" :loading="checking" :disabled="publishing" @click="loadCheck()">重新检查</n-button>
        <span class="spacer"></span>
        <n-button size="small" :disabled="publishing" @click="emit('update:show', false)">取消</n-button>
        <n-button size="small" type="primary" :disabled="checking || !check?.can_release" :loading="publishing" @click="publish">确认发布</n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useMessage } from 'naive-ui'
import { getAppReleaseCheck, releaseApp } from '@/api'
import type { Application, AppReleaseCheck } from '@/api/types'

const props = defineProps<{ show: boolean; appId: string }>()
const emit = defineEmits<{ 'update:show': [show: boolean]; published: [app: Application]; eval: [] }>()
const message = useMessage()
const checking = ref(false)
const publishing = ref(false)
const check = ref<AppReleaseCheck | null>(null)
const notes = ref('')
const error = ref('')
let request = 0

function errorText(caught: unknown) {
  const text = caught instanceof Error ? caught.message : '发布失败，请重试'
  try {
    const detail = JSON.parse(text)
    return [detail.message, ...(Array.isArray(detail.issues) ? detail.issues : [])].filter(Boolean).join('\n') || text
  } catch { return text }
}
async function loadCheck(preserveError = false) {
  const token = ++request
  checking.value = true
  check.value = null
  if (!preserveError) error.value = ''
  try {
    const result = await getAppReleaseCheck(props.appId)
    if (token === request) check.value = result
  } catch (caught) {
    if (token === request) error.value = errorText(caught)
  } finally {
    if (token === request) checking.value = false
  }
}
function goEval() {
  emit('update:show', false)
  emit('eval')
}
async function publish() {
  if (publishing.value || checking.value || !check.value?.can_release) return
  publishing.value = true
  error.value = ''
  try {
    const app = await releaseApp(props.appId, notes.value.trim())
    emit('published', app)
    emit('update:show', false)
    message.success(`已发布线上 v${app.published_version ?? ''}`)
  } catch (caught) {
    error.value = errorText(caught)
    await loadCheck(true)
  } finally { publishing.value = false }
}
watch(() => [props.show, props.appId] as const, ([show]) => {
  if (show) { notes.value = ''; void loadCheck() }
  else { request++; checking.value = false }
}, { immediate: true })
</script>

<style scoped>
.release-content { display: flex; flex-direction: column; gap: 20px; min-height: 80px; }
h3 { margin: 0 0 10px; color: #1f2329; font-size: 13px; font-weight: 600; }
.section-head, .gate-head, .footer-actions { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.section-head { justify-content: space-between; margin-bottom: 10px; }
.section-head h3 { margin: 0; }
.gate-row { padding: 12px 0; border-bottom: 1px solid #eef0f3; }
.gate-row:last-child { border-bottom: 0; }
.gate-head { justify-content: space-between; margin-bottom: 5px; font-size: 13px; }
.gate-head strong { overflow-wrap: anywhere; }
.hint { color: #646e7d; font-size: 12px; line-height: 1.7; }
p.hint { margin: 8px 0 0; }
.issue-list { margin: 0; padding-left: 18px; }
.error-text { white-space: pre-wrap; overflow-wrap: anywhere; }
.spacer { flex: 1; }
</style>
