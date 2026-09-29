<template>
  <section class="page" data-module="inspection">
    <!-- ===================== 计划列表 ===================== -->
    <template v-if="!currentId">
      <header class="page-head">
        <div>
          <h2>信号设备巡检</h2>
          <p class="page-desc">
            巡检计划状态按 待下发 → 执行中 → 已复核 流转；现场问题挂到具体巡检项，复核不通过退回执行中并写明原因，交班后刷新仍可查到每一步的执行人。
          </p>
        </div>
        <div class="page-actions">
          <button class="btn primary" type="button" @click="openCreate">登记巡检计划</button>
          <button class="btn" type="button" @click="exportRows">导出巡检计划清单</button>
        </div>
      </header>

      <div class="stat-row">
        <article v-for="item in stats" :key="item.label" class="stat-card">
          <span class="stat-label">{{ item.label }}</span>
          <strong class="stat-value">{{ item.value }}</strong>
        </article>
      </div>

      <form class="filter-bar" @submit.prevent="reload">
        <label class="filter-item">
          <span>关键字</span>
          <input v-model="keyword" placeholder="计划编号 / 巡检名称 / 设备范围" />
        </label>
        <label class="filter-item">
          <span>计划状态</span>
          <select v-model="statusFilter">
            <option value="">全部</option>
            <option v-for="s in ['待下发', '执行中', '已复核']" :key="s" :value="s">{{ s }}</option>
          </select>
        </label>
        <button class="btn" type="submit">查询</button>
        <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
        <button class="btn ghost" type="button" @click="reload">刷新</button>
      </form>

      <table class="data-table">
        <thead>
          <tr>
            <th v-for="column in columns" :key="column">{{ column }}</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="String(row.id)" class="clickable" @click="openDetail(Number(row.id))">
            <td v-for="column in columns" :key="column">
              <span v-if="column === '计划状态'" class="badge" :class="statusClass(String(row['计划状态']))">
                {{ row[column] ?? '—' }}
              </span>
              <span v-else-if="column === '未处理问题'">
                <span v-if="Number(row[column]) > 0" class="issue-count">{{ row[column] }} 条待处理</span>
                <span v-else>—</span>
              </span>
              <span v-else>{{ display(row[column]) }}</span>
            </td>
            <td class="row-actions" @click.stop>
              <button class="link" type="button" @click="openDetail(Number(row.id))">查看 / 执行</button>
            </td>
          </tr>
          <tr v-if="!rows.length">
            <td :colspan="columns.length + 1" class="empty-state">暂无巡检计划，可先登记一份</td>
          </tr>
        </tbody>
      </table>

      <footer class="page-foot">
        <span>共 {{ total }} 份巡检计划</span>
        <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
        <span v-else-if="okMessage" class="ok-text">{{ okMessage }}</span>
      </footer>
    </template>

    <!-- ===================== 计划明细 ===================== -->
    <template v-else-if="detail">
      <header class="page-head detail-head">
        <div>
          <button class="btn ghost back-btn" type="button" @click="backToList">← 返回列表</button>
          <h2>{{ detail.巡检名称 }}</h2>
          <p class="page-desc">
            计划编号 {{ detail.计划编号 }} · {{ detail.巡检日期 }} · {{ detail.设备范围 }} · {{ detail.班组 }}
          </p>
        </div>
        <div class="detail-badges">
          <span class="badge" :class="statusClass(detail.计划状态)">{{ detail.计划状态 }}</span>
          <span class="badge info">进度 {{ detail.进度 }}</span>
          <span v-if="Number(detail.未处理问题) > 0" class="badge danger">{{ detail.未处理问题 }} 条问题待处理</span>
          <span v-if="detail.status === '已复核'" class="badge archived">已归档（只读）</span>
        </div>
      </header>

      <div v-if="detail.status === '已复核'" class="banner archived-banner">
        该巡检计划已复核归档（复核人：{{ detail.复核人 }} · {{ detail.复核时间 }}），任何内容都不允许再改动。
      </div>
      <div v-if="lastReject" class="banner reject-banner">
        <strong>最近一次复核被退回（{{ lastReject.复核人 }} · {{ lastReject.复核时间 }}）：</strong>
        {{ lastReject.退回原因 }}
      </div>
      <div v-if="detail.待复核" class="banner pending-banner">
        计划已提交复核，等待复核结论；复核期间巡检记录与现场问题暂不可改。
      </div>

      <div v-if="errorMessage" class="banner error-banner">{{ errorMessage }}</div>
      <div v-if="okMessage" class="banner ok-banner">{{ okMessage }}</div>

      <!-- 当班操作人：交班后接手人改成自己的名字，记录里就能区分每一步是谁干的 -->
      <div class="operator-bar">
        <label>
          当前操作人
          <input v-model="operator" placeholder="如：李接手" @change="persistOperator" />
        </label>
        <span class="hint">交班接手后先改成本人姓名，巡检记录与流转记录都会按此留名</span>
      </div>

      <!-- 动作按钮 -->
      <div class="action-bar">
        <template v-if="detail.status === '待下发'">
          <button class="btn primary" type="button" @click="dispatch">下发计划</button>
          <button class="btn" type="button" @click="showAddItem = !showAddItem">补充巡检项</button>
        </template>
        <template v-else-if="detail.status === '执行中'">
          <button v-if="!detail.待复核" class="btn primary" type="button" @click="submitReview">提交复核</button>
          <button v-if="!detail.待复核" class="btn" type="button" @click="showAddItem = !showAddItem">补充巡检项</button>
          <button v-if="detail.待复核" class="btn primary" type="button" @click="approve">复核通过</button>
          <button v-if="detail.待复核" class="btn danger-btn" type="button" @click="showReject = !showReject">复核退回</button>
        </template>
        <button class="btn ghost" type="button" @click="loadDetail(currentId)">刷新明细</button>
      </div>

      <!-- 复核退回原因 -->
      <form v-if="showReject" class="inline-form" @submit.prevent="reject">
        <label class="grow">
          <span>退回原因（必填，会写进巡检流转记录，执行人刷新即可看到）</span>
          <textarea v-model="rejectReason" rows="2" placeholder="如：Ⅱ路切换试验未记录切换时间，请补测后重新提交"></textarea>
        </label>
        <button class="btn danger-btn" type="submit">确认退回执行中</button>
      </form>

      <!-- 一致性对账 -->
      <section class="panel">
        <h3>清单与记录对账 <span class="hint">巡检清单与巡检记录明细的结论必须对得上才允许提交复核</span></h3>
        <ul v-if="consistencyErrors.length" class="error-list">
          <li v-for="(err, i) in consistencyErrors" :key="i" class="error-text">· {{ err }}</li>
        </ul>
        <p v-else class="ok-text">清单与巡检记录明细一致，可以提交复核。</p>
      </section>

      <!-- 补充巡检项 -->
      <form v-if="showAddItem && detail.status !== '已复核'" class="inline-form" @submit.prevent="addItem">
        <label>
          <span>巡检项编号（可空）</span>
          <input v-model="newItem.巡检项编号" placeholder="如 X04" />
        </label>
        <label class="grow">
          <span>巡检项名称（必填）</span>
          <input v-model="newItem.巡检项名称" placeholder="如 信号机灯端电压测量" />
        </label>
        <label>
          <span>设备编号</span>
          <input v-model="newItem.设备编号" placeholder="如 S-004" />
        </label>
        <button class="btn primary" type="submit">加入清单</button>
        <span class="hint">同一份计划里重复登记同一巡检项会被当场拦下</span>
      </form>

      <!-- 巡检清单 + 巡检记录明细 + 现场问题 -->
      <section class="panel">
        <h3>巡检清单与巡检记录明细（{{ detail.items.length }} 项）</h3>
        <table class="data-table item-table">
          <thead>
            <tr>
              <th>巡检项编号</th>
              <th>巡检项名称 / 检查内容</th>
              <th style="width: 110px">结论</th>
              <th style="width: 150px">执行人 / 时间</th>
              <th style="width: 200px">现场问题</th>
              <th v-if="canEdit" style="width: 230px">巡检登记</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="item in detail.items" :key="item.id">
              <tr>
                <td>{{ item.巡检项编号 }}</td>
                <td>
                  <strong>{{ item.巡检项名称 }}</strong>
                  <div v-if="item.设备编号" class="hint">设备：{{ item.设备编号 }}</div>
                  <div v-if="item.检查内容" class="hint">{{ item.检查内容 }}</div>
                </td>
                <td>
                  <span v-if="item.结论" class="badge" :class="item.结论 === '异常' ? 'danger' : 'ok'">
                    {{ item.结论 }}
                  </span>
                  <span v-else class="hint">未检</span>
                </td>
                <td>
                  <template v-if="item.执行人">
                    <div>{{ item.执行人 }}</div>
                    <div class="hint">{{ item.执行时间 }}</div>
                  </template>
                  <span v-else class="hint">—</span>
                </td>
                <td>
                  <button
                    class="link"
                    type="button"
                    @click="toggleIssues(item.id)"
                  >{{ item.问题.length ? `现场问题 ${item.问题.length} 条` : '无 / 登记问题' }}</button>
                </td>
                <td v-if="canEdit">
                  <select v-model="drafts[item.id].结论">
                    <option value="">选择结论</option>
                    <option value="正常">正常</option>
                    <option value="异常">异常</option>
                  </select>
                  <button
                    class="btn mini primary"
                    type="button"
                    @click="saveRecord(item.id, drafts[item.id].结论)"
                  >保存记录</button>
                </td>
              </tr>
              <tr v-if="openIssues[item.id]" class="issue-row">
                <td colspan="6">
                  <div v-if="!item.问题.length" class="hint">该巡检项暂无现场问题。</div>
                  <ul v-else class="issue-list">
                    <li v-for="issue in item.问题" :key="issue.id">
                      <div class="issue-head">
                        <span class="badge" :class="issue.严重程度 === '严重' ? 'danger' : 'warn'">{{ issue.严重程度 }}</span>
                        <span class="badge" :class="issue.处理状态 === '已处理' ? 'ok' : 'danger'">{{ issue.处理状态 }}</span>
                        <strong>{{ issue.问题描述 }}</strong>
                      </div>
                      <div class="hint">
                        登记：{{ issue.登记人 }} · {{ issue.登记时间 }}
                        <template v-if="issue.处理人">
                          ｜处理：{{ issue.处理人 }} · {{ issue.处理时间 }} — {{ issue.处理说明 }}
                        </template>
                      </div>
                      <form
                        v-if="canEdit && issue.处理状态 === '未处理'"
                        class="issue-resolve"
                        @submit.prevent="resolveIssue(item.id, issue.id, drafts[item.id].resolveNote)"
                      >
                        <input v-model="drafts[item.id].resolveNote" placeholder="处理说明（必填）" />
                        <button class="btn mini" type="submit">登记处理结果</button>
                      </form>
                    </li>
                  </ul>
                  <form
                    v-if="canEdit"
                    class="issue-add"
                    @submit.prevent="addIssue(item.id, drafts[item.id].issueText, drafts[item.id].severity)"
                  >
                    <input v-model="drafts[item.id].issueText" placeholder="现场发现的问题描述（必填，挂在本巡检项上）" />
                    <select v-model="drafts[item.id].severity">
                      <option value="一般">一般</option>
                      <option value="严重">严重</option>
                    </select>
                    <button class="btn mini primary" type="submit">挂问题</button>
                  </form>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </section>

      <!-- 流转记录：交班后接手的人在这里看到上一步是谁执行的 -->
      <section class="panel">
        <h3>流转记录（交班留痕）</h3>
        <ul class="log-list">
          <li v-for="(log, i) in [...detail.logs].reverse()" :key="i" class="log-item">
            <span class="log-time">{{ log.time }}</span>
            <span class="badge log-action">{{ log.action }}</span>
            <span class="log-operator">{{ log.operator }}</span>
            <span class="log-detail">{{ log.detail }}</span>
          </li>
        </ul>
      </section>
    </template>

    <!-- ===================== 新建计划弹窗 ===================== -->
    <div v-if="showCreate" class="modal-mask" @click.self="showCreate = false">
      <div class="modal">
        <h3>登记巡检计划</h3>
        <div v-if="createError" class="banner error-banner">{{ createError }}</div>
        <div class="form-grid">
          <label><span>计划编号 *</span><input v-model="createForm.计划编号" placeholder="如 XJ-2026-1006" /></label>
          <label><span>巡检名称 *</span><input v-model="createForm.巡检名称" placeholder="如 10月信号设备例行巡检" /></label>
          <label><span>巡检日期 *</span><input v-model="createForm.巡检日期" placeholder="2026-10-06" /></label>
          <label><span>班组 *</span><input v-model="createForm.班组" placeholder="如 信号一工班" /></label>
          <label class="full"><span>设备范围 *</span><input v-model="createForm.设备范围" placeholder="如 甲站Ⅰ场信号机、转辙机" /></label>
        </div>
        <div class="modal-items">
          <div class="modal-items-head">
            <span>巡检清单 *（至少一个巡检项；同一计划内编号/名称重复会被拦下）</span>
            <button class="btn mini" type="button" @click="addCreateRow">加一行</button>
          </div>
          <div v-for="(row, idx) in createForm.items" :key="idx" class="create-item-row">
            <input v-model="row.巡检项编号" placeholder="编号（可空）" class="w-code" />
            <input v-model="row.巡检项名称" placeholder="巡检项名称（必填）" class="grow" />
            <input v-model="row.设备编号" placeholder="设备编号（可空）" class="w-code" />
            <button class="btn mini ghost" type="button" @click="createForm.items.splice(idx, 1)">删除</button>
          </div>
        </div>
        <div class="modal-foot">
          <button class="btn ghost" type="button" @click="showCreate = false">取消</button>
          <button class="btn primary" type="button" @click="submitCreate">登记（待下发）</button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'

