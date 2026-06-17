<script setup>
import { ref, onMounted, computed } from 'vue'
import { useWorkflowStore } from '../../stores/workflowStore'

const workflowStore = useWorkflowStore()

const toolboxSearch = ref('')
const activeSection = ref('workflow') // 'workflow' | 'toolbox'
const isLoading = ref(false)
const dragPreviewEl = ref(null)

onMounted(async () => {
  isLoading.value = true
  try {
    await Promise.all([
      workflowStore.loadWorkflows(),
      workflowStore.loadTemplates()
    ])
    // 加载后如果没有选中任何工作流，自动加载翻译模板
    if (!workflowStore.currentWorkflowId) {
      workflowStore.loadTranslationTemplate()
    }
  } finally {
    isLoading.value = false
  }
})

function handleWorkflowClick(workflowId) {
  workflowStore.selectWorkflow(workflowId)
}

function handleNewWorkflow() {
  workflowStore.createNewWorkflow()
}

async function handleDeleteWorkflow(event, workflowId, workflowName) {
  event.stopPropagation()
  const ok = window.confirm(`确定删除工作流「${workflowName || '未命名工作流'}」吗？`)
  if (!ok) return
  try {
    await workflowStore.deleteWorkflow(workflowId)
  } catch (e) {
    window.alert(e?.message || '删除工作流失败')
  }
}

function handleSearch(e) {
  workflowStore.setSearchQuery(e.target.value)
}

function handleAddNode(item) {
  workflowStore.addNode(item)
}

function handleLoadTranslationTemplate() {
  workflowStore.loadTranslationTemplate()
}

function getWorkflowRunState(workflowId) {
  const state = workflowStore.getWorkflowExecutionState(workflowId)
  if (!state) return null
  const hasStarted = state.isExecuting || state.executionId || state.executionLogs?.length || state.executionProgress > 0
  if (!hasStarted) return null
  const lastLog = state.executionLogs?.[state.executionLogs.length - 1]
  const failed = Boolean(lastLog?.type === 'error')
  const progress = Math.max(0, Math.min(100, Number(state.executionProgress) || 0))
  return {
    progress,
    status: failed ? 'failed' : state.isExecuting ? 'running' : progress >= 100 ? 'completed' : 'paused',
    label: failed ? '!' : progress >= 100 && !state.isExecuting ? '✓' : `${progress}%`
  }
}

function progressRingStyle(runState) {
  const value = Math.max(0, Math.min(100, Number(runState?.progress) || 0))
  return { '--workflow-progress': `${value * 3.6}deg` }
}

const workflowIconPalettes = [
  ['#dbeafe', '#1d4ed8'],
  ['#dcfce7', '#047857'],
  ['#fef3c7', '#b45309'],
  ['#ffe4e6', '#be123c'],
  ['#ede9fe', '#6d28d9'],
  ['#cffafe', '#0e7490'],
  ['#e0e7ff', '#4338ca'],
  ['#f0fdfa', '#0f766e'],
  ['#fae8ff', '#a21caf'],
  ['#ffedd5', '#c2410c']
]

function hashText(text) {
  const value = String(text || '')
  let hash = 0
  for (let i = 0; i < value.length; i++) {
    hash = Math.imul(hash, 31) + value.charCodeAt(i)
  }
  return hash >>> 0
}

function workflowIconStyle(wf) {
  const palette = workflowIconPalettes[hashText(`${wf?.id || ''}|${wf?.name || ''}`) % workflowIconPalettes.length]
  return {
    '--workflow-icon-bg': palette[0],
    '--workflow-icon-fg': palette[1]
  }
}

/** 组件库搜索过滤（拖拽仍作用于当前列表项） */
const filteredToolboxSections = computed(() => {
  const q = toolboxSearch.value.trim().toLowerCase()
  if (!q) return workflowStore.toolboxItems
  return workflowStore.toolboxItems
    .map(section => ({
      ...section,
      items: section.items.filter(
        i =>
          i.name.toLowerCase().includes(q) ||
          (i.title && i.title.toLowerCase().includes(q)) ||
          (i.body && i.body.toLowerCase().includes(q))
      )
    }))
    .filter(section => section.items.length > 0)
})

