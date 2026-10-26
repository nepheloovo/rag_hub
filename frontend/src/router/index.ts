import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    name: 'role-select',
    component: () => import('@/views/RoleSelect.vue')
  },
  {
    path: '/app',
    component: () => import('@/layouts/MainLayout.vue'),
    children: [
      { path: '', redirect: '/app/apps' },
      {
        path: 'apps',
        name: 'apps',
        component: () => import('@/views/apps/AppList.vue'),
        meta: { title: '应用', roles: ['admin', 'manager', 'user'] }
      },
      {
        path: 'apps/:id',
        name: 'app-detail',
        component: () => import('@/views/apps/AppDetail.vue'),
        meta: { title: '应用详情', roles: ['admin', 'manager', 'user'] }
      },
      {
        path: 'chat',
        name: 'chat',
        component: () => import('@/views/chat/ChatView.vue'),
        meta: { title: '对话（调试）', roles: ['admin', 'manager', 'user'] }
      },
      {
        path: 'knowledge',
        name: 'knowledge',
        component: () => import('@/views/kb/KnowledgeList.vue'),
        meta: { title: '知识库', roles: ['admin', 'manager'] }
      },
      {
        path: 'knowledge/:id',
        name: 'knowledge-detail',
        component: () => import('@/views/kb/KnowledgeDetail.vue'),
        meta: { title: '知识库详情', roles: ['admin', 'manager'] }
      },
      {
        path: 'models',
        name: 'models',
        component: () => import('@/views/settings/ModelConfig.vue'),
        meta: { title: '模型配置', roles: ['admin'] }
      },
      {
        path: 'logs',
        name: 'logs',
        component: () => import('@/views/logs/Logs.vue'),
        meta: { title: '日志监测', roles: ['admin'] }
      }
    ]
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

// 简单角色守卫：未选角色跳回选择页；无权限页面重定向到对话页
router.beforeEach(to => {
  const role = localStorage.getItem('rag-zhongtai-role')
  if (to.path.startsWith('/app') && !role) return { path: '/' }
  if (to.meta.roles && role && !(to.meta.roles as string[]).includes(role)) {
    return { path: '/app/chat' }
  }
  return true
})

export default router
