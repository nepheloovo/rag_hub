<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2 class="page-title">设置</h2>
        <p class="page-desc">团队、角色与权限、Agent 接入和审计</p>
      </div>
    </div>

    <n-card size="small">
      <n-tabs v-model:value="activeTab" type="line">
        <n-tab-pane name="members" tab="成员">
          <n-empty description="成员管理规划中（路线图 Phase 4：企业 SSO 飞书/企业微信 同步）" style="padding: 48px 0">
            <template #extra>
              <div class="plan-tip">
                当前阶段暂用前端角色选择（管理员 / 知识库管理人员 / 使用者）代替真实成员体系。SSO 接入后：成员按部门自动同步，支持平台管理员 / 应用开发者 / 知识库管理员 / 业务使用者四种角色。
              </div>
            </template>
          </n-empty>
        </n-tab-pane>
        <n-tab-pane name="roles" tab="角色与权限">
          <div style="margin-top: 12px">
            <n-data-table :columns="columns" :data="rows" :bordered="false" :pagination="false" />
          </div>
        </n-tab-pane>
        <n-tab-pane name="agent" tab="Agent 接入">
          <n-empty description="发布渠道接入规划中（路线图 Phase 3：官网嵌入 / 企业微信）" style="padding: 48px 0" />
        </n-tab-pane>
        <n-tab-pane name="audit" tab="审计日志">
          <n-alert type="info" :bordered="false" style="margin-top: 12px">
            对话日志（查询内容 / Token / 时长）已可用，见
            <n-button text type="primary" size="small" @click="$router.push('/app/logs')">日志监测</n-button>
            。全操作审计留痕规划于 Phase 4。
          </n-alert>
        </n-tab-pane>
      </n-tabs>
    </n-card>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const activeTab = ref('members')

const columns = [
  { title: '角色', key: 'name', width: 180 },
  { title: '说明', key: 'desc' },
  { title: '状态', key: 'status', width: 120 }
]
const rows = [
  { name: '管理员', desc: '全部功能：应用/知识库/工具/模型配置/看板/设置/日志', status: '已可用' },
  { name: '知识库管理人员', desc: '知识库管理、应用搭建（原型暂按此边界）', status: '已可用' },
  { name: '业务使用者', desc: '使用已发布应用对话', status: '已可用' },
  { name: '应用开发者', desc: '编排应用、管理工具（Phase 4 细化）', status: '规划中' }
]
</script>

<style scoped>
.page-title {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  color: #1f2329;
}

.page-desc {
  margin: 6px 0 0;
  font-size: 13px;
  color: #8f959e;
}

.page-head {
  margin-bottom: 20px;
}

.plan-tip {
  max-width: 620px;
  font-size: 13px;
  line-height: 1.8;
  color: #6b7280;
}
</style>
