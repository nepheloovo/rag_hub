<template>
  <div class="message-feedback">
    <div class="feedback-actions">
      <n-button
        size="tiny"
        quaternary
        :type="currentRating === 1 ? 'primary' : 'default'"
        :disabled="saving"
        :aria-pressed="currentRating === 1"
        :aria-label="currentRating === 1 ? '取消有帮助反馈' : '回答有帮助'"
        @click="toggleRating(1)"
      >
        <template #icon><n-icon><ThumbsUpOutline /></n-icon></template>
        有帮助
      </n-button>
      <n-button
        size="tiny"
        quaternary
        :type="currentRating === -1 ? 'primary' : 'default'"
        :disabled="saving"
        :aria-pressed="currentRating === -1"
        :aria-label="currentRating === -1 ? '取消需改进反馈' : '回答需要改进'"
        @click="toggleRating(-1)"
      >
        <template #icon><n-icon><ThumbsDownOutline /></n-icon></template>
        需改进
      </n-button>
      <span v-if="saving" class="feedback-hint" role="status">保存中…</span>
    </div>
    <div v-if="commentOpen && currentRating === -1" class="feedback-comment">
      <n-input
        v-model:value="comment"
        type="textarea"
        size="small"
        :autosize="{ minRows: 1, maxRows: 3 }"
        :disabled="saving"
        placeholder="哪里需要改进？（选填）"
        aria-label="回答需要改进的原因（选填）"
      />
      <div class="comment-actions">
        <n-button size="tiny" quaternary :disabled="saving" @click="commentOpen = false">跳过</n-button>
        <n-button size="tiny" type="primary" :loading="saving" :disabled="!comment.trim()" @click="saveComment">
          提交原因
        </n-button>
      </div>
    </div>
    <div v-if="error" class="feedback-error" role="alert">{{ error }}</div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { ThumbsDownOutline, ThumbsUpOutline } from '@vicons/ionicons5'
import { submitMessageFeedback, submitPublicMessageFeedback } from '@/api'
import type { FeedbackRating } from '@/api/types'

const props = withDefaults(defineProps<{
  messageId: string
  rating?: FeedbackRating
  publicAppId?: string
}>(), { rating: 0, publicAppId: '' })
const emit = defineEmits<{ 'update:rating': [FeedbackRating] }>()
const currentRating = ref<FeedbackRating>(props.rating)
const saving = ref(false)
const commentOpen = ref(false)
const comment = ref('')
const error = ref('')

watch(() => props.rating, value => { currentRating.value = value })
watch(() => props.messageId, () => {
  currentRating.value = props.rating
  commentOpen.value = false
  comment.value = ''
  error.value = ''
})

async function submit(rating: FeedbackRating, reason?: string) {
  if (saving.value || !props.messageId) return false
  saving.value = true
  error.value = ''
  const messageId = props.messageId
  try {
    const body = { rating, ...(reason ? { comment: reason } : {}) }
    const result = props.publicAppId
      ? await submitPublicMessageFeedback(props.publicAppId, messageId, body)
      : await submitMessageFeedback(messageId, body)
    if (props.messageId !== messageId) return false
    currentRating.value = result.rating
    emit('update:rating', result.rating)
    return true
  } catch (e: any) {
    if (props.messageId === messageId) error.value = e.message || '反馈保存失败，请重试'
    return false
  } finally {
    saving.value = false
  }
}

async function toggleRating(rating: 1 | -1) {
  const nextRating = currentRating.value === rating ? 0 : rating
  if (await submit(nextRating)) {
    commentOpen.value = nextRating === -1
    comment.value = ''
  }
}

async function saveComment() {
  if (!comment.value.trim()) return
  if (await submit(-1, comment.value.trim())) commentOpen.value = false
}
</script>

<style scoped>
.message-feedback {
  margin-top: 6px;
  width: 100%;
  white-space: normal;
}
.feedback-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
}
.feedback-hint {
  font-size: 11px;
  color: #6b7280;
}
.feedback-comment {
  max-width: 420px;
  margin-top: 6px;
}
.comment-actions {
  display: flex;
  justify-content: flex-end;
  gap: 6px;
  margin-top: 6px;
}
.feedback-error {
  margin-top: 5px;
  font-size: 12px;
  color: #d22d3d;
  line-height: 1.6;
  overflow-wrap: anywhere;
}
</style>
