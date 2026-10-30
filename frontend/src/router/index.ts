import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/LoginView.vue')
  },
  {
    path: '/sso-callback',
    name: 'sso-callback',
    component: () => import('@/views/SsoCallback.vue')
  },
  {
    path: '/pub/:appId',
    name: 'public-chat',
    component: () => import('@/views/PublicChat.vue')
  },
  {
    path: '/app',
    component: () => import('@/layouts/MainLayout.vue'),
    children: [
      { path: '', redirect: '/app/workbench' },
      {
        path: 'workbench',
        name: 'workbench',
        component: () => import('@/views/workbench/Workbench.vue'),
        meta: { title: '工作台', roles: ['platform_admin', 'app_developer', 'kb_admin', 'business_user'] }
      },
      {
        path: 'apps',
        name: 'apps',
        component: () => import('@/views/apps/AppList.vue'),
        meta: { title: '应用', roles: ['platform_admin', 'app_developer', 'kb_admin', 'business_user'] }
      },
      {
        path: 'apps/:id',
        name: 'app-detail',
        component: () => import('@/views/apps/AppDetail.vue'),
        meta: { title: '应用详情', roles: ['platform_admin', 'app_developer', 'kb_admin', 'business_user'] }
      },
      {
        path: 'knowledge',
        name: 'knowledge',
        component: () => import('@/views/kb/KnowledgeList.vue'),
        meta: { title: '知识库', roles: ['platform_admin', 'app_developer', 'kb_admin'] }
      },
      {
        path: 'knowledge/:id',
        name: 'knowledge-detail',
        component: () => import('@/views/kb/KnowledgeDetail.vue'),
        meta: { title: '知识库详情', roles: ['platform_admin', 'app_developer', 'kb_admin'] }
      },
      {
        path: 'tools',
        name: 'tools',
        component: () => import('@/views/placeholder/ToolsView.vue'),
        meta: { title: '工具', roles: ['platform_admin', 'app_developer', 'kb_admin'] }
      },
      {
        path: 'dashboard',
        name: 'dashboard',
        component: () => import('@/views/placeholder/DashboardView.vue'),
        meta: { title: '看板', roles: ['platform_admin', 'app_developer', 'kb_admin'] }
      },
      {
        path: 'settings',
        name: 'settings',
        component: () => import('@/views/placeholder/SettingsView.vue'),
        meta: { title: '设置', roles: ['platform_admin'] }
      },
      {
        path: 'models',
        name: 'models',
        component: () => import('@/views/settings/ModelConfig.vue'),
        meta: { title: '模型配置', roles: ['platform_admin'] }
      },
      {
        path: 'observability',
        name: 'observability',
        component: () => import('@/views/observability/Observability.vue'),
        meta: { title: '可观测中心', roles: ['platform_admin', 'app_developer', 'kb_admin'] }
      },
      {
        path: 'observability/traces/:id',
        name: 'trace-detail',
        component: () => import('@/views/observability/TraceDetail.vue'),
        meta: { title: '调用链路', roles: ['platform_admin', 'app_developer', 'kb_admin'] }
      },
      {
        path: 'eval',
        name: 'eval',
        component: () => import('@/views/eval/EvalCenter.vue'),
        meta: { title: '评测集', roles: ['platform_admin', 'app_developer', 'kb_admin'] }
      },
      {
        path: 'eval/:id',
        name: 'eval-set-detail',
        component: () => import('@/views/eval/EvalSetDetail.vue'),
        meta: { title: '评测集详情', roles: ['platform_admin', 'app_developer', 'kb_admin'] }
      },
      {
        path: 'logs',
        redirect: { path: '/app/observability', query: { tab: 'logs' } }
      }
    ]
  },
  {
    path: '/',
    redirect: '/app/workbench'
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

// 认证守卫：无 token 跳登录页；角色不匹配跳工作台
router.beforeEach(to => {
  const token = localStorage.getItem('zhishu-token')
  const isPublic = to.path.startsWith('/pub/') || to.path === '/login'
  if (to.path.startsWith('/app') && !token) return { path: '/login', query: { redirect: to.fullPath } }
  if (isPublic) return true
  const userRaw = localStorage.getItem('zhishu-user')
  const role = userRaw ? JSON.parse(userRaw).role : null
  if (to.meta.roles && role && !(to.meta.roles as string[]).includes(role)) {
    return { path: '/app/workbench' }
  }
  return true
})

export default router