const ENDPOINT = '/api/inspection'
const columns = ['计划编号', '巡检名称', '巡检日期', '设备范围', '班组', '进度', '未处理问题', '计划状态']

type Row = Record<string, unknown>
interface Issue {
  id: number
  问题描述: string
  严重程度: string
  登记人: string
  登记时间: string
  处理状态: string
  处理人: string | null
  处理时间: string | null
  处理说明: string | null
}
interface Item {
  id: number
  巡检项编号: string
  巡检项名称: string
  检查内容: string
  设备编号: string
  结论: '正常' | '异常' | null
  执行人: string | null
  执行时间: string | null
  问题: Issue[]
}
interface LogEntry {
  action: string
  operator: string
  time: string
  detail: string
}
interface Review {
  round: number
  结论: '通过' | '退回' | null
  提交人: string
  提交时间: string
  复核人: string | null
  复核时间: string | null
  退回原因: string | null
}
interface Plan {
  id: number
  status: '待下发' | '执行中' | '已复核'
  计划状态: string
  待复核: boolean
  计划编号: string
  巡检名称: string
  巡检日期: string
  设备范围: string
  班组: string
  创建人: string
  创建时间: string
  下发人: string | null
  下发时间: string | null
  复核人: string | null
  复核时间: string
  进度: string
  未处理问题: number
  items: Item[]
  logs: LogEntry[]
  reviews?: Review[]
}
interface ActionResponse {
  ok: boolean
  message: string
  entry: Plan | null
}
interface ConsistencyReport {
  ok: boolean
  errors: string[]
}

