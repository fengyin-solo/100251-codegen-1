<template>
  <section class="page inspection-page" data-module="inspection">
    <header class="page-head">
      <div>
        <h2>信号设备巡检</h2>
        <p class="page-desc">
          巡检计划按「待下发 → 执行中 → 已复核」流转；现场问题逐项挂载，复核驳回写清原因，复核通过后归档锁定。
        </p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">新建巡检计划</button>
        <button class="btn" type="button" @click="exportRows">导出巡检清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar inspection-filter" @submit.prevent="reload">
      <label class="filter-item">
        <span>关键词</span>
        <input v-model="keyword" placeholder="按巡检计划编号或车站检索" />
      </label>
      <label class="filter-item">
        <span>计划状态</span>
        <select v-model="statusFilter">
          <option value="">全部状态</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
      <button class="btn ghost" type="button" @click="reload">刷新</button>
    </form>

    <table class="data-table plan-table">
      <thead>
        <tr>
          <th>巡检计划编号</th>
          <th>巡检日期</th>
          <th>所属车站</th>
          <th>作业班组</th>
          <th>状态</th>
          <th>巡检进度</th>
          <th>现场问题</th>
          <th>下发人</th>
          <th>最近执行人</th>
          <th>复核人</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)" :class="{ archived: row.archived }">
          <td>
            <button class="link" type="button" @click="selectPlan(row.id)">{{ row['巡检计划编号'] }}</button>
          </td>
          <td>{{ row['巡检日期'] || '—' }}</td>
          <td>{{ row['所属车站'] || '—' }}</td>
          <td>{{ row['作业班组'] || '—' }}</td>
          <td><span class="status-badge" :data-status="row.status">{{ row.status }}</span></td>
          <td>{{ progressText(row) }}</td>
          <td>{{ issueCount(row) }}</td>
          <td>{{ row['下发人'] || '—' }}</td>
          <td>{{ row['最近执行人'] || '—' }}</td>
          <td>{{ row['复核人'] || '—' }}</td>
          <td class="row-actions">
            <button class="link" type="button" @click="selectPlan(row.id)">查看</button>
            <button v-if="row.status === '待下发' && !row.archived" class="link" type="button" @click="dispatch(row)">
              下发
            </button>
            <button v-if="row.status === '执行中' && !row.archived" class="link" type="button" @click="openReview(row)">
              提交复核
            </button>
            <span v-if="row.archived" class="archive-text">已归档</span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td colspan="11" class="empty-state">暂无巡检计划，可先新建一份计划</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条巡检计划</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <section v-if="selectedPlan" class="detail-panel">
      <header class="detail-head">
        <div>
          <h3>{{ selectedPlan['巡检计划编号'] }} · {{ selectedPlan['所属车站'] }}</h3>
          <p>
            {{ selectedPlan.status }}
            <template v-if="selectedPlan.archived"> · 已归档，不允许再改动</template>
            <template v-if="selectedPlan['驳回原因']"> · 最近驳回原因：{{ selectedPlan['驳回原因'] }}</template>
          </p>
        </div>
        <button class="btn ghost" type="button" @click="selectedPlan = null">关闭明细</button>
      </header>

      <h4>巡检清单与巡检记录明细</h4>
      <table class="data-table item-table">
        <thead>
          <tr>
            <th>#</th>
            <th>巡检项</th>
            <th>设备编号</th>
            <th>巡检内容</th>
            <th>巡检标准</th>
            <th>巡检清单结论</th>
            <th>巡检记录明细结论</th>
            <th>执行人</th>
            <th>执行时间</th>
            <th>现场问题</th>
            <th v-if="selectedPlan.status === '执行中'">现场操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in selectedPlan['巡检清单']" :key="String(item.id)">
            <td>{{ item.id }}</td>
            <td>{{ item['巡检项'] }}</td>
            <td>{{ item['设备编号'] }}</td>
            <td>{{ item['巡检内容'] }}</td>
            <td>{{ item['巡检标准'] || '—' }}</td>
            <td>
              <span class="conclusion" :data-conclusion="item['清单结论']">{{ item['清单结论'] }}</span>
            </td>
            <td>
              <span class="conclusion" :data-conclusion="recordOf(item.id)?.['记录结论']">
                {{ recordOf(item.id)?.['记录结论'] || '待巡检' }}
              </span>
            </td>
            <td>{{ recordOf(item.id)?.['执行人'] || '—' }}</td>
            <td>{{ recordOf(item.id)?.['执行时间'] || '—' }}</td>
            <td>
              <ul v-if="recordOf(item.id)?.['问题列表']?.length" class="issue-list">
                <li v-for="issue in recordOf(item.id)?.['问题列表']" :key="issue['问题编号']">
                  <strong>{{ issue['问题编号'] }}</strong>
                  {{ issue['问题描述'] }}
                  <span class="issue-meta">{{ issue['登记人'] }} · {{ issue['登记时间'] }}</span>
                </li>
              </ul>
              <span v-else>—</span>
            </td>
            <td v-if="selectedPlan.status === '执行中'" class="row-actions">
              <button class="link" type="button" @click="openExecute(item, '正常')">登记正常</button>
              <button class="link danger" type="button" @click="openExecute(item, '异常')">登记异常</button>
              <button class="link" type="button" @click="openIssue(item)">挂现场问题</button>
            </td>
          </tr>
        </tbody>
      </table>

      <h4>流转与交接记录</h4>
      <table class="data-table history-table">
        <thead>
          <tr>
            <th>时间</th>
            <th>动作</th>
            <th>操作人</th>
            <th>原状态</th>
            <th>新状态</th>
            <th>原因 / 说明</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(history, index) in selectedPlan['操作轨迹']" :key="index">
            <td>{{ history['时间'] }}</td>
            <td>{{ history['动作'] }}</td>
            <td>{{ history['操作人'] }}</td>
            <td>{{ history['原状态'] || '—' }}</td>
            <td>{{ history['新状态'] || '—' }}</td>
            <td>{{ history['原因'] || history['说明'] || '—' }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <div v-if="showCreate" class="modal-mask" @click.self="showCreate = false">
      <form class="modal-card create-modal" @submit.prevent="submitCreate">
        <header class="modal-head">
          <h3>新建巡检计划</h3>
          <button class="btn ghost" type="button" @click="showCreate = false">关闭</button>
        </header>
        <div class="form-grid">
          <label>
            <span>巡检计划编号 *</span>
            <input v-model="createForm['巡检计划编号']" placeholder="如 INSP-20260929-003" />
          </label>
          <label>
            <span>巡检日期 *</span>
            <input v-model="createForm['巡检日期']" type="date" />
          </label>
          <label>
            <span>所属车站 *</span>
            <input v-model="createForm['所属车站']" placeholder="请输入车站或车辆段" />
          </label>
          <label>
            <span>作业班组</span>
            <input v-model="createForm['作业班组']" placeholder="请输入作业班组" />
          </label>
        </div>

        <div class="item-editor-head">
          <h4>巡检清单 *</h4>
          <button class="btn" type="button" @click="addCreateItem">新增巡检项</button>
        </div>
        <p class="form-hint">同一份计划中的巡检项名称不能重复；缺少任一项时整单不落库。</p>
        <div v-for="(item, index) in createForm['巡检项']" :key="index" class="item-editor-row">
          <strong>第 {{ index + 1 }} 项</strong>
          <input v-model="item['巡检项']" placeholder="巡检项名称 *" />
          <input v-model="item['设备编号']" placeholder="设备编号 *" />
          <input v-model="item['巡检内容']" placeholder="巡检内容 *" />
          <input v-model="item['巡检标准']" placeholder="巡检标准" />
          <button class="btn ghost danger" type="button" @click="removeCreateItem(index)">删除</button>
        </div>

        <footer class="modal-foot">
          <span v-if="createError" class="error-text">{{ createError }}</span>
          <button class="btn primary" type="submit" :disabled="saving">{{ saving ? '提交中...' : '保存计划' }}</button>
        </footer>
      </form>
    </div>

    <div v-if="executeTarget" class="modal-mask" @click.self="executeTarget = null">
      <form class="modal-card" @submit.prevent="submitExecute">
        <header class="modal-head">
          <h3>登记巡检记录：{{ executeTarget['巡检项'] }}</h3>
          <button class="btn ghost" type="button" @click="executeTarget = null">关闭</button>
        </header>
        <div class="form-stack">
          <label>
            <span>巡检清单结论</span>
            <input :value="executeForm['清单结论']" disabled />
          </label>
          <label>
            <span>巡检记录明细结论</span>
            <input :value="executeForm['记录结论']" disabled />
          </label>
          <label v-if="executeForm['清单结论'] === '异常'">
            <span>现场问题描述 *</span>
            <textarea v-model="executeForm['问题描述']" rows="3" placeholder="描述设备异常、位置和现象"></textarea>
          </label>
          <label>
            <span>执行备注</span>
            <textarea v-model="executeForm['执行备注']" rows="3" placeholder="可填写测量值、处置情况等"></textarea>
          </label>
        </div>
        <footer class="modal-foot">
          <span v-if="executeError" class="error-text">{{ executeError }}</span>
          <button class="btn primary" type="submit">保存执行记录</button>
        </footer>
      </form>
    </div>

    <div v-if="issueTarget" class="modal-mask" @click.self="issueTarget = null">
      <form class="modal-card" @submit.prevent="submitIssue">
        <header class="modal-head">
          <h3>挂现场问题：{{ issueTarget['巡检项'] }}</h3>
          <button class="btn ghost" type="button" @click="issueTarget = null">关闭</button>
        </header>
        <div class="form-stack">
          <label>
            <span>问题描述 *</span>
            <textarea v-model="issueForm['问题描述']" rows="4" placeholder="问题必须挂到具体巡检项上"></textarea>
          </label>
          <label>
            <span>问题等级</span>
            <select v-model="issueForm['问题等级']">
              <option>一般</option>
              <option>重要</option>
              <option>紧急</option>
            </select>
          </label>
        </div>
        <footer class="modal-foot">
          <span v-if="issueError" class="error-text">{{ issueError }}</span>
          <button class="btn primary" type="submit">保存问题</button>
        </footer>
      </form>
    </div>

    <div v-if="reviewTarget" class="modal-mask" @click.self="reviewTarget = null">
      <form class="modal-card" @submit.prevent="submitReview">
        <header class="modal-head">
          <h3>复核巡检计划：{{ reviewTarget['巡检计划编号'] }}</h3>
          <button class="btn ghost" type="button" @click="reviewTarget = null">关闭</button>
        </header>
        <div class="form-stack">
          <label>
            <span>复核结论 *</span>
            <select v-model="reviewForm['复核结论']">
              <option value="通过">通过并归档</option>
              <option value="驳回">不通过，退回执行中</option>
            </select>
          </label>
          <label v-if="reviewForm['复核结论'] === '驳回'">
            <span>退回原因 *</span>
            <textarea v-model="reviewForm['原因']" rows="4" placeholder="请写清需要现场补查或整改的内容"></textarea>
          </label>
        </div>
        <footer class="modal-foot">
          <span v-if="reviewError" class="error-text">{{ reviewError }}</span>
          <button class="btn primary" type="submit">提交复核</button>
        </footer>
      </form>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'
import { useSessionStore } from '@/stores/session'

type Issue = {
  问题编号: string
  问题描述: string
  问题等级: string
  登记人: string
  登记时间: string
}

type ChecklistItem = {
  id: number
  巡检项: string
  设备编号: string
  巡检内容: string
  巡检标准?: string
  清单结论: string
}

type RecordItem = {
  巡检项ID: number
  巡检项: string
  记录结论: string
  执行人?: string | null
  执行时间?: string | null
  执行备注?: string | null
  问题列表: Issue[]
}

type HistoryItem = {
  时间: string
  动作: string
  操作人: string
  原状态?: string | null
  新状态?: string | null
  原因?: string | null
  说明?: string | null
}

type Plan = {
  id: number
  status: string
  archived: boolean
  abnormal: boolean
  巡检计划编号: string
  巡检日期: string
  所属车站: string
  作业班组?: string
  巡检清单: ChecklistItem[]
  巡检记录明细: RecordItem[]
  下发人?: string | null
  最近执行人?: string | null
  复核人?: string | null
  驳回原因?: string | null
  操作轨迹: HistoryItem[]
}

const ENDPOINT = '/api/inspection'
const statuses = ['待下发', '执行中', '已复核']
const session = useSessionStore()

const rows = ref<Plan[]>([])
const total = ref(0)
const errorMessage = ref('')
const keyword = ref('')
const statusFilter = ref('')
const selectedPlan = ref<Plan | null>(null)

const showCreate = ref(false)
const saving = ref(false)
const createError = ref('')
const createForm = ref({
  巡检计划编号: '',
  巡检日期: '',
  所属车站: '',
  作业班组: '',
  巡检项: [
    { 巡检项: '', 设备编号: '', 巡检内容: '', 巡检标准: '' },
    { 巡检项: '', 设备编号: '', 巡检内容: '', 巡检标准: '' },
  ],
})

const executeTarget = ref<ChecklistItem | null>(null)
const executeError = ref('')
const executeForm = ref({ 清单结论: '正常', 记录结论: '正常', 问题描述: '', 执行备注: '' })

const issueTarget = ref<ChecklistItem | null>(null)
const issueError = ref('')
const issueForm = ref({ 问题描述: '', 问题等级: '一般' })

const reviewTarget = ref<Plan | null>(null)
const reviewError = ref('')
const reviewForm = ref({ 复核结论: '通过', 原因: '' })

const stats = computed(() => {
  const allPlans = computedPlans.value
  return [
    { label: '待下发', value: allPlans.filter((item) => item.status === '待下发').length },
    { label: '执行中', value: allPlans.filter((item) => item.status === '执行中').length },
    { label: '已复核 / 已归档', value: allPlans.filter((item) => item.status === '已复核').length },
    { label: '挂起问题', value: allPlans.reduce((sum, item) => sum + issueCount(item), 0) },
  ]
})

const computedPlans = computed(() => rows.value)

function progressText(plan: Plan): string {
  const totalItems = plan['巡检清单']?.length ?? 0
  const doneItems = (plan['巡检记录明细'] ?? []).filter((item) => item['记录结论'] !== '待巡检').length
  return `${doneItems}/${totalItems}`
}

function issueCount(plan: Plan): number {
  return (plan['巡检记录明细'] ?? []).reduce((sum, item) => sum + (item['问题列表']?.length ?? 0), 0)
}

function recordOf(itemId: number): RecordItem | undefined {
  return selectedPlan.value?.['巡检记录明细']?.find((item) => item['巡检项ID'] === itemId)
}

function resetFilters() {
  keyword.value = ''
  statusFilter.value = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  createError.value = ''
  createForm.value = {
    巡检计划编号: '',
    巡检日期: '',
    所属车站: '',
    作业班组: '',
    巡检项: [{ 巡检项: '', 设备编号: '', 巡检内容: '', 巡检标准: '' }],
  }
  showCreate.value = true
}

function addCreateItem() {
  createForm.value['巡检项'].push({ 巡检项: '', 设备编号: '', 巡检内容: '', 巡检标准: '' })
}

function removeCreateItem(index: number) {
  createForm.value['巡检项'].splice(index, 1)
}

function openExecute(item: ChecklistItem, conclusion: string) {
  executeTarget.value = item
  executeError.value = ''
  executeForm.value = { 清单结论: conclusion, 记录结论: conclusion, 问题描述: '', 执行备注: '' }
}

function openIssue(item: ChecklistItem) {
  issueTarget.value = item
  issueError.value = ''
  issueForm.value = { 问题描述: '', 问题等级: '一般' }
}

function openReview(plan: Plan) {
  reviewTarget.value = plan
  reviewError.value = ''
  reviewForm.value = { 复核结论: '通过', 原因: '' }
}

async function readActionMessage(response: Response): Promise<string> {
  const payload = (await response.json()) as { message?: string }
  return payload.message || `接口返回 ${response.status}`
}

async function postAction(path: string, body: Record<string, unknown>): Promise<boolean> {
  errorMessage.value = ''
  const response = await request(path, {
    method: 'POST',
    body: JSON.stringify({ values: body }),
  })
  if (!response.ok) {
    errorMessage.value = await readActionMessage(response)
    return false
  }
  const payload = (await response.json()) as { ok?: boolean; message?: string }
  if (payload.ok === false) {
    errorMessage.value = payload.message || '操作未生效'
    return false
  }
  errorMessage.value = payload.message || ''
  return true
}

async function dispatch(plan: Plan) {
  const ok = await postAction(`${ENDPOINT}/${plan.id}/dispatch`, { 操作人: session.operator })
  if (ok) await refreshAfterMutation(plan.id)
}

async function submitCreate() {
  saving.value = true
  createError.value = ''
  try {
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({ values: { ...createForm.value, 操作人: session.operator } }),
    })
    const payload = (await response.json()) as { ok?: boolean; message?: string; entry?: Plan }
    if (!response.ok || payload.ok === false) {
      createError.value = payload.message || '巡检计划未保存'
      return
    }
    showCreate.value = false
    await reload()
    if (payload.entry?.id) await selectPlan(payload.entry.id)
  } catch (error) {
    createError.value = error instanceof Error ? error.message : '巡检计划保存失败'
  } finally {
    saving.value = false
  }
}

