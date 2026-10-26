import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export type Role = 'admin' | 'manager' | 'user'

const STORAGE_KEY = 'rag-zhongtai-role'

export const roleMeta: Record<Role, { label: string; desc: string }> = {
  admin: { label: '管理员', desc: '全权限：模型配置、日志监测、知识库管理、对话' },
  manager: { label: '知识库管理人员', desc: '创建知识库、导入与管理文档、测试检索' },
  user: { label: '使用者', desc: '选择知识库进行在线对话' }
}

export const useAppStore = defineStore('app', () => {
  const role = ref<Role | null>(localStorage.getItem(STORAGE_KEY) as Role | null)

  const setRole = (r: Role) => {
    role.value = r
    localStorage.setItem(STORAGE_KEY, r)
  }

  const clearRole = () => {
    role.value = null
    localStorage.removeItem(STORAGE_KEY)
  }

  const roleLabel = computed(() => (role.value ? roleMeta[role.value].label : ''))

  return { role, setRole, clearRole, roleLabel }
})
