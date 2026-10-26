<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2 class="page-title">模型配置</h2>
        <p class="page-desc">配置模型服务商（OpenRouter / AIHubmix / 通义），支持 Embedding、Rerank、LLM 三类模型</p>
      </div>
    </div>

    <n-card size="small" title="全局默认模型" style="margin-bottom: 16px">
      <div class="default-row">
        <div class="default-item">
          <div class="default-label">默认 Embedding 模型</div>
          <n-select
            v-model:value="defaults.default_embedding"
            :options="embeddingOptions"
            style="width: 300px"
            placeholder="选择模型"
            @update:value="saveDefaults"
          />
        </div>
        <div class="default-item">
          <div class="default-label">默认 Rerank 模型</div>
          <n-select
            v-model:value="defaults.default_rerank"
            :options="rerankOptions"
            style="width: 300px"
            placeholder="未配置时自动降级为纯向量召回"
            clearable
            @update:value="saveDefaults"
          />
        </div>
        <div class="default-item">
          <div class="default-label">默认 LLM 模型</div>
          <n-select
            v-model:value="defaults.default_llm"
            :options="llmOptions"
            style="width: 300px"
            placeholder="选择模型"
            @update:value="saveDefaults"
          />
        </div>
      </div>
    </n-card>

    <n-spin :show="loading">
      <n-card
        v-for="p in providers"
        :key="p.id"
        size="small"
        class="provider-card"
        :class="{ disabled: !p.enabled }"
      >
        <template #header>
          <div class="provider-head">
            <div class="provider-left">
              <div class="provider-logo" :class="p.id">{{ p.name.slice(0, 1) }}</div>
              <span class="provider-name">{{ p.name }}</span>
              <n-tag v-if="p.enabled" size="small" type="success" :bordered="false">已启用</n-tag>
              <n-tag v-else size="small" :bordered="false" type="default">未启用</n-tag>
            </div>
            <n-space :size="10" align="center">
              <n-button size="small" ghost type="primary" :loading="testingId === p.id" @click="doTest(p)">
                测试连通性
              </n-button>
              <n-switch v-model:value="p.enabled" @update:value="() => saveProvider(p)" />
            </n-space>
          </div>
        </template>

        <n-form label-placement="left" label-width="90">
          <n-form-item label="API Key">
            <n-input
              v-model:value="p._draftKey"
              type="password"
              show-password-on="click"
              :placeholder="p.api_key ? '已配置（输入新 Key 可覆盖）' : '输入 API Key'"
              style="max-width: 480px"
              @blur="() => saveProvider(p)"
            />
          </n-form-item>
          <n-form-item label="Base URL">
            <n-input v-model:value="p.base_url" style="max-width: 480px" @blur="() => saveProvider(p)" />
          </n-form-item>
        </n-form>

        <div class="model-groups">
          <div class="model-group">
            <div class="group-label">
              Embedding 模型
              <n-tag size="tiny" :bordered="false" type="info">{{ p.models.embedding.length }}</n-tag>
            </div>
            <div class="tag-wrap">
              <n-tag
                v-for="m in p.models.embedding"
                :key="m"
                closable
                @close="removeModel(p, 'embedding', m)"
              >
                {{ m }}
              </n-tag>
              <n-button size="tiny" quaternary type="primary" @click="addModel(p, 'embedding')">
                <template #icon><n-icon><AddOutline /></n-icon></template>
                添加
              </n-button>
            </div>
          </div>

          <div class="model-group">
            <div class="group-label">
              Rerank 模型
              <n-tag size="tiny" :bordered="false" type="info">{{ p.models.rerank.length }}</n-tag>
            </div>
            <div class="tag-wrap">
              <template v-if="p.models.rerank.length">
                <n-tag
                  v-for="m in p.models.rerank"
                  :key="m"
                  closable
                  @close="removeModel(p, 'rerank', m)"
                >
                  {{ m }}
                </n-tag>
              </template>
              <span v-else class="empty-tip">该服务商暂无 Rerank 模型</span>
              <n-button size="tiny" quaternary type="primary" @click="addModel(p, 'rerank')">
                <template #icon><n-icon><AddOutline /></n-icon></template>
                添加
              </n-button>
            </div>
          </div>

          <div class="model-group">
            <div class="group-label">
              LLM 模型
              <n-tag size="tiny" :bordered="false" type="info">{{ p.models.llm.length }}</n-tag>
            </div>
            <div class="tag-wrap">
              <n-tag
                v-for="m in p.models.llm"
                :key="m"
                closable
                @close="removeModel(p, 'llm', m)"
              >
                {{ m }}
              </n-tag>
              <n-button size="tiny" quaternary type="primary" @click="addModel(p, 'llm')">
                <template #icon><n-icon><AddOutline /></n-icon></template>
                添加
              </n-button>
            </div>
          </div>
        </div>
      </n-card>
    </n-spin>

    <n-card size="small" style="margin-top: 16px">
      <div class="note">
        <n-icon size="16" color="#fa8c16"><AlertCircleOutline /></n-icon>
        <span>
          Rerank 降级策略：对话链路检测到「全局默认 Rerank 模型」为空或调用失败时，自动跳过精排，直接使用向量召回 top-k 结果。
          例如 OpenRouter 无 Rerank 模型，仍可正常完成对话。
        </span>
      </div>
    </n-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, reactive } from 'vue'