async function submitExecute() {
  if (!selectedPlan.value || !executeTarget.value) return
  const ok = await postAction(
    `${ENDPOINT}/${selectedPlan.value.id}/items/${executeTarget.value.id}/execute`,
    { ...executeForm.value, 操作人: session.operator },
  )
  if (ok) {
    executeTarget.value = null
    await refreshAfterMutation(selectedPlan.value.id)
  } else {
    executeError.value = errorMessage.value
  }
}

async function submitIssue() {
  if (!selectedPlan.value || !issueTarget.value) return
  const ok = await postAction(
    `${ENDPOINT}/${selectedPlan.value.id}/items/${issueTarget.value.id}/issues`,
    { ...issueForm.value, 操作人: session.operator },
  )
  if (ok) {
    issueTarget.value = null
    await refreshAfterMutation(selectedPlan.value.id)
  } else {
    issueError.value = errorMessage.value
  }
}

async function submitReview() {
  if (!reviewTarget.value) return
  const ok = await postAction(`${ENDPOINT}/${reviewTarget.value.id}/review`, {
    ...reviewForm.value,
    操作人: session.operator,
  })
  if (ok) {
    const planId = reviewTarget.value.id
    reviewTarget.value = null
    await refreshAfterMutation(planId)
  } else {
    reviewError.value = errorMessage.value
  }
}

async function refreshAfterMutation(planId: number) {
  await reload(false)
  await selectPlan(planId, false)
}

async function reload(clearError: boolean | Event = true) {
  if (clearError !== false) errorMessage.value = ''
  const params = new URLSearchParams()
  if (keyword.value.trim()) params.set('keyword', keyword.value.trim())
  if (statusFilter.value) params.set('status', statusFilter.value)
  params.set('size', '200')
  try {
    const response = await request(`${ENDPOINT}?${params.toString()}`)
    if (!response.ok) throw new Error('巡检计划列表读取失败')
    const payload = (await response.json()) as { items?: Plan[]; total?: number }
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '巡检计划列表读取失败'
  }
}

async function selectPlan(planId: number, clearError = true) {
  if (clearError) errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${planId}`)
    if (!response.ok) throw new Error('巡检计划明细读取失败')
    selectedPlan.value = (await response.json()) as Plan
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '巡检计划明细读取失败'
  }
}

onMounted(() => {
  void reload()
})
</script>
