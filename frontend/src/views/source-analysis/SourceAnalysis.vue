<template>
  <div class="source-analysis">
    <el-card shadow="never" class="hero">
      <div class="hero-head">
        <div>
          <h2>源码分析 · 自动生成用例</h2>
          <p class="sub">
            输入本地项目目录，平台会静态解析接口、参数与校验规则，再由大模型生成测试用例。
            整个过程只读，不会修改目标项目。
          </p>
        </div>
        <el-tag type="info" effect="plain">只读分析</el-tag>
      </div>

      <div class="path-row">
        <el-input
          v-model="path"
          placeholder="例如：C:\Users\HP\Desktop\pingjian-ai-assistant-lc"
          clearable
          @keyup.enter="runAnalyze"
        >
          <template #prefix><el-icon><FolderOpened /></el-icon></template>
        </el-input>
        <el-button type="primary" :loading="loading" @click="runAnalyze">
          {{ loading ? '分析中…' : '开始分析' }}
        </el-button>
      </div>

      <div v-if="loading" class="progress">
        <el-steps :active="stage" finish-status="success" simple>
          <el-step title="扫描目录" />
          <el-step title="解析接口" />
          <el-step title="生成用例" />
        </el-steps>
        <p class="tip">正在分析 {{ path }}，接口较多或调用大模型时需要几十秒，请稍候…</p>
      </div>
    </el-card>

    <template v-if="job">
      <el-row :gutter="16" class="stats">
        <el-col :span="6"><el-card shadow="never"><div class="stat"><b>{{ job.stats.file_count || 0 }}</b><span>扫描文件</span></div></el-card></el-col>
        <el-col :span="6"><el-card shadow="never"><div class="stat"><b>{{ job.stats.endpoint_count || 0 }}</b><span>识别接口</span></div></el-card></el-col>
        <el-col :span="6"><el-card shadow="never"><div class="stat"><b>{{ job.stats.case_count || 0 }}</b><span>生成用例</span></div></el-card></el-col>
        <el-col :span="6"><el-card shadow="never"><div class="stat"><b>{{ job.stats.table_count || 0 }}</b><span>数据表</span></div></el-card></el-col>
      </el-row>

      <el-card shadow="never" class="result">
        <div class="result-head">
          <div class="meta">
            <el-tag>{{ job.framework || '未知框架' }}</el-tag>
            <el-tag :type="job.mode === 'ai' ? 'success' : 'warning'" effect="dark">
              {{ job.mode === 'ai' ? 'AI 生成' : '规则兜底生成' }}
            </el-tag>
            <el-tag v-if="job.stats.auth" type="danger" effect="plain">项目需要鉴权</el-tag>
            <span class="path-text">{{ job.project_path }}</span>
          </div>
          <el-button type="success" :loading="importing" @click="importCases">导入到项目</el-button>
        </div>

        <el-alert
          v-if="job.status === 'failed'"
          type="error"
          :title="job.error || '分析失败'"
          :closable="false"
          show-icon
        />

        <el-tabs v-model="tab">
          <el-tab-pane label="接口清单" name="endpoints">
            <el-table :data="job.endpoints" size="small" border max-height="420">
              <el-table-column prop="method" label="方法" width="80">
                <template #default="{ row }"><el-tag size="small">{{ row.method }}</el-tag></template>
              </el-table-column>
              <el-table-column prop="path" label="路径" min-width="220" show-overflow-tooltip />
              <el-table-column prop="module" label="模块" width="130" />
              <el-table-column label="请求体" min-width="160">
                <template #default="{ row }">
                  <span v-if="row.body_fields && row.body_fields.length">
                    {{ row.body_fields.map(f => f.name).join(', ') }}
                  </span>
                  <span v-else class="muted">—</span>
                </template>
              </el-table-column>
              <el-table-column label="参数" min-width="150">
                <template #default="{ row }">
                  <span v-if="row.query && row.query.length">query: {{ row.query.join(', ') }}</span>
                  <span v-if="row.path_vars && row.path_vars.length">path: {{ row.path_vars.join(', ') }}</span>
                  <span v-if="!row.query?.length && !row.path_vars?.length" class="muted">—</span>
                </template>
              </el-table-column>
              <el-table-column label="鉴权" width="70">
                <template #default="{ row }">
                  <el-tag v-if="row.auth" type="danger" size="small">是</el-tag>
                  <span v-else class="muted">否</span>
                </template>
              </el-table-column>
            </el-table>
          </el-tab-pane>

          <el-tab-pane :label="`生成用例（${(job.cases || []).length}）`" name="cases">
            <el-table :data="job.cases" size="small" border max-height="480">
              <el-table-column type="expand">
                <template #default="{ row }">
                  <div class="case-detail">
                    <p><b>前置条件：</b>{{ row.preconditions || '—' }}</p>
                    <p><b>操作步骤：</b><br>{{ row.steps || '—' }}</p>
                    <p><b>预期结果：</b>{{ row.expected || '—' }}</p>
                  </div>
                </template>
              </el-table-column>
              <el-table-column type="index" width="50" />
              <el-table-column prop="title" label="用例标题" min-width="320" show-overflow-tooltip />
              <el-table-column label="场景" width="90">
                <template #default="{ row }">
                  <el-tag size="small" :type="sceneType(row.scene)">{{ sceneText(row.scene) }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="priority" label="优先级" width="80" />
              <el-table-column prop="module" label="模块" width="110" />
              <el-table-column label="接口" min-width="200" show-overflow-tooltip>
                <template #default="{ row }">{{ row.method }} {{ row.path }}</template>
              </el-table-column>
            </el-table>
          </el-tab-pane>
        </el-tabs>
      </el-card>
    </template>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { FolderOpened } from '@element-plus/icons-vue'
import api from '@/utils/api'

const path = ref('C:\\Users\\HP\\Desktop\\pingjian-ai-assistant-lc')
const loading = ref(false)
const importing = ref(false)
const stage = ref(1)
const tab = ref('cases')
const job = ref(null)

const scenes = {
  normal: { text: '正常', type: 'success' },
  boundary: { text: '边界', type: 'warning' },
  exception: { text: '异常', type: 'danger' },
  auth: { text: '权限', type: 'info' },
}
const sceneText = (s) => scenes[s]?.text || s
const sceneType = (s) => scenes[s]?.type || 'info'

async function runAnalyze () {
  if (!path.value.trim()) {
    ElMessage.warning('请填写项目路径')
    return
  }
  loading.value = true
  stage.value = 1
  job.value = null
  const timer = setInterval(() => { if (stage.value < 2) stage.value += 1 }, 1500)
  try {
    const { data } = await api.post('/source-analysis/analyze/', { path: path.value.trim() }, { timeout: 180000 })
    job.value = data
    stage.value = 3
    if (data.status === 'failed') {
      ElMessage.error(data.error || '分析失败')
    } else {
      ElMessage.success(`已识别 ${data.stats.endpoint_count} 个接口，生成 ${data.stats.case_count} 条用例`)
    }
  } catch (e) {
    ElMessage.error(e?.response?.data?.error || '分析请求失败')
  } finally {
    clearInterval(timer)
    loading.value = false
  }
}

async function importCases () {
  try {
    await ElMessageBox.confirm('将把当前生成的用例导入项目（草稿状态），未导入的不受影响。', '导入用例', { type: 'info' })
  } catch {
    return
  }
  importing.value = true
  try {
    const { data } = await api.post(`/source-analysis/jobs/${job.value.id}/import/`, {})
    ElMessageBox.alert(`已导入 ${data.imported} 条用例到项目「${data.project_name}」，可在「用例管理」中查看。`, '导入完成', { type: 'success' })
  } catch (e) {
    ElMessage.error(e?.response?.data?.error || '导入失败')
  } finally {
    importing.value = false
  }
}
</script>

<style scoped>
.source-analysis { padding: 4px; }
.hero-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }
.hero h2 { margin: 0 0 6px; font-size: 20px; }
.sub { margin: 0; color: #666; font-size: 13px; line-height: 1.7; }
.path-row { display: flex; gap: 12px; margin-top: 18px; }
.progress { margin-top: 18px; }
.tip { margin: 10px 0 0; color: #999; font-size: 12px; }
.stats { margin-top: 16px; }
.stat { display: flex; flex-direction: column; align-items: center; }
.stat b { font-size: 26px; color: #1890ff; }
.stat span { color: #888; font-size: 12px; margin-top: 4px; }
.result { margin-top: 16px; }
.result-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.meta { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.path-text { color: #999; font-size: 12px; margin-left: 4px; }
.muted { color: #bbb; }
.case-detail { padding: 4px 24px; color: #555; font-size: 13px; line-height: 1.8; }
.case-detail p { margin: 2px 0; }
</style>
