<template>
  <n-modal
    :show="show"
    preset="card"
    :title="title"
    style="width: 640px; max-width: calc(100vw - 32px); max-height: calc(100vh - 40px)"
    :bordered="false"
    @update:show="emit('update:show', $event)"
  >
    <div class="flow-body">
      <div class="flow-hint">
        <n-icon size="15"><FlaskOutline /></n-icon>
        <span>{{ hint }}</span>
      </div>

      <div class="field">
        <label class="label">Case 标签</label>
        <div class="label-switch">
          <button
            type="button"
            class="label-option good"
            :class="{ active: form.label === 'good' }"
            @click="form.label = 'good'"
          >
            <n-icon size="15"><CheckmarkCircleOutline /></n-icon>
            Good Case
            <span>回答正确 / 可作正例</span>
          </button>
          <button
            type="button"
            class="label-option bad"
            :class="{ active: form.label === 'bad' }"
            @click="form.label = 'bad'"
          >
            <n-icon size="15"><CloseCircleOutline /></n-icon>
            Bad Case
            <span>回答错误 / 有风险</span>
          </button>
        </div>
      </div>

      <template v-if="mode === 'manual'">
        <div class="field">
          <label class="label">问题 <span class="req">*</span></label>
          <n-input v-model:value="form.question" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" placeholder="用户当时问了什么" />
        </div>
        <div class="field">
          <label class="label">实际回答</label>
          <n-input v-model:value="form.answer" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" placeholder="线上给出的回答" />
        </div>
      </template>
      <template v-else>
        <div class="preview">
          <div class="preview-label">问题</div>
          <div class="preview-text">{{ presetQuestion || '（无）' }}</div>
        </div>
        <div class="preview">
          <div class="preview-label">线上回答</div>
          <div class="preview-text answer">{{ presetAnswer || '（无）' }}</div>
        </div>
      </template>

      <div class="field">
        <label class="label">期望回答（评测基线）</label>
        <n-input
          v-model:value="form.reference_answer"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 5 }"
          placeholder="写出你认为正确的回答，后续可据此做回归对比（可留空）"
        />
      </div>

      <div class="field-row">
        <div class="field">
          <label class="label">必须包含关键词</label>
          <n-dynamic-tags v-model:value="form.expected_keywords" />
        </div>
        <div class="field">
          <label class="label">禁止出现关键词</label>
          <n-dynamic-tags v-model:value="form.forbidden_keywords" />
        </div>
      </div>
      <div class="standard-row">
        <label class="label">要求引用</label>
        <n-switch v-model:value="form.require_citations" aria-label="要求引用" />
        <n-tag size="tiny" :bordered="false" :type="ready ? 'success' : 'warning'">{{ ready ? '可运行' : '待补标准' }}</n-tag>
      </div>

      <div class="field-row">
        <div class="field">
          <label class="label">加入评测集</label>
          <n-select v-model:value="form.set_id" :options="setOptions" placeholder="仅回流到 Case 池" clearable />
        </div>
        <div class="field">
          <label class="label">标签</label>
          <n-dynamic-tags v-model:value="form.tags" :max="6" />
        </div>
      </div>

      <div class="field">
        <label class="label">备注</label>
        <n-input v-model:value="form.note" type="textarea" :autosize="{ minRows: 1, maxRows: 3 }" placeholder="为什么标记 good / bad，便于后续复盘" />
      </div>
    </div>

    <template #footer>
      <div class="modal-footer">
        <n-button quaternary @click="emit('update:show', false)">取消</n-button>
        <n-button type="primary" :loading="submitting" :disabled="!valid" @click="submit">
          {{ form.set_id ? '回流并加入评测集' : '回流到 Case 池' }}
        </n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useMessage } from 'naive-ui'
import { CheckmarkCircleOutline, CloseCircleOutline, FlaskOutline } from '@vicons/ionicons5'
import { createCase, listEvalSets, traceToCase, updateCase } from '@/api'
import type { EvalSetSummary } from '@/api/types'

const props = withDefaults(
  defineProps<{
    show: boolean
    mode?: 'trace' | 'manual' | 'log'
    traceId?: string
    presetQuestion?: string
    presetAnswer?: string
    presetAppId?: string
    presetAppName?: string
    initialLabel?: 'good' | 'bad'
    defaultSetId?: string
  }>(),
  {
    mode: 'trace',
    traceId: '',
    presetQuestion: '',
    presetAnswer: '',
    presetAppId: '',
    presetAppName: '',
    initialLabel: 'good',
    defaultSetId: ''
  }
)
const emit = defineEmits<{ 'update:show': [boolean]; saved: [any] }>()
const message = useMessage()

const sets = ref<EvalSetSummary[]>([])
const submitting = ref(false)
const form = reactive({
  label: 'good' as 'good' | 'bad',
  question: '',
  answer: '',
  reference_answer: '',
  expected_keywords: [] as string[],
  forbidden_keywords: [] as string[],
  require_citations: false,
  tags: [] as string[],
  note: '',
  set_id: null as string | null
})

