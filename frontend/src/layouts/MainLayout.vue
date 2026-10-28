<template>
  <n-layout has-sider position="absolute" style="height: 100%">
    <n-layout-sider
      bordered
      :width="224"
      :native-scrollbar="false"
      style="background: #fff"
    >
      <div class="side-logo">
        <div class="logo-mark">
          <n-icon size="20" color="#fff"><GridOutline /></n-icon>
        </div>
        <span>知枢</span>
      </div>

      <n-menu
        :value="activeKey"
        :options="menuOptions"
        :indent="20"
        @update:value="onMenuSelect"
      />

      <div class="side-bottom">
        <n-tag :bordered="false" type="info" size="small" round>{{ store.roleLabel }}</n-tag>
        <n-button text size="small" style="color: #8f959e" @click="switchRole">
          切换角色
        </n-button>
      </div>
    </n-layout-sider>

    <n-layout style="background: #f5f6f8">
      <n-layout-header bordered style="background: #fff; height: 56px; padding: 0 24px">
        <div class="header-row">
          <span class="header-title">{{ route.meta.title || '' }}</span>
          <n-space align="center" :size="12">
            <n-tag :bordered="false" type="info" size="small" round>{{ store.roleLabel }}</n-tag>
            <n-tooltip trigger="hover">
              <template #trigger>
                <n-button quaternary circle size="small" @click="switchRole">
                  <template #icon><n-icon><ExitOutline /></n-icon></template>
                </n-button>
              </template>
              退出并切换角色
            </n-tooltip>
          </n-space>
        </div>
      </n-layout-header>

      <n-layout-content
        :native-scrollbar="true"
        :content-style="{ height: 'calc(100vh - 56px)', overflowY: 'auto' }"
      >
        <router-view />
      </n-layout-content>
    </n-layout>
  </n-layout>
</template>

<script setup lang="ts">
import { computed, h, markRaw } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NIcon } from 'naive-ui'
import {
  Library,
  GridOutline,
  HomeOutline,
  ConstructOutline,
  BarChartOutline,
  FolderOpenOutline,
  SettingsOutline,
  ExitOutline
} from '@vicons/ionicons5'
import { useAppStore } from '@/stores/app'

const route = useRoute()
const router = useRouter()
const store = useAppStore()

function renderIcon(icon: any) {
  return () => h(NIcon, null, { default: () => h(icon) })
}

const allMenus = [
  { key: 'workbench', label: '工作台', icon: renderIcon(markRaw(HomeOutline)), path: '/app/workbench', roles: ['admin', 'manager', 'user'] },
  { key: 'apps', label: '应用', icon: renderIcon(markRaw(GridOutline)), path: '/app/apps', roles: ['admin', 'manager', 'user'] },
  { key: 'knowledge', label: '知识库', icon: renderIcon(markRaw(FolderOpenOutline)), path: '/app/knowledge', roles: ['admin', 'manager'] },
  { key: 'tools', label: '工具', icon: renderIcon(markRaw(ConstructOutline)), path: '/app/tools', roles: ['admin', 'manager'] },
  { key: 'dashboard', label: '看板', icon: renderIcon(markRaw(BarChartOutline)), path: '/app/dashboard', roles: ['admin', 'manager'] },
  { key: 'settings', label: '设置', icon: renderIcon(markRaw(SettingsOutline)), path: '/app/settings', roles: ['admin'] }
]

const menuOptions = computed(() =>
  allMenus
    .filter(m => store.role && m.roles.includes(store.role))
    .map(m => ({ key: m.key, label: m.label, icon: m.icon }))
)

const activeKey = computed(() => {
  if (route.name === 'knowledge-detail') return 'knowledge'
  if (route.name === 'app-detail') return 'apps'
  if (route.name === 'models') return 'settings'
  if (route.name === 'logs') return 'settings'
  const found = allMenus.find(m => m.path === route.path)
  return found ? found.key : 'workbench'
})

function onMenuSelect(key: string) {
  const menu = allMenus.find(m => m.key === key)
  if (menu) router.push(menu.path)
}

function switchRole() {
  store.clearRole()
  router.push('/')
}
</script>

<style scoped>
.side-logo {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 16px 20px;
  font-size: 16px;
  font-weight: 700;
  color: #1f2329;
}

.logo-mark {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: linear-gradient(135deg, #3370ff, #5c8aff);
  display: flex;
  align-items: center;
  justify-content: center;
}

.side-bottom {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  padding: 14px 20px;
  border-top: 1px solid #f0f1f3;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.header-row {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.header-title {
  font-size: 15px;
  font-weight: 600;
  color: #1f2329;
}
</style>
