<template>
  <n-modal
    :show="show"
    preset="card"
    title="AI 设计评测集"
    style="width: 740px; max-width: calc(100vw - 32px)"
    :bordered="false"
    :mask-closable="!generating"
    :close-on-esc="!generating"
    :closable="!generating"
    @update:show="close"
  >
    <div class="design-body">
      <n-alert v-if="error" type="error" :show-icon="false">{{ error }}</n-alert>
      <div v-if="loading" class="loading"><n-spin size="small" /><span>加载评测规则…</span></div>
      <template v-else-if="!result">
        <div class="field">
          <label class="label">评测规则</label>
          <span class="hint">已按应用场景勾选推荐规则，可按业务需要调整。</span>
          <n-checkbox-group v-model:value="form.rule_keys" :disabled="generating">
            <div class="rule-list">
              <n-checkbox v-for="rule in rules" :key="rule.key" class="rule-row" :value="rule.key" :aria-label="rule.name">
                <span class="rule-content">
                  <span class="rule-title">{{ rule.name }} <n-tag v-if="defaultKeys.includes(rule.key)" size="tiny" :bordered="false" type="info">推荐</n-tag></span>
                  <span class="rule-description">{{ rule.description }}</span>
                </span>
              </n-checkbox>
            </div>
          </n-checkbox-group>
          <n-button v-if="!rules.length" text size="small" type="primary" @click="loadRules">重新加载规则</n-button>
        </div>
        <div class="field">
          <label class="label" for="eval-design-directions">补充业务方向（选填）</label>
          <n-input id="eval-design-directions" v-model:value="form.directions" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" :disabled="generating" placeholder="例如：重点测试退换货时效、超出知识范围的问题，以及需要引用制度原文的回答" />
        </div>
        <div class="form-row">
          <div class="field">
            <label class="label">生成数量</label>
            <n-input-number v-model:value="form.count" :min="1" :max="30" :precision="0" :disabled="generating" />
            <span class="hint">每次 1～30 条 Case</span>
          </div>
          <div class="field">
            <label class="label">生成目标</label>
            <n-radio-group v-model:value="form.target" :disabled="generating">
              <n-radio value="new">新建评测集</n-radio>
              <n-radio value="existing" :disabled="!boundSets.length">已有评测集</n-radio>
            </n-radio-group>
            <n-input v-if="form.target === 'new'" v-model:value="form.set_name" :disabled="generating" placeholder="评测集名称（留空由系统命名）" />
            <n-select v-else v-model:value="form.set_id" :options="setOptions" :disabled="generating" filterable placeholder="选择本应用的评测集" />
          </div>
        </div>
        <p class="hint design-note">生成的 Case 会包含可自动判定的标准。生成后可查看并编辑，再基于当前草稿运行。</p>
      </template>

      <template v-if="result">
        <n-alert :type="result.simulated ? 'warning' : 'success'" :show-icon="false">
          已向「{{ result.set.name }}」加入 {{ result.cases.length }} 条 Case。
          <div v-if="result.simulated" class="hint result-simulation">当前使用模拟模型，Case 来自规则兜底生成；配置真实模型后可重新设计。</div>
        </n-alert>
        <n-collapse :default-expanded-names="result.cases.length ? [result.cases[0].id] : []">
          <n-collapse-item v-for="item in result.cases" :key="item.id" :name="item.id" :title="item.question">
            <div class="case-standard">
              <n-tag size="tiny" :bordered="false" :type="item.readiness === 'ready' ? 'success' : 'warning'">{{ item.readiness === 'ready' ? '可运行' : '待补标准' }}</n-tag>
              <div v-if="item.reference_answer" class="standard-row"><span>期望回答</span><div>{{ item.reference_answer }}</div></div>
              <div v-if="item.expected_keywords?.length" class="standard-row"><span>必须包含</span><div>{{ item.expected_keywords.join('、') }}</div></div>
              <div v-if="item.forbidden_keywords?.length" class="standard-row"><span>禁止出现</span><div>{{ item.forbidden_keywords.join('、') }}</div></div>
              <div class="standard-row"><span>要求引用</span><div>{{ item.require_citations ? '是' : '否' }}</div></div>
              <div v-if="item.tags?.length" class="hint">{{ item.tags.join(' · ') }}</div>
            </div>
          </n-collapse-item>
        </n-collapse>
      </template>
    </div>
    <template #footer>
      <div class="modal-footer">
        <template v-if="result">
          <n-button @click="close(false)">完成</n-button>
          <n-button type="primary" @click="runGenerated">
            <template #icon><n-icon><PlayOutline /></n-icon></template>
            立即运行
          </n-button>
        </template>
        <template v-else>
          <n-button :disabled="generating" @click="close(false)">取消</n-button>
          <n-button type="primary" :loading="generating" :disabled="!valid" @click="generate">
            <template #icon><n-icon><SparklesOutline /></n-icon></template>
            {{ generating ? '正在设计 Case…' : '生成评测集' }}
          </n-button>
        </template>
      </div>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { PlayOutline, SparklesOutline } from '@vicons/ionicons5'