const rows = ref<Row[]>([])
const total = ref(0)
const keyword = ref('')
const statusFilter = ref('')
const errorMessage = ref('')
const okMessage = ref('')

const currentId = ref<number | null>(null)
const detail = ref<Plan | null>(null)
const consistencyErrors = ref<string[]>([])
const operator = ref(localStorage.getItem('inspection.operator') || '值班管理员')
const showAddItem = ref(false)
const showReject = ref(false)
const rejectReason = ref('')
const newItem = reactive({ 巡检项编号: '', 巡检项名称: '', 设备编号: '' })

const drafts = reactive<Record<number, { 结论: string; issueText: string; severity: string; resolveNote: string }>>({})

const showCreate = ref(false)
const createError = ref('')
const createForm = reactive({
  计划编号: '',
  巡检名称: '',
  巡检日期: '',
  设备范围: '',
  班组: '',
  items: [{ 巡检项编号: '', 巡检项名称: '', 设备编号: '' }],
})

const openIssues = reactive<Record<number, boolean>>({})

const stats = computed(() => [
  { label: '待下发', value: rows.value.filter((r) => r['计划状态'] === '待下发').length },
  { label: '执行中（含待复核）', value: rows.value.filter((r) => r['计划状态'] === '执行中' || r['计划状态'] === '待复核').length },
  { label: '已复核归档', value: rows.value.filter((r) => r['计划状态'] === '已复核').length },
  { label: '未处理现场问题', value: rows.value.reduce((sum, r) => sum + Number(r['未处理问题'] || 0), 0) },
])

