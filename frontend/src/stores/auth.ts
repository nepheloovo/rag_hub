import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api } from '@/api/client'

export type Role = 'platform_admin' | 'app_developer' | 'kb_admin' | 'business_user'

export const roleLabels: Record<Role, string> = {
  platform_admin: '平台管理员',
  app_developer: '应用开发者',
  kb_admin: '知识库管理员',
  business_user: '业务使用者'
}

export interface AuthUser {
  id: string
  username: string
  display_name: string
  department: string
  role: Role
}

const TOKEN_KEY = 'zhishu-token'
const USER_KEY = 'zhishu-user'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem(TOKEN_KEY))
  const user = ref<AuthUser | null>(JSON.parse(localStorage.getItem(USER_KEY) || 'null'))

  const role = computed<Role | null>(() => user.value?.role || null)
  const displayName = computed(() => user.value?.display_name || user.value?.username || '')

  async function login(username: string, password: string) {
    const resp = await api<{ token: string; user: AuthUser }>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password })
    })
    token.value = resp.token
    user.value = resp.user
    localStorage.setItem(TOKEN_KEY, resp.token)
    localStorage.setItem(USER_KEY, JSON.stringify(resp.user))
  }

  async function refreshMe() {
    try {
      const me = await api<AuthUser>('/auth/me')
      user.value = me
      localStorage.setItem(USER_KEY, JSON.stringify(me))
    } catch {
      logout()
    }
  }

  function logout() {
    token.value = null
    user.value = null
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
    localStorage.removeItem('rag-zhongtai-role') // 兼容旧版
  }

  return { token, user, role, displayName, login, logout, refreshMe }
})