import { aiDesignEval, getEvalDesignRules } from '@/api'
import type { AiDesignEvalResponse, EvalDesignRule, EvalSetSummary } from '@/api/types'

const props = withDefaults(defineProps<{ show: boolean; appId: string; sets?: EvalSetSummary[] }>(), { sets: () => [] })
const emit = defineEmits<{
  'update:show': [show: boolean]
  generated: [result: AiDesignEvalResponse]
  run: [setId: string]
}>()
const loading = ref(false)
const generating = ref(false)
const error = ref('')
const rules = ref<EvalDesignRule[]>([])
const defaultKeys = ref<string[]>([])
const result = ref<AiDesignEvalResponse | null>(null)
const form = reactive({ rule_keys: [] as string[], directions: '', count: 10 as number | null, target: 'new', set_id: null as string | null, set_name: '' })
let request = 0

const boundSets = computed(() => props.sets.filter(set => set.app_id === props.appId))
const setOptions = computed(() => boundSets.value.map(set => ({ label: set.name, value: set.id })))
const valid = computed(() => !loading.value && !!props.appId && rules.value.length > 0 && (form.rule_keys.length > 0 || !!form.directions.trim()) && form.count !== null && form.count >= 1 && form.count <= 30 && (form.target === 'new' || !!form.set_id))

function close(show: boolean) {
  if (!generating.value) emit('update:show', show)
}
async function loadRules() {
  const token = ++request
  loading.value = true
  error.value = ''
  rules.value = []
  try {
    const response = await getEvalDesignRules(props.appId)
    if (token !== request || !props.show) return
    rules.value = response.rules
    defaultKeys.value = response.default_keys
    form.rule_keys = [...response.default_keys]
  } catch (caught: any) {
    if (token === request) error.value = caught.message || '评测规则加载失败，请重试'
  } finally {
    if (token === request) loading.value = false
  }
}
async function generate() {
  if (!valid.value || generating.value) return
  generating.value = true
  error.value = ''
  try {
    const response = await aiDesignEval({
      app_id: props.appId,
      ...(form.target === 'existing' ? { set_id: form.set_id! } : form.set_name.trim() ? { set_name: form.set_name.trim() } : {}),
      rule_keys: form.rule_keys,
      directions: form.directions.trim(),
      count: form.count!
    })
    result.value = response
    emit('generated', response)
  } catch (caught: any) {
    error.value = caught.message || '生成失败，请重试'
  } finally {
    generating.value = false
  }
}
function runGenerated() {
  if (!result.value) return
  emit('run', result.value.set.id)
  close(false)
}
watch(() => [props.show, props.appId] as const, ([show]) => {
  if (!show) { request++; return }
  result.value = null
  error.value = ''
  form.directions = ''
  form.count = 10
  form.target = 'new'
  form.set_id = null
  form.set_name = ''
  void loadRules()
}, { immediate: true })
</script>

<style scoped>
.design-body { display: flex; flex-direction: column; gap: 18px; max-height: min(65vh, 660px); overflow-y: auto; padding-right: 4px; }
.loading { display: flex; align-items: center; justify-content: center; gap: 10px; padding: 50px 0; color: #6b7280; font-size: 12px; }
.field { display: flex; flex-direction: column; gap: 8px; min-width: 0; }
.label { color: #4e5969; font-size: 12px; font-weight: 500; }
.hint { font-size: 12px; color: #6b7280; line-height: 1.7; }
.rule-list { display: flex; flex-direction: column; }
.rule-row { display: flex; align-items: flex-start; gap: 10px; padding: 11px 0; border-bottom: 1px solid #eef0f3; cursor: pointer; }
.rule-row:last-child { border-bottom: 0; }
.rule-content { min-width: 0; display: flex; flex-direction: column; gap: 4px; }
.rule-title { display: flex; gap: 8px; align-items: center; color: #1f2329; font-size: 13px; font-weight: 500; }
.rule-description { font-size: 12px; color: #6b7280; line-height: 1.7; }
.form-row { display: grid; grid-template-columns: minmax(130px, 1fr) minmax(0, 2fr); gap: 22px; }
.design-note { margin: 0; }
.modal-footer { display: flex; justify-content: flex-end; gap: 10px; flex-wrap: wrap; }
.result-simulation { color: inherit; margin-top: 4px; }
.case-standard { display: flex; flex-direction: column; align-items: flex-start; gap: 9px; }
.standard-row { display: grid; grid-template-columns: 65px minmax(0, 1fr); gap: 10px; width: 100%; font-size: 12px; line-height: 1.7; white-space: pre-wrap; overflow-wrap: anywhere; }
.standard-row > span { color: #6b7280; }
@media (max-width: 560px) { .form-row { grid-template-columns: 1fr; gap: 16px; } }
</style>