const canEdit = computed(
  () => detail.value?.status === '执行中' && !detail.value.待复核,
)

const lastReject = computed<Review | null>(() => {
  const reviews = detail.value?.reviews ?? []
  return [...reviews].reverse().find((r) => r.结论 === '退回') ?? null
})

function display(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—'
  return String(value)
}

function statusClass(status: string): string {
  if (status === '已复核') return 'archived'
  if (status === '执行中') return 'warn'
  if (status === '待复核') return 'info'
  return ''
}

function persistOperator() {
  localStorage.setItem('inspection.operator', operator.value)
}

function flash(message: string, ok = false) {
  errorMessage.value = ok ? '' : message
  okMessage.value = ok ? message : ''
  if (ok) window.setTimeout(() => (okMessage.value = ''), 4000)
}

async function post(path: string, values: Record<string, unknown>): Promise<ActionResponse> {
  const response = await request(`${ENDPOINT}${path}`, {
    method: 'POST',
    body: JSON.stringify({ values: { operator: operator.value, ...values } }),
  })
  return (await response.json()) as ActionResponse
}

// ---------- 列表 ----------
async function reload() {
  errorMessage.value = ''
  const params = new URLSearchParams()
  if (keyword.value) params.set('keyword', keyword.value)
  if (statusFilter.value) params.set('status', statusFilter.value)
  try {
    const response = await request(`${ENDPOINT}?${params.toString()}`)
    if (!response.ok) throw new Error('巡检计划列表读取失败')
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? 0
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '巡检计划列表读取失败'
  }
}