const title = computed(() =>
  props.mode === 'trace' ? '回流线上 Case · 来自调用链路' : props.mode === 'log' ? '回流线上 Case · 来自对话日志' : '手动新建 Case'
)
const hint = computed(() => {
  if (props.mode === 'trace') return '问题、回答、检索上下文将自动带入，无需重复填写。'
  if (props.mode === 'log') return '从历史对话日志回流；建议补充期望回答，评测价值更高。'
  return '手动录入一条评测 Case，适合整理外部反馈或人工构造边界用例。'
})
const setOptions = computed(() => sets.value.map(s => ({ label: `${s.name}（${s.case_count}）`, value: s.id })))
const valid = computed(() => props.mode !== 'manual' || !!form.question.trim())
const ready = computed(() => !!(props.mode === 'manual' ? form.question.trim() : props.presetQuestion.trim()) && !!(
  form.reference_answer.trim() || form.expected_keywords.some(k => k.trim()) || form.forbidden_keywords.some(k => k.trim()) || form.require_citations
))

watch(
  () => props.show,
  async show => {
    if (!show) return
    form.label = props.initialLabel
    form.question = props.mode === 'manual' ? '' : props.presetQuestion
    form.answer = props.mode === 'manual' ? '' : props.presetAnswer
    form.reference_answer = ''
    form.expected_keywords = []
    form.forbidden_keywords = []
    form.require_citations = false
    form.tags = []
    form.note = ''
    form.set_id = props.defaultSetId || null
    try {
      sets.value = await listEvalSets()
    } catch {
      sets.value = []
    }
  }
)

async function submit() {
  if (!valid.value) return
  submitting.value = true
  try {
    let result: any
    const standards = {
      expected_keywords: form.expected_keywords.map(k => k.trim()).filter(Boolean),
      forbidden_keywords: form.forbidden_keywords.map(k => k.trim()).filter(Boolean),
      require_citations: form.require_citations
    }
    if (props.mode === 'trace' && props.traceId) {
      result = await traceToCase(props.traceId, {
        label: form.label,
        note: form.note,
        tags: form.tags,
        reference_answer: form.reference_answer,
        set_id: form.set_id || ''
      })
      if (standards.expected_keywords.length || standards.forbidden_keywords.length || standards.require_citations) {
        try {
          await updateCase(result.case_id, standards)
        } catch (e: any) {
          message.error(`Case 已回流，评测标准保存失败，请在 Case 池补充：${e.message || '保存失败'}`)
          emit('saved', result)
          emit('update:show', false)
          return
        }
      }
    } else {
      result = await createCase({
        trace_id: props.traceId || undefined,
        question: form.question,
        answer: form.answer,
        reference_answer: form.reference_answer,
        ...standards,
        label: form.label,
        status: 'confirmed',
        app_id: props.presetAppId || undefined,
        app_name: props.presetAppName || undefined,
        source: props.mode === 'log' ? 'log' : 'manual',
        tags: form.tags,
        note: form.note,
        set_id: form.set_id || undefined
      })
    }
    message.success(
      form.set_id ? `已回流为 ${form.label === 'good' ? 'Good' : 'Bad'} Case 并加入评测集` : `已回流为 ${form.label === 'good' ? 'Good' : 'Bad'} Case`
    )
    emit('saved', result)
    emit('update:show', false)
  } catch (e: any) {
    message.error(e.message || '回流失败')
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.flow-body {
  display: flex;
  flex-direction: column;
  gap: 14px;
  max-height: calc(100vh - 240px);
  overflow-y: auto;
  padding-right: 4px;
}
.flow-hint {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 12px;
  line-height: 1.6;
  color: #4d6a9c;
  background: #f4f7ff;
  border: 1px solid #e2eaff;
  border-radius: 7px;
  padding: 9px 11px;
}
.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}
.field-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.standard-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.label {
  font-size: 12px;
  color: #4e5969;
}
.req {
  color: #d22d3d;
}
.label-switch {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
.label-option {
  display: flex;
  align-items: center;
  gap: 6px;
  border: 1px solid #e5e6eb;
  background: #fff;
  border-radius: 8px;
  padding: 10px 12px;
  font-size: 12.5px;
  color: #5c6470;
  cursor: pointer;
  text-align: left;
  flex-wrap: wrap;
  transition: border-color 160ms ease, background 160ms ease;
}
.label-option span {
  width: 100%;
  padding-left: 21px;
  font-size: 10.5px;
  color: #9aa1ab;
}
.label-option.good.active {
  border-color: #7bd0a2;
  background: #f2fbf6;
  color: #147a4a;
}
.label-option.bad.active {
  border-color: #f0a6ad;
  background: #fff5f5;
  color: #bf2c3b;
}
.preview {
  background: #fafbfc;
  border: 1px solid #eef0f3;
  border-radius: 7px;
  padding: 9px 11px;
}
.preview-label {
  font-size: 10.5px;
  color: #8a9099;
  margin-bottom: 4px;
}
.preview-text {
  font-size: 12px;
  line-height: 1.65;
  color: #333b48;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 96px;
  overflow: auto;
}
.preview-text.answer {
  color: #4b5563;
}
.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}
@media (max-width: 640px) {
  .field-row,
  .label-switch {
    grid-template-columns: 1fr;
  }
}
</style>
