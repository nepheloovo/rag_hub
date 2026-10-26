<template>
  <div class="role-page">
    <div class="role-card">
      <div class="logo-row">
        <div class="logo-mark">
          <n-icon size="26" color="#fff"><Library /></n-icon>
        </div>
        <span class="logo-text">企业知识库中台</span>
      </div>
      <h2 class="title">选择你的角色进入</h2>
      <p class="subtitle">当前为 1.0 内测版本，暂未接入登录，请选择本次会话使用的角色</p>

      <div class="role-grid">
        <div
          v-for="r in roles"
          :key="r.key"
          class="role-item"
          :class="{ active: selected === r.key }"
          @click="selected = r.key"
        >
          <n-icon size="30" :color="selected === r.key ? '#3370ff' : '#8f959e'">
            <component :is="r.icon" />
          </n-icon>
          <div class="role-name">{{ r.label }}</div>
          <div class="role-desc">{{ r.desc }}</div>
        </div>
      </div>

      <n-button
        type="primary"
        size="large"
        block
        :disabled="!selected"
        style="margin-top: 24px; height: 44px"
        @click="enter"
      >
        进入系统
      </n-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, markRaw } from 'vue'
import { useRouter } from 'vue-router'
import { NIcon } from 'naive-ui'
import {
  ShieldCheckmarkOutline,
  FolderOpenOutline,
  ChatbubblesOutline,
  Library
} from '@vicons/ionicons5'
import { useAppStore, roleMeta } from '@/stores/app'
import type { Role } from '@/stores/app'

const router = useRouter()
const store = useAppStore()
const selected = ref<Role | null>(null)

const roles: { key: Role; label: string; desc: string; icon: any }[] = [
  { key: 'admin', label: roleMeta.admin.label, desc: roleMeta.admin.desc, icon: markRaw(ShieldCheckmarkOutline) },
  { key: 'manager', label: roleMeta.manager.label, desc: roleMeta.manager.desc, icon: markRaw(FolderOpenOutline) },
  { key: 'user', label: roleMeta.user.label, desc: roleMeta.user.desc, icon: markRaw(ChatbubblesOutline) }
]

function enter() {
  if (!selected.value) return
  store.setRole(selected.value)
  router.push('/app/apps')
}
</script>

<style scoped>
.role-page {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(160deg, #f0f4ff 0%, #f5f6f8 45%, #eef3ff 100%);
}

.role-card {
  width: 560px;
  padding: 40px 44px;
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
  margin: 28px 0 8px;
  font-size: 22px;
  font-weight: 700;
  color: #1f2329;
}

.subtitle {
  margin: 0 0 24px;
  font-size: 13px;
  color: #8f959e;
}

.role-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}

.role-item {
  border: 1.5px solid #e5e7eb;
  border-radius: 12px;
  padding: 20px 14px;
  cursor: pointer;
  transition: all 0.2s;
  text-align: center;
}

.role-item:hover {
  border-color: #b7c8ff;
  background: #f8faff;
}

.role-item.active {
  border-color: #3370ff;
  background: #f0f5ff;
  box-shadow: 0 0 0 2px rgba(51, 112, 255, 0.12);
}

.role-name {
  margin-top: 10px;
  font-size: 15px;
  font-weight: 600;
  color: #1f2329;
}

.role-desc {
  margin-top: 6px;
  font-size: 12px;
  line-height: 1.5;
  color: #8f959e;
}
</style>
