<template>
  <div class="cb-page">
    <n-spin size="large" />
    <div class="cb-text">正在完成飞书登录…</div>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'

const route = useRoute()
const router = useRouter()
const message = useMessage()

onMounted(() => {
  const token = route.query.token as string
  const userRaw = route.query.user as string
  if (token && userRaw) {
    try {
      const user = JSON.parse(userRaw)
      localStorage.setItem('zhishu-token', token)
      localStorage.setItem('zhishu-user', JSON.stringify(user))
      message.success(`欢迎，${user.display_name || user.username}`)
      router.replace('/app/workbench')
      return
    } catch {
      /* fallthrough */
    }
  }
  message.error('飞书登录失败，请重试')
  router.replace('/login')
})
</script>

<style scoped>
.cb-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 14px;
  background: #f5f6f8;
}

.cb-text {
  font-size: 14px;
  color: #6b7280;
}
</style>
