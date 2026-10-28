<template>
  <div class="login-page">
    <div class="login-card">
      <div class="logo-row">
        <div class="logo-mark">
          <n-icon size="26" color="#fff"><GridOutline /></n-icon>
        </div>
        <span class="logo-text">知枢 · AI 应用中台</span>
      </div>
      <h2 class="title">登录</h2>
      <p class="subtitle">使用企业账号登录（SSO 接入前使用本地账号）</p>

      <n-form label-placement="top">
        <n-form-item label="用户名">
          <n-input v-model:value="username" placeholder="用户名" @keydown.enter="doLogin" />
        </n-form-item>
        <n-form-item label="密码">
          <n-input
            v-model:value="password"
            type="password"
            show-password-on="click"
            placeholder="密码"
            @keydown.enter="doLogin"
          />
        </n-form-item>
      </n-form>

      <n-button type="primary" size="large" block :loading="loading" :disabled="!username.trim() || !password" @click="doLogin">
        登录
      </n-button>

      <n-divider>或使用企业身份登录</n-divider>
      <div class="sso-row">
        <n-button block secondary :disabled="!sso.feishu.enabled" @click="ssoHint('feishu')">
          飞书登录
        </n-button>
        <n-button block secondary :disabled="!sso.wecom.enabled" @click="ssoHint('wecom')">
          企业微信登录
        </n-button>
      </div>
      <div class="demo-hint">
        演示账号：admin / admin123（平台管理员）
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import { GridOutline } from '@vicons/ionicons5'
import { api } from '@/api/client'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const message = useMessage()
const store = useAuthStore()

const username = ref('')
const password = ref('')
const loading = ref(false)
const sso = ref<any>({ feishu: { enabled: false, note: '' }, wecom: { enabled: false, note: '' } })

async function doLogin() {
  loading.value = true
  try {
    await store.login(username.value.trim(), password.value)
    message.success('登录成功')
    router.push('/app/workbench')
  } catch (e: any) {
    message.error(e.message)
  } finally {
    loading.value = false
  }
}

function ssoHint(channel: string) {
  message.info(channel === 'feishu' ? sso.value.feishu.note : sso.value.wecom.note)
}

onMounted(async () => {
  try {
    sso.value = await api('/auth/sso-config')
  } catch {
    /* 静默 */
  }
  // 已登录直接进入
  if (store.token) {
    try {
      await store.refreshMe()
      router.push('/app/workbench')
    } catch {
      /* 保持登录页 */
    }
  }
})
</script>

<style scoped>
.login-page {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(160deg, #f0f4ff 0%, #f5f6f8 45%, #eef3ff 100%);
}

.login-card {
  width: 420px;
  padding: 40px 40px 32px;
  background: #fff;
  border-radius: 16px;
  box-shadow: 0 8px 32px rgba(31, 41, 99, 0.08);
}

.logo-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.logo-mark {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  background: linear-gradient(135deg, #3370ff, #5c8aff);
  display: flex;
  align-items: center;
  justify-content: center;
}

.logo-text {
  font-size: 18px;
  font-weight: 700;
  color: #1f2329;
}

.title {
  margin: 24px 0 6px;
  font-size: 22px;
  font-weight: 700;
  color: #1f2329;
}

.subtitle {
  margin: 0 0 20px;
  font-size: 13px;
  color: #8f959e;
}

.sso-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.demo-hint {
  margin-top: 16px;
  font-size: 12px;
  color: #a8adb5;
  text-align: center;
}
</style>