function onToolboxDragStart(e, item) {
  const payload = JSON.stringify({
    schemaKey: item.schemaKey,
    type: item.type,
    icon: item.icon,
    title: item.title,
    body: item.body,
    name: item.name
  })
  try {
    e.dataTransfer.setData('application/x-workflow-node', payload)
  } catch (_) {
    /* 部分环境仅支持 text/plain */
  }
  e.dataTransfer.setData('text/plain', payload)
  e.dataTransfer.effectAllowed = 'copy'
  const preview = document.createElement('div')
  preview.className = 'workflow-drag-preview'
  const icon = document.createElement('span')
  icon.className = 'workflow-drag-preview-icon'
  icon.textContent = item.icon || ''
  const title = document.createElement('span')
  title.className = 'workflow-drag-preview-title'
  title.textContent = item.name || item.title || ''
  preview.appendChild(icon)
  preview.appendChild(title)
  document.body.appendChild(preview)
  dragPreviewEl.value = preview
  try {
    e.dataTransfer.setDragImage(preview, 18, 18)
  } catch (_) {
    /* ignore */
  }
}

function onToolboxDragEnd() {
  if (dragPreviewEl.value?.parentNode) {
    dragPreviewEl.value.parentNode.removeChild(dragPreviewEl.value)
  }
  dragPreviewEl.value = null
}
</script>