import { useMessage, useDialog } from 'naive-ui'
import { AddOutline, AlertCircleOutline } from '@vicons/ionicons5'
import { getDefaults, listProviders, testProvider, updateDefaults, updateProvider } from '@/api'
import type { ModelDefaults, Provider } from '@/api/types'

type ProviderWithDraft = Provider & { _draftKey?: string }

const message = useMessage()
const dialog = useDialog()
const providers = ref<ProviderWithDraft[]>([])
const loading = ref(false)
const testingId = ref<string | null>(null)

const defaults = reactive<ModelDefaults>({
  default_embedding: '',
  default_rerank: '',
  default_llm: ''
})

const embeddingOptions = computed(() =>
  providers.value.flatMap(p => p.models.embedding.map(m => ({ label: `${p.name} · ${m}`, value: `${p.id}:${m}` })))
)
const rerankOptions = computed(() =>
  providers.value.flatMap(p => p.models.rerank.map(m => ({ label: `${p.name} · ${m}`, value: `${p.id}:${m}` })))
)
const llmOptions = computed(() =>
  providers.value.flatMap(p => p.models.llm.map(m => ({ label: `${p.name} · ${m}`, value: `${p.id}:${m}` })))
)

async function load() {
  loading.value = true
  try {
    const [ps, ds] = await Promise.all([listProviders(), getDefaults()])
    providers.value = ps.map(p => ({ ...p, _draftKey: '' }))
    defaults.default_embedding = ds.default_embedding
    defaults.default_rerank = ds.default_rerank
    defaults.default_llm = ds.default_llm
  } catch (e: any) {
    message.error(e.message)
  } finally {
    loading.value = false
  }
}

async function saveProvider(p: ProviderWithDraft) {
  const payload: any = {
    enabled: p.enabled,
    base_url: p.base_url
  }
  if (p._draftKey && p._draftKey.trim()) {
    payload.api_key = p._draftKey.trim()
  }
  try {
    const updated = await updateProvider(p.id, payload)
    p.api_key = updated.api_key
    p._draftKey = ''
    message.success(`「${p.name}」已保存`)
  } catch (e: any) {
    message.error(e.message)
  }
}

async function saveDefaults() {
  try {
    await updateDefaults({
      default_embedding: defaults.default_embedding,
      default_rerank: defaults.default_rerank,
      default_llm: defaults.default_llm
    })
    message.success('默认模型已保存')
  } catch (e: any) {
    message.error(e.message)
  }
}

async function doTest(p: ProviderWithDraft) {
  testingId.value = p.id
  try {
    const result = await testProvider(p.id)
    if (result.ok) {
      message.success(`${p.name}：${result.message}（${result.latency_ms}ms）`)
    } else {
      message.error(`${p.name}：${result.message}`)
    }
  } catch (e: any) {
    message.error(e.message)
  } finally {
    testingId.value = null
  }
}

async function addModel(p: ProviderWithDraft, type: 'embedding' | 'rerank' | 'llm') {
  const name = window.prompt(`请输入 ${type} 模型名称（如 text-embedding-v3）`)
  if (name && name.trim()) {
    const model = name.trim()
    if (!p.models[type].includes(model)) {
      try {
        const updated = await updateProvider(p.id, {
          models: { embedding: p.models.embedding, rerank: p.models.rerank, llm: p.models.llm, [type]: [...p.models[type], model] }
        } as any)
        p.models = updated.models
        message.success('已添加模型')
      } catch (e: any) {
        message.error(e.message)
      }
    }
  }
}

function removeModel(p: ProviderWithDraft, type: 'embedding' | 'rerank' | 'llm', model: string) {
  dialog.warning({
    title: '删除模型',
    content: `确定删除「${model}」吗？删除后使用该模型的配置将失效。`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        const updated = await updateProvider(p.id, {
          models: { embedding: p.models.embedding, rerank: p.models.rerank, llm: p.models.llm, [type]: p.models[type].filter(m => m !== model) }
        } as any)
        p.models = updated.models
        message.success('已删除')
      } catch (e: any) {
        message.error(e.message)
      }
    }
  })
}

onMounted(load)
</script>

<style scoped>
.page-head {
  margin-bottom: 20px;
}

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

.default-row {
  display: flex;
  flex-wrap: wrap;
  gap: 32px;
}

.default-label {
  font-size: 13px;
  color: #4b5563;
  margin-bottom: 8px;
}

.provider-card {
  margin-bottom: 16px;
}

.provider-card.disabled {
  opacity: 0.78;
}

.provider-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.provider-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.provider-logo {
  width: 28px;
  height: 28px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 700;
  color: #fff;
}

.provider-logo.tongyi {
  background: linear-gradient(135deg, #615ced, #8a6dff);
}

.provider-logo.openrouter {
  background: #334155;
}

.provider-logo.aihubmix {
  background: linear-gradient(135deg, #0ea5e9, #22d3ee);
}

.provider-name {
  font-size: 15px;
  font-weight: 600;
  color: #1f2329;
}

.model-groups {
  display: flex;
  flex-direction: column;
  gap: 16px;
  margin-top: 8px;
}

.group-label {
  font-size: 13px;
  font-weight: 600;
  color: #4b5563;
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
}

.tag-wrap {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.empty-tip {
  font-size: 12px;
  color: #a8adb5;
}

.note {
  display: flex;
  gap: 8px;
  font-size: 13px;
  color: #6b7280;
  line-height: 1.7;
  align-items: flex-start;
}
</style>