function resetFilters() {
  keyword.value = ''
  statusFilter.value = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

// ---------- 新建 ----------
function openCreate() {
  createError.value = ''
  Object.assign(createForm, {
    计划编号: '', 巡检名称: '', 巡检日期: '', 设备范围: '', 班组: '',
  })
  createForm.items = [{ 巡检项编号: '', 巡检项名称: '', 设备编号: '' }]
  showCreate.value = true
}

function addCreateRow() {
  createForm.items.push({ 巡检项编号: '', 巡检项名称: '', 设备编号: '' })
}

async function submitCreate() {
  createError.value = ''
  const result = await post('', {
    计划编号: createForm.计划编号,
    巡检名称: createForm.巡检名称,
    巡检日期: createForm.巡检日期,
    设备范围: createForm.设备范围,
    班组: createForm.班组,
    items: createForm.items,
  })
  if (!result.ok) {
    createError.value = result.message
    return
  }
  showCreate.value = false
  flash(result.message || '巡检计划已登记', true)
  await reload()
  if (result.entry) await openDetail(result.entry.id)
}

// ---------- 明细 ----------
function ensureDrafts(item: Item) {
  if (!drafts[item.id]) {
    drafts[item.id] = { 结论: item.结论 ?? '', issueText: '', severity: '一般', resolveNote: '' }
  }
}

async function openDetail(id: number) {
  currentId.value = id
  errorMessage.value = ''
  okMessage.value = ''
  showAddItem.value = false
  showReject.value = false
  rejectReason.value = ''
  await loadDetail(id)
}

async function loadDetail(id: number) {
  try {
    const response = await request(`${ENDPOINT}/${id}`)
    const payload = await response.json()
    if (!response.ok || payload.ok === false) {
      throw new Error(payload.message || '巡检计划读取失败')
    }
    detail.value = payload as Plan
    detail.value.items.forEach(ensureDrafts)
    await loadConsistency(id)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '巡检计划读取失败'
    detail.value = null
  }
}

async function loadConsistency(id: number) {
  try {
    const response = await request(`${ENDPOINT}/${id}/consistency`)
    const payload = (await response.json()) as ConsistencyReport
    consistencyErrors.value = payload.errors ?? []
  } catch {
    consistencyErrors.value = []
  }
}

function backToList() {
  currentId.value = null
  detail.value = null
  void reload()
}

function toggleIssues(itemId: number) {
  openIssues[itemId] = !openIssues[itemId]
}

// ---------- 明细内操作 ----------
async function handleAction(values: Record<string, unknown>, successMsg?: string) {
  if (!detail.value) return
  const result = await post(`/${detail.value.id}/actions`, values)
  if (!result.ok) {
    flash(result.message)
    return
  }
  if (result.entry) detail.value = result.entry
  result.entry?.items.forEach(ensureDrafts)
  flash(successMsg || result.message, true)
  await loadConsistency(detail.value.id)
}

function dispatch() {
  void handleAction({ action: '下发' })
}

async function submitReview() {
  await handleAction({ action: '提交复核' })
}

async function approve() {
  await handleAction({ action: '复核通过' })
  showReject.value = false
}

async function reject() {
  if (!rejectReason.value.trim()) {
    flash('复核退回必须写清退回原因')
    return
  }
  await handleAction({ action: '复核退回', 退回原因: rejectReason.value.trim() })
  showReject.value = false
  rejectReason.value = ''
}

async function addItem() {
  if (!detail.value) return
  const result = await post(`/${detail.value.id}/items`, { ...newItem })
  if (!result.ok || !result.entry) {
    flash(result.message)
    return
  }
  detail.value = result.entry
  result.entry.items.forEach(ensureDrafts)
  newItem.巡检项编号 = ''
  newItem.巡检项名称 = ''
  newItem.设备编号 = ''
  showAddItem.value = false
  flash('巡检项已加入清单', true)
  await loadConsistency(result.entry.id)
}

async function saveRecord(itemId: number, conclusion: string) {
  if (!detail.value) return
  if (!conclusion) {
    flash('请先选择巡检结论（正常 / 异常）')
    return
  }
  const result = await post(`/${detail.value.id}/items/${itemId}/record`, { 结论: conclusion })
  if (!result.ok || !result.entry) {
    flash(result.message)
    return
  }
  detail.value = result.entry
  result.entry.items.forEach(ensureDrafts)
  flash('巡检记录已登记', true)
  await loadConsistency(result.entry.id)
}

async function addIssue(itemId: number, text: string, severity: string) {
  if (!detail.value) return
  if (!text.trim()) {
    flash('请填写现场问题描述')
    return
  }
  const result = await post(`/${detail.value.id}/items/${itemId}/issues`, {
    问题描述: text.trim(),
    严重程度: severity,
  })
  if (!result.ok || !result.entry) {
    flash(result.message)
    return
  }
  detail.value = result.entry
  result.entry.items.forEach(ensureDrafts)
  drafts[itemId].issueText = ''
  openIssues[itemId] = true
  flash('现场问题已挂到该巡检项', true)
  await loadConsistency(result.entry.id)
}

async function resolveIssue(itemId: number, issueId: number, note: string) {
  if (!detail.value) return
  if (!note.trim()) {
    flash('请填写问题处理说明')
    return
  }
  const result = await post(`/${detail.value.id}/items/${itemId}/issues/${issueId}/resolve`, {
    处理说明: note.trim(),
  })
  if (!result.ok || !result.entry) {
    flash(result.message)
    return
  }
  detail.value = result.entry
  result.entry.items.forEach(ensureDrafts)
  drafts[itemId].resolveNote = ''
  flash('问题处理结果已登记', true)
  await loadConsistency(result.entry.id)
}

onMounted(reload)
</script>

<style scoped>
.page-actions { display: flex; gap: 8px; }
.clickable { cursor: pointer; }
.clickable:hover { background: #f1f6ff; }
.issue-count { color: #b42318; font-weight: 600; }
.ok-text { color: #067647; }
.hint { color: var(--muted); font-size: 12px; font-weight: 400; }
.grow { flex: 1; }

.detail-head { gap: 16px; }
.back-btn { margin-bottom: 6px; padding: 2px 8px; }
.detail-badges { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }

.badge {
  display: inline-block; padding: 2px 10px; border-radius: 999px;
  font-size: 12px; border: 1px solid var(--border); background: #f1f5f9;
}
.badge.ok { background: #ecfdf3; border-color: #abefc6; color: #067647; }
.badge.danger { background: #fef3f2; border-color: #fda29b; color: #b42318; }
.badge.warn { background: #fffaeb; border-color: #fedf89; color: #b54708; }
.badge.info { background: #eff8ff; border-color: #84caff; color: #175cd3; }
.badge.archived { background: #f2f4f7; border-color: #d0d5dd; color: #475467; }

.banner { border-radius: 6px; padding: 10px 12px; margin-bottom: 10px; font-size: 13px; border: 1px solid; }
.error-banner { background: #fef3f2; border-color: #fda29b; color: #b42318; }
.ok-banner { background: #ecfdf3; border-color: #abefc6; color: #067647; }
.reject-banner { background: #fef3f2; border-color: #fda29b; color: #7a271a; }
.pending-banner { background: #eff8ff; border-color: #84caff; color: #175cd3; }
.archived-banner { background: #f2f4f7; border-color: #d0d5dd; color: #475467; }

.operator-bar {
  display: flex; align-items: center; gap: 12px; background: #fff;
  border: 1px solid var(--border); border-radius: 8px; padding: 10px 12px; margin-bottom: 12px;
}
.operator-bar label { display: flex; align-items: center; gap: 8px; font-size: 13px; }
.operator-bar input { width: 160px; padding: 4px 8px; border: 1px solid var(--border); border-radius: 6px; }

.action-bar { display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
.btn.danger-btn { background: #d92d20; border-color: #d92d20; color: #fff; }
.btn.mini { padding: 3px 10px; font-size: 12px; }

.inline-form {
  display: flex; gap: 10px; align-items: flex-end; flex-wrap: wrap;
  background: #fff; border: 1px solid var(--border); border-radius: 8px; padding: 10px 12px; margin-bottom: 12px;
}
.inline-form label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--muted); }
.inline-form input, .inline-form textarea {
  padding: 5px 8px; border: 1px solid var(--border); border-radius: 6px; font-size: 13px; min-width: 180px;
}

.panel {
  background: #fff; border: 1px solid var(--border); border-radius: 8px;
  padding: 12px; margin-bottom: 12px;
}
.panel h3 { margin: 0 0 10px; font-size: 14px; display: flex; gap: 10px; align-items: baseline; }
.error-list { margin: 0; padding-left: 4px; list-style: none; font-size: 13px; }

.item-table select { padding: 3px 6px; border: 1px solid var(--border); border-radius: 6px; }
.item-table td > * + * { margin-left: 6px; }
.issue-row td { background: #f8fafc; }
.issue-list { list-style: none; margin: 0 0 8px; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.issue-list li { border: 1px solid var(--border); border-radius: 6px; padding: 6px 8px; background: #fff; }
.issue-head { display: flex; gap: 8px; align-items: center; font-size: 13px; }
.issue-resolve, .issue-add { display: flex; gap: 8px; margin-top: 6px; }
.issue-resolve input, .issue-add input {
  flex: 1; padding: 4px 8px; border: 1px solid var(--border); border-radius: 6px;
}
.issue-add select { padding: 4px 6px; border: 1px solid var(--border); border-radius: 6px; }

.log-list { list-style: none; margin: 0; padding: 0; }
.log-item {
  display: flex; gap: 10px; align-items: baseline; padding: 6px 0;
  border-bottom: 1px dashed var(--border); font-size: 13px;
}
.log-time { color: var(--muted); width: 140px; flex-shrink: 0; }
.log-action { flex-shrink: 0; }
.log-operator { font-weight: 600; width: 80px; flex-shrink: 0; }
.log-detail { color: #334155; }

.modal-mask {
  position: fixed; inset: 0; background: rgba(16, 24, 40, 0.45);
  display: flex; align-items: flex-start; justify-content: center; padding-top: 60px; z-index: 100;
}
.modal { background: #fff; border-radius: 10px; width: 760px; max-width: calc(100vw - 40px); padding: 18px 20px; }
.modal h3 { margin: 0 0 12px; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.form-grid label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--muted); }
.form-grid .full { grid-column: 1 / -1; }
.form-grid input { padding: 6px 8px; border: 1px solid var(--border); border-radius: 6px; font-size: 13px; }
.modal-items { margin-top: 12px; }
.modal-items-head { display: flex; justify-content: space-between; align-items: center; font-size: 12px; color: var(--muted); margin-bottom: 6px; }
.create-item-row { display: flex; gap: 8px; margin-bottom: 6px; }
.create-item-row input { padding: 6px 8px; border: 1px solid var(--border); border-radius: 6px; font-size: 13px; }
.create-item-row .w-code { width: 130px; }
.modal-foot { display: flex; justify-content: flex-end; gap: 8px; margin-top: 14px; }
</style>