<template>
  <aside class="workflow-sidebar">

    <!-- Loading Indicator -->
    <div v-if="isLoading" class="sidebar-loading">
      <div class="loading-dots">
        <span></span><span></span><span></span>
      </div>
    </div>

    <template v-else>
      <!-- Section Switcher -->
      <div class="sidebar-switcher">
        <button
          class="switcher-btn"
          :class="{ active: activeSection === 'workflow' }"
          @click="activeSection = 'workflow'"
        >
          <span>📋</span> 工作流
        </button>
        <button
          class="switcher-btn"
          :class="{ active: activeSection === 'toolbox' }"
          @click="activeSection = 'toolbox'"
        >
          <span>🧩</span> 组件库
        </button>
      </div>

      <!-- ===================== 工作流面板 ===================== -->
      <template v-if="activeSection === 'workflow'">
        <!-- New Workflow -->
        <div class="sidebar-section">
          <button class="new-workflow-btn" @click="handleNewWorkflow">
            <span>+</span>
            <span>新建工作流</span>
          </button>
        </div>

        <!-- Quick Template: Translation Flow -->
        <div class="sidebar-section">
          <div class="template-quick-card" @click="handleLoadTranslationTemplate">
            <div class="template-quick-icon">🌍</div>
            <div class="template-quick-info">
              <div class="template-quick-name">文档翻译流</div>
              <div class="template-quick-desc">PDF → AI翻译 → 输出</div>
            </div>
            <div class="template-quick-badge">预设</div>
          </div>
        </div>

        <!-- Search -->
        <div class="sidebar-section sidebar-search">
          <input
            type="text"
            placeholder="搜索工作流..."
            :value="workflowStore.searchQuery"
            @input="handleSearch"
          />
        </div>

        <!-- Workflow List -->
        <div class="sidebar-scroll">
          <!-- Custom Workflows -->
          <div class="workflow-group" v-if="workflowStore.customWorkflows.length > 0">
            <div class="workflow-group-title">我的工作流</div>
            <div
              v-for="wf in workflowStore.customWorkflows"
              :key="wf.id"
              class="workflow-item"
              :class="{ active: workflowStore.currentWorkflowId === wf.id }"
              @click="handleWorkflowClick(wf.id)"
            >
              <span class="workflow-icon" :style="workflowIconStyle(wf)">{{ wf.icon }}</span>
              <div class="workflow-info">
                <span class="workflow-name">{{ wf.name }}</span>
                <span class="workflow-time">{{ wf.time }}</span>
              </div>
              <div
                v-if="getWorkflowRunState(wf.id)"
                class="workflow-progress-ring"
                :class="'workflow-progress-' + getWorkflowRunState(wf.id).status"
                :style="progressRingStyle(getWorkflowRunState(wf.id))"
                :title="getWorkflowRunState(wf.id).status === 'running' ? `执行中 ${getWorkflowRunState(wf.id).progress}%` : getWorkflowRunState(wf.id).status === 'completed' ? '已完成' : '执行失败'"
              >
                <span>{{ getWorkflowRunState(wf.id).label }}</span>
              </div>
              <button
                type="button"
                class="workflow-delete-btn"
                title="删除工作流"
                @click="handleDeleteWorkflow($event, wf.id, wf.name)"
              >×</button>
            </div>
          </div>

          <!-- System Templates -->
          <div class="workflow-group" v-if="workflowStore.templateWorkflows.length > 0">
            <div class="workflow-group-title">系统预设模板</div>
            <div
              v-for="wf in workflowStore.templateWorkflows"
              :key="wf.id"
              class="workflow-item"
              :class="{ active: workflowStore.currentWorkflowId === wf.id }"
              @click="handleWorkflowClick(wf.id)"
            >
              <span class="workflow-icon" :style="workflowIconStyle(wf)">{{ wf.icon }}</span>
              <div class="workflow-info">
                <span class="workflow-name">{{ wf.name }}</span>
                <span class="workflow-time">{{ wf.time }}</span>
              </div>
              <div
                v-if="getWorkflowRunState(wf.id)"
                class="workflow-progress-ring"
                :class="'workflow-progress-' + getWorkflowRunState(wf.id).status"
                :style="progressRingStyle(getWorkflowRunState(wf.id))"
                :title="getWorkflowRunState(wf.id).status === 'running' ? `执行中 ${getWorkflowRunState(wf.id).progress}%` : getWorkflowRunState(wf.id).status === 'completed' ? '已完成' : '执行失败'"
              >
                <span>{{ getWorkflowRunState(wf.id).label }}</span>
              </div>
            </div>
          </div>

          <!-- Empty State -->
          <div v-if="workflowStore.customWorkflows.length === 0 && workflowStore.templateWorkflows.length === 0" class="workflow-empty">
            <div class="workflow-empty-icon">📋</div>
            <div class="workflow-empty-text">暂无工作流</div>
            <button class="workflow-empty-btn" @click="handleNewWorkflow">创建第一个工作流</button>
          </div>
        </div>
      </template>

      <!-- ===================== 组件库面板 ===================== -->
      <template v-else>
        <!-- Search -->
        <div class="sidebar-section sidebar-search">
          <input
            type="text"
            v-model="toolboxSearch"
            placeholder="搜索组件..."
          />
        </div>

        <!-- Toolbox：左侧可拖入画布，右侧 + 仍一键添加 -->
        <div class="sidebar-scroll">
          <div
            v-for="section in filteredToolboxSections"
            :key="section.section"
            class="toolbox-section"
          >
            <div class="toolbox-section-title">{{ section.section }}</div>
            <div
              v-for="item in section.items"
              :key="section.section + '|' + item.schemaKey + '|' + item.name"
              class="toolbox-item"
            >
              <div
                class="toolbox-item-main"
                draggable="true"
                title="按住拖到画布"
                @dragstart="onToolboxDragStart($event, item)"
                @dragend="onToolboxDragEnd"
              >
                <div class="toolbox-item-icon">{{ item.icon }}</div>
                <span class="toolbox-item-name">{{ item.name }}</span>
              </div>
              <button
                type="button"
                class="toolbox-item-add"
                draggable="false"
                title="添加到画布末尾"
                @click.stop="handleAddNode(item)"
              >+</button>
            </div>
          </div>
        </div>
      </template>
    </template>
  </aside>
</template>

<style scoped>
.sidebar-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 120px;
}

.loading-dots {
  display: flex;
  gap: 6px;
}

.loading-dots span {
  width: 8px;
  height: 8px;
  background: var(--accent-purple);
  border-radius: 50%;
  animation: pulse-dot 1.4s ease-in-out infinite;
}

.loading-dots span:nth-child(2) { animation-delay: 0.2s; }
.loading-dots span:nth-child(3) { animation-delay: 0.4s; }

@keyframes pulse-dot {
  0%, 80%, 100% { opacity: 0.3; transform: scale(0.8); }
  40% { opacity: 1; transform: scale(1); }
}

.template-quick-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.15), rgba(168, 85, 247, 0.1));
  border: 1px solid rgba(99, 102, 241, 0.3);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all 0.2s;
  position: relative;
  overflow: hidden;
}

