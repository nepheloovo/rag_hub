<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2 class="page-title">工具与模型</h2>
        <p class="page-desc">统一管理应用可用的模型和工具。工具一次接入，所有 Chat Flow 与 Agent 都能复用。</p>
      </div>
    </div>

    <n-card size="small" style="margin-bottom: 16px">
      <n-tabs v-model:value="activeTab" type="line">
        <n-tab-pane name="tools" tab="工具库">
          <n-empty description="工具模块规划中（路线图 Phase 3）" style="padding: 48px 0">
            <template #extra>
              <div class="plan-tip">
                规划能力：HTTP 工具（订单查询/创建工单/客户档案）、MCP 服务、工作流插件（BI 查询）、系统内置（联网搜索/导出 Word），统一接入供应用调用并统计用量。
              </div>
            </template>
          </n-empty>
        </n-tab-pane>
        <n-tab-pane name="mcp" tab="MCP 服务">
          <n-empty description="MCP 服务接入规划中" style="padding: 48px 0" />
        </n-tab-pane>
        <n-tab-pane name="models" tab="模型">
          <div style="max-width: 640px; margin-top: 12px">
            <n-alert type="info" :bordered="false">
              模型按用途分组（默认对话/推理/长文写作/视觉/重排/本地部署）规划中。当前可在
              <n-button text type="primary" size="small" @click="$router.push('/app/models')">模型配置</n-button>
              中管理服务商与 embedding / Rerank / LLM 模型。
            </n-alert>
          </div>
        </n-tab-pane>
      </n-tabs>
    </n-card>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
const activeTab = ref('tools')
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
  max-width: 560px;
  font-size: 13px;
  line-height: 1.8;
  color: #6b7280;
}
</style>