.template-quick-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.1), rgba(168, 85, 247, 0.05));
  opacity: 0;
  transition: opacity 0.2s;
}

.template-quick-card:hover {
  border-color: rgba(99, 102, 241, 0.5);
  transform: translateY(-1px);
  box-shadow: 0 4px 16px rgba(99, 102, 241, 0.2);
}

.template-quick-card:hover::before {
  opacity: 1;
}

.template-quick-icon {
  width: 40px;
  height: 40px;
  background: linear-gradient(135deg, var(--accent-primary), var(--accent-purple));
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  flex-shrink: 0;
}

.template-quick-info {
  flex: 1;
  min-width: 0;
}

.template-quick-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 2px;
}

.template-quick-desc {
  font-size: 12px;
  color: var(--text-muted);
}

.template-quick-badge {
  font-size: 11px;
  font-weight: 600;
  color: var(--accent-primary);
  background: rgba(99, 102, 241, 0.15);
  padding: 2px 8px;
  border-radius: 10px;
  flex-shrink: 0;
}

.workflow-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 40px 20px;
  gap: 8px;
}

.workflow-empty-icon {
  font-size: 40px;
  opacity: 0.3;
}

.workflow-empty-text {
  font-size: 14px;
  color: var(--text-muted);
}

.workflow-empty-btn {
  margin-top: 8px;
  padding: 8px 16px;
  background: rgba(99, 102, 241, 0.15);
  border: 1px solid rgba(99, 102, 241, 0.3);
  border-radius: var(--radius-md);
  font-size: 13px;
  font-weight: 500;
  color: var(--accent-primary);
  cursor: pointer;
  transition: all 0.2s;
}

.workflow-empty-btn:hover {
  background: rgba(99, 102, 241, 0.25);
  border-color: var(--accent-primary);
}

.workflow-progress-ring {
  --workflow-progress: 0deg;
  width: 34px;
  height: 34px;
  flex-shrink: 0;
  border-radius: 50%;
  display: grid;
  place-items: center;
  background:
    conic-gradient(var(--accent-cyan) var(--workflow-progress), rgba(45, 99, 139, 0.18) 0deg);
  box-shadow: 0 3px 10px rgba(28, 80, 128, 0.16);
  position: relative;
}

.workflow-progress-ring::after {
  content: '';
  position: absolute;
  inset: 4px;
  border-radius: 50%;
  background: var(--bg-card);
  border: 1px solid rgba(45, 99, 139, 0.12);
}

.workflow-progress-ring span {
  position: relative;
  z-index: 1;
  font-size: 10px;
  font-weight: 800;
  color: var(--text-primary);
  letter-spacing: -0.3px;
}

.workflow-progress-running {
  background:
    conic-gradient(var(--accent-cyan) var(--workflow-progress), rgba(45, 99, 139, 0.18) 0deg);
}

.workflow-progress-completed {
  background: conic-gradient(var(--accent-success) 360deg, rgba(45, 99, 139, 0.18) 0deg);
}

.workflow-progress-completed span {
  color: var(--accent-success);
  font-size: 14px;
}

.workflow-progress-failed {
  background: conic-gradient(var(--accent-danger) 360deg, rgba(45, 99, 139, 0.18) 0deg);
}

.workflow-progress-failed span {
  color: var(--accent-danger);
  font-size: 14px;
}

.workflow-delete-btn {
  width: 26px;
  height: 26px;
  flex-shrink: 0;
  border: 1px solid rgba(225, 29, 72, 0.18);
  border-radius: var(--radius-sm);
  background: rgba(225, 29, 72, 0.08);
  color: var(--accent-danger);
  font-size: 18px;
  line-height: 1;
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.15s, background 0.15s, border-color 0.15s, transform 0.15s;
}

.workflow-item:hover .workflow-delete-btn,
.workflow-item.active .workflow-delete-btn {
  opacity: 1;
}

.workflow-delete-btn:hover {
  background: rgba(225, 29, 72, 0.16);
  border-color: var(--accent-danger);
  transform: translateY(-1px);
}

.toolbox-item-main {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: grab;
}

.toolbox-item-main:active {
  cursor: grabbing;
}
</style>
