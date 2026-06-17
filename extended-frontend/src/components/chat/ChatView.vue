<script setup>
defineOptions({ name: 'ChatView' })

import { ref, onMounted, onUnmounted, nextTick, watch, computed } from 'vue'
import { marked } from 'marked'
import { useSessionStore } from '../../stores/sessionStore'
import { useFileStore } from '../../stores/fileStore'
import { useTabStore } from '../../stores/tabStore'
import libraryApi from '../../api/library'
import ChatSidebar from './ChatSidebar.vue'

// 配置 marked
marked.setOptions({
  breaks: true,
  gfm: true,
})

const sessionStore = useSessionStore()
const fileStore = useFileStore()
const tabStore = useTabStore()

const messagesContainer = ref(null)
const inputText = ref('')
const textareaRef = ref(null)
const isDragover = ref(false)
const previewEntities = ref({})
const showLibraryPicker = ref(false)
const librarySpaces = ref([])
const libraryDocs = ref([])
const libraryPickerSpaceId = ref('')
const libraryPickerSelectedIds = ref(new Set())
const libraryPickerLoading = ref(false)
const libraryPickerError = ref('')

const showProgress = computed(() => sessionStore.showProgressBar)
const progressVal = computed(() => sessionStore.progressValue)
const progressMsg = computed(() => sessionStore.progressMessage)
const selectedFileCount = computed(() => {
  return [...fileStore.tempFiles.data, ...fileStore.tempFiles.template]
    .filter(file => file.is_selected).length
})

const chatModes = ['default_conversation', 'document_understanding', 'document_editing']
const modeLabels = {
  default_conversation: '默认对话',
  document_understanding: '文档理解',
  document_editing: '文档编辑'
}

function switchChatMode(mode) {
  sessionStore.switchMode(mode)
}

const quickActions = [
  { icon: '📖', text: '分析文档', prompt: '分析这份文档的核心内容', mode: 'document_understanding' },
  { icon: '🎯', text: '提取信息', prompt: '提取文档中的关键信息', mode: 'document_understanding' },
  { icon: '🌍', text: '翻译内容', prompt: '帮我翻译这份文档的主要内容', mode: 'document_understanding' },
  { icon: '🔄', text: '使用工作流', action: 'workflow' }
]

function scrollToBottom() {
  nextTick(() => {
    if (messagesContainer.value) {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
    }
  })
}

watch(() => sessionStore.currentSessionId, () => {
  scrollToBottom()
})

watch(() => sessionStore.messages.length, () => {
  scrollToBottom()
})

watch(() => sessionStore.isStreaming, (streaming) => {
  if (streaming) scrollToBottom()
})

onMounted(() => {
  sessionStore.connectWebSocket()
  scrollToBottom()
})

onUnmounted(() => {
  sessionStore.disconnectWebSocket()
})

function insertPrompt(prompt) {
  if (prompt.action) {
    tabStore.switchTab(prompt.action)
    return
  }
  if (prompt.mode) {
    sessionStore.switchMode(prompt.mode)
  }
  if (prompt.prompt) {
    inputText.value = prompt.prompt
    nextTick(() => {
      autoResize()
      textareaRef.value?.focus()
    })
  }
}

function formatTime(isoString) {
  if (!isoString) return ''
  const dt = new Date(isoString)
  if (Number.isNaN(dt.getTime())) return ''
  return dt.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

function copyMessage(content) {
  navigator.clipboard.writeText(content)
}

function renderMarkdown(content) {
  if (!content) return ''
  return marked.parse(content)
}

function autoResize() {
  if (textareaRef.value) {
    textareaRef.value.style.height = 'auto'
    textareaRef.value.style.height = Math.min(textareaRef.value.scrollHeight, 200) + 'px'
  }
}

function handleKeyDown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    sendMessage()
  }
}

async function sendMessage() {
  const text = inputText.value.trim()
  if (!text) return

  await sessionStore.sendMessage(text, sessionStore.currentMode)
  inputText.value = ''
  if (textareaRef.value) {
    textareaRef.value.style.height = 'auto'
  }
}

function handleDragOver(e) {
  e.preventDefault()
  isDragover.value = true
}

function handleDragLeave() {
  isDragover.value = false
}

function handleDrop(e) {
  e.preventDefault()
  isDragover.value = false
  const files = Array.from(e.dataTransfer.files)
  if (files.length > 0) {
    files.forEach(file => fileStore.addFile(fileStore.currentFileType, file))
  }
}

function handleFileInput(e) {
  const files = Array.from(e.target.files)
  if (files.length > 0) {
    files.forEach(file => fileStore.addFile(fileStore.currentFileType, file))
  }
}

function triggerFileInput() {
  const input = document.createElement('input')
  input.type = 'file'
  input.multiple = true
  input.accept = '.pdf,.doc,.docx,.xlsx,.xls,.txt'
  input.onchange = handleFileInput
  input.click()
}

async function openLibraryPicker() {
  showLibraryPicker.value = true
  libraryPickerError.value = ''
  if (librarySpaces.value.length === 0) {
    await loadLibrarySpacesForPicker()
  } else if (libraryPickerSpaceId.value) {
    await loadLibraryDocsForPicker(libraryPickerSpaceId.value)
  }
}

async function loadLibrarySpacesForPicker() {
  libraryPickerLoading.value = true
  libraryPickerError.value = ''
  try {
    const res = await libraryApi.getSpaces()
    librarySpaces.value = res?.spaces || []
    if (!libraryPickerSpaceId.value && librarySpaces.value.length > 0) {
      libraryPickerSpaceId.value = librarySpaces.value[0].id
    }
    if (libraryPickerSpaceId.value) {
      await loadLibraryDocsForPicker(libraryPickerSpaceId.value)
    }
  } catch (e) {
    libraryPickerError.value = e.message || '加载文档库失败'
  } finally {
    libraryPickerLoading.value = false
  }
}

async function loadLibraryDocsForPicker(spaceId) {
  if (!spaceId) {
    libraryDocs.value = []
    return
  }
  libraryPickerLoading.value = true
  libraryPickerError.value = ''
  libraryPickerSelectedIds.value = new Set()
  try {
    const res = await libraryApi.getDocs(spaceId)
    libraryDocs.value = (res?.docs || []).map(d => ({
      id: d.id,
      name: d.file_name,
      file_name: d.file_name,
      file_size: d.file_size,
      size_bytes: d.file_size,
      file_extension: d.file_extension,
      file_path: d.storage_key || d.blob_url || d.file_path || '',
      storage_key: d.storage_key || d.blob_url || d.file_path || '',
      created_at: d.created_at,
    }))
  } catch (e) {
    libraryPickerError.value = e.message || '加载文档失败'
  } finally {
    libraryPickerLoading.value = false
  }
}

function changeLibraryPickerSpace(event) {
  libraryPickerSpaceId.value = event.target.value
  loadLibraryDocsForPicker(libraryPickerSpaceId.value)
}

function toggleLibraryPickerDoc(docId) {
  const next = new Set(libraryPickerSelectedIds.value)
  if (next.has(docId)) next.delete(docId)
  else next.add(docId)
  libraryPickerSelectedIds.value = next
}

function confirmLibraryPicker() {
  const docs = libraryDocs.value.filter(doc => libraryPickerSelectedIds.value.has(doc.id))
  fileStore.addReferencedFiles(fileStore.currentFileType, docs)
  showLibraryPicker.value = false
  fileStore.filesPanelCollapsed = false
  libraryPickerSelectedIds.value = new Set()
}

function closeLibraryPicker() {
  showLibraryPicker.value = false
}

function switchFileType(type) {
  fileStore.switchFileType(type)
}

function removeFile(file, type) {
  sessionStore.removeSessionFile(file, type)
}

function formatFileSize(bytes) {
  if (!bytes) return ''
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

function getFileExt(fileName) {
  if (!fileName || typeof fileName !== 'string') return 'FILE'
  const ext = fileName.split('.').pop()
  return ext ? ext.toUpperCase() : 'FILE'
}

function downloadResultFile(fileInfo) {
  const sid = sessionStore.currentSessionId
  if (fileInfo?.file_id && sid) {
    const url = `/api/sessions/${encodeURIComponent(sid)}/files/${encodeURIComponent(fileInfo.file_id)}/download`
    window.open(url, '_blank', 'noopener,noreferrer')
    return
  }
  if (!fileInfo?.file_path) return
  const url = `/api/files/download?path=${encodeURIComponent(fileInfo.file_path)}`
  const a = document.createElement('a')
  a.href = url
  a.download = fileInfo.file_name
  a.click()
}

function canDownloadFile(fileInfo) {
  return !!(fileInfo?.file_id || String(fileInfo?.file_path || '').trim())
}

function getDownloadFiles(files) {
  return (Array.isArray(files) ? files : []).filter(canDownloadFile)
}

// ============ 实体提取表格预览 ============
function getPreviewEntities(msg) {
  if (!msg) return []
  if (previewEntities.value[msg.id]) return previewEntities.value[msg.id]
  const entities = msg.entitiesData || []
  if (entities.length > 0) {
    previewEntities.value[msg.id] = entities
  }
  return entities
}

function getEntityHeaders(msg) {
  const entities = getPreviewEntities(msg)
  if (!entities || entities.length === 0) return []
  return Object.keys(entities[0])
}

function getEntityCells(entity, header) {
  const val = entity[header]
  if (val === undefined || val === null) return ''
  if (Array.isArray(val)) return val[0] ?? ''
  return String(val)
}

function downloadEntitiesJson(msg) {
  const entities = getPreviewEntities(msg)
  if (!entities.length) return
  const json = JSON.stringify(entities, null, 2)
  const blob = new Blob([json], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'extraction_result.json'
  a.click()
  URL.revokeObjectURL(url)
}

/** WebSocket 写在根上；历史消息可能在 metadata.tableFillingData */
function getTableFillingData(msg) {
  if (!msg || msg.role !== 'assistant') return null
  let metadata = msg.metadata
  if (typeof metadata === 'string') {
    try {
      metadata = JSON.parse(metadata)
    } catch {
      metadata = null
    }
  }
  return msg.tableFillingData ?? metadata?.tableFillingData ?? metadata?.table_filling_data ?? null
}

function getTableFillDownloadFiles(msg) {
  const tf = getTableFillingData(msg)
  if (Array.isArray(tf?.generated_files) && tf.generated_files.length) return getDownloadFiles(tf.generated_files)
  if (Array.isArray(tf?.generatedFiles) && tf.generatedFiles.length) return getDownloadFiles(tf.generatedFiles)
  if (Array.isArray(msg?.generated_files) && msg.generated_files.length) return getDownloadFiles(msg.generated_files)
  if (Array.isArray(msg?.generatedFiles) && msg.generatedFiles.length) return getDownloadFiles(msg.generatedFiles)
  const fallback = []
  const templateOutput = tf?.template_output || tf?.output_template
  if (templateOutput) {
    const path = String(templateOutput)
    const suffix = path.split(/[\\/]/).pop()?.split('.').pop() || 'docx'
    fallback.push({
      file_path: path,
      file_name: path.split(/[\\/]/).pop() || `table_filling_result.${suffix}`,
    })
  }
  if (tf?.output_json) {
    const path = String(tf.output_json)
    fallback.push({
      file_path: path,
      file_name: path.split(/[\\/]/).pop() || 'table_filling_result.json',
    })
  }
  if (fallback.length) return getDownloadFiles(fallback)
  return []
}

const TABLE_PREVIEW_MAX_ROWS = 50

function tablePreviewRows(tf) {
  if (!tf || typeof tf !== 'object') return []
  const a = tf.previewData
  const b = tf.filtered_rows
  if (Array.isArray(a) && a.length) return a
  if (Array.isArray(b) && b.length) return b
  return []
}

function tablePreviewDisplayRows(tf) {
  return tablePreviewRows(tf).slice(0, TABLE_PREVIEW_MAX_ROWS)
}

function tablePreviewExtraCount(tf) {
  const n = tablePreviewRows(tf).length
  return n > TABLE_PREVIEW_MAX_ROWS ? n - TABLE_PREVIEW_MAX_ROWS : 0
}

function tablePreviewColumns(rows) {
  if (!Array.isArray(rows) || rows.length === 0) return []
  const ordered = []
  const seen = new Set()
  const first = rows[0]
  if (first && typeof first === 'object' && !Array.isArray(first)) {
    for (const k of Object.keys(first)) {
      ordered.push(k)
      seen.add(k)
    }
  }
  for (const row of rows) {
    if (!row || typeof row !== 'object' || Array.isArray(row)) continue
    for (const k of Object.keys(row)) {
      if (!seen.has(k)) {
        seen.add(k)
        ordered.push(k)
      }
    }
  }
  return ordered
}

function formatTablePreviewCell(val) {
  if (val === null || val === undefined || val === '') return '—'
  if (typeof val === 'object') {
    try {
      return JSON.stringify(val)
    } catch {
      return String(val)
    }
  }
  return String(val)
}

/** 每条助手消息最多算一次预览结构，避免模板里对每格重复 tablePreviewColumns */
function buildTableFillPreviewBundle(msg) {
  const tf = getTableFillingData(msg)
  if (!tf || tf.success === undefined) return null
  const rows = tablePreviewRows(tf)
  if (!rows.length) return null
  const columns = tablePreviewColumns(rows)
  const displayRows = rows.slice(0, TABLE_PREVIEW_MAX_ROWS)
  const extra = Math.max(0, rows.length - TABLE_PREVIEW_MAX_ROWS)
  return { tf, columns, displayRows, totalRows: rows.length, extra }
}

const tableFillPreviewByMessageKey = computed(() => {
  const list = sessionStore.messages
  const out = {}
  for (let i = 0; i < list.length; i++) {
    const msg = list[i]
    if (msg.role !== 'assistant') continue
    const key = msg.id != null && msg.id !== '' ? String(msg.id) : `_i_${i}`
    const b = buildTableFillPreviewBundle(msg)
    if (b) out[key] = b
  }
  return out
})

function tablePreviewBundleFor(msg, index) {
  const key = msg.id != null && msg.id !== '' ? String(msg.id) : `_i_${index}`
  return tableFillPreviewByMessageKey.value[key] || null
}

function tablePreviewBundleList(msg, index) {
  const b = tablePreviewBundleFor(msg, index)
  return b ? [b] : []
}

function getFileStyle(fileName) {
  const ext = (fileName || '').split('.').pop().toLowerCase()
  const map = {
    pdf:  { bg: 'rgba(239, 68, 68, 0.15)', text: '#ef4444', icon: '📄' },
    doc:  { bg: 'rgba(59, 130, 246, 0.15)', text: '#3b82f6', icon: '📝' },
    docx: { bg: 'rgba(59, 130, 246, 0.15)', text: '#3b82f6', icon: '📝' },
    xls:  { bg: 'rgba(16, 185, 129, 0.15)', text: '#10b981', icon: '📊' },
    xlsx: { bg: 'rgba(16, 185, 129, 0.15)', text: '#10b981', icon: '📊' },
    txt:  { bg: 'rgba(161, 161, 170, 0.15)', text: '#a1a1aa', icon: '📃' },
    md:   { bg: 'rgba(161, 161, 170, 0.15)', text: '#a1a1aa', icon: '📃' },
  }
  return map[ext] || { bg: 'rgba(161, 161, 170, 0.15)', text: '#a1a1aa', icon: '📎' }
}

function userMessageAttachments(msg) {
  const m = msg.metadata || {}
  const data = (m.files || []).map((f) => ({ ...f, _kind: 'data' }))
  const tpl = (m.template_files || []).map((f) => ({ ...f, _kind: 'template' }))
  return [...data, ...tpl]
}
</script>

<template>
  <div class="chat-view">
    <ChatSidebar :collapsed="sessionStore.sidebarCollapsed" />
    <div class="chat-main" :class="{ 'sidebar-collapsed': sessionStore.sidebarCollapsed }">
      <!-- 展开按钮 - 在右侧始终可见 -->
      <button v-if="sessionStore.sidebarCollapsed" class="sidebar-toggle collapsed-toggle" @click="sessionStore.toggleSidebar" title="展开侧边栏">
        →
      </button>

      <!-- 处理模式气泡容器 -->
      <div class="mode-selector">
        <span class="mode-label">处理模式:</span>
        <div class="mode-tabs">
          <button
            v-for="mode in chatModes"
            :key="mode"
            class="mode-tab"
            :class="{ active: sessionStore.currentMode === mode }"
            @click="switchChatMode(mode)"
          >
            {{ modeLabels[mode] }}
          </button>
        </div>
      </div>

      <div class="chat-messages" ref="messagesContainer">
        <div v-if="sessionStore.isInitializing" class="welcome-state">
          <div class="welcome-icon">💬</div>
          <h1 class="welcome-title">加载中...</h1>
        </div>

        <div v-else-if="sessionStore.messages.length === 0" class="welcome-state">
          <div class="welcome-icon">💬</div>
          <h1 class="welcome-title">智能对话</h1>
          <p class="welcome-subtitle">
            通过自然语言与系统交互，完成文档分析，信息提取，内容生成等任务
          </p>
          <div class="quick-actions">
            <button
              v-for="action in quickActions"
              :key="action.text"
              class="quick-action"
              @click="insertPrompt(action)"
            >
              <span>{{ action.icon }}</span>
              <span>{{ action.text }}</span>
            </button>
          </div>
        </div>

        <div
          v-for="(msg, index) in sessionStore.messages"
          :key="msg.id != null ? msg.id : `m-${index}`"
          class="message"
          :class="msg.role"
        >
          <div class="message-avatar">
            {{ msg.role === 'user' ? '👤' : msg.role === 'system' ? 'ℹ️' : '🤖' }}
          </div>
          <div class="message-content">
            <!-- 用户消息：带附件时显示文件卡片 -->
            <template v-if="msg.role === 'user' && userMessageAttachments(msg).length > 0">
              <div class="user-attachments">
                <div
                  v-for="(att, idx) in userMessageAttachments(msg)"
                  :key="`${att.id ?? att.file_id ?? idx}-${att.file_name}`"
                  class="attachment-card"
                  :class="{ 'attachment-uploading': att.pending }"
                >
                  <div
                    class="attachment-icon"
                    :style="{ background: getFileStyle(att.file_name).bg, color: getFileStyle(att.file_name).text }"
                  >
                    <span v-if="att.pending" class="attachment-spinner">⏳</span>
                    <span v-else>{{ getFileStyle(att.file_name).icon }}</span>
                  </div>
                  <div class="attachment-info">
                    <div class="attachment-name" :title="att.file_name">{{ att.file_name }}</div>
                    <div class="attachment-meta">
                      <span v-if="att.pending" class="upload-status">上传中...</span>
                      <template v-else>
                        {{ getFileExt(att.file_name) }}
                        <span v-if="formatFileSize(att.file_size)"> | {{ formatFileSize(att.file_size) }}</span>
                      </template>
                      <span v-if="att._kind === 'template'" class="template-badge">· 模板</span>
                    </div>
                  </div>
                </div>
              </div>
              <div v-if="msg.content" class="message-bubble">
                <span>{{ msg.content }}</span>
              </div>
            </template>
            <!-- 用户消息：无附件 -->
            <div v-else-if="msg.role === 'user'" class="message-bubble">
              <span>{{ msg.content }}</span>
            </div>
            <!-- 系统消息 -->
            <div v-else-if="msg.role === 'system'" class="message-bubble system">
              <span>{{ msg.content }}</span>
            </div>
            <!-- 助手消息 -->
            <div v-else class="message-bubble" :class="{ 'md-content': msg.role === 'assistant' }">
              <div v-if="msg.role === 'assistant'" v-html="renderMarkdown(msg.content)"></div>
              <!-- Loading 动画 -->
              <div v-if="msg.isLoading" class="typing-indicator">
                <span class="typing-dot"></span>
                <span class="typing-dot"></span>
                <span class="typing-dot"></span>
              </div>
              <!-- 表格填表预览：每条消息只取一次 bundle（computed 预聚合 + 单次 list 迭代） -->
              <template v-for="tb in tablePreviewBundleList(msg, index)" :key="(msg.id != null ? msg.id : index) + '-tbl'">
                <div class="entity-preview table-fill-preview">
                  <div class="entity-preview-header">
                    <div>
                      <span class="entity-preview-title">
                        📋 表格结果预览（{{ tb.totalRows }} 行）
                      </span>
                      <span v-if="tb.tf.matched_rows != null" class="table-fill-stats table-fill-stats-inline">
                        命中 {{ tb.tf.matched_rows }}/{{ tb.tf.total_rows ?? '—' }} 行
                      </span>
                    </div>
                    <div v-if="getTableFillDownloadFiles(msg).length" class="entity-preview-actions">
                      <button
                        v-for="f in getTableFillDownloadFiles(msg)"
                        :key="f.file_id ?? f.file_path"
                        class="entity-action-btn"
                        type="button"
                        @click="downloadResultFile(f)"
                      >
                        {{ getFileExt(f.file_name) }} ↓
                      </button>
                    </div>
                  </div>
                  <div class="entity-table-wrapper">
                    <table class="entity-table">
                      <thead>
                        <tr>
                          <th v-for="col in tb.columns" :key="col">
                            {{ col }}
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr v-for="(row, ri) in tb.displayRows" :key="ri">
                          <td
                            v-for="col in tb.columns"
                            :key="col"
                            :title="formatTablePreviewCell(row && row[col] !== undefined ? row[col] : '')"
                          >
                            {{ formatTablePreviewCell(row && row[col] !== undefined ? row[col] : '') }}
                          </td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                  <div v-if="tb.extra > 0" class="entity-preview-more">
                    还有 {{ tb.extra }} 行未展示，请下载生成文件查看全部
                  </div>
                </div>
              </template>
              <!-- 仅表格填表：无 previewData 时仍要下载；勿用 getTableFillDownloadFiles 单独判断，否则无 tableFillingData 时会误用 msg.generated_files 与实体提取重复 -->
              <div
                v-if="getTableFillingData(msg) && getTableFillDownloadFiles(msg).length && !tablePreviewBundleFor(msg, index)"
                class="entity-preview table-fill-preview table-fill-downloads-only"
              >
                <div class="entity-preview-header">
                  <span class="entity-preview-title">📋 生成结果</span>
                  <div class="entity-preview-actions">
                    <button
                      v-for="f in getTableFillDownloadFiles(msg)"
                      :key="f.file_id ?? f.file_path"
                      class="entity-action-btn"
                      type="button"
                      @click="downloadResultFile(f)"
                    >
                      {{ getFileExt(f.file_name) }} ↓
                    </button>
                  </div>
                </div>
              </div>
              <!-- 混合模式专用：仅展示统一填表后的结果预览与下载 -->
              <template v-if="msg.mixedSource === 'merged' && (msg.tableFillingPreview || getDownloadFiles(msg.generated_files).length)">
                <div class="entity-preview table-fill-preview">
                  <div class="entity-preview-header">
                    <div>
                      <span class="entity-preview-title">📋 混合填表结果预览</span>
                      <span v-if="msg.tableFillingPreview?.matched_rows != null" class="table-fill-stats table-fill-stats-inline">
                        共 {{ msg.tableFillingPreview.matched_rows }} 行
                      </span>
                    </div>
                    <div v-if="getDownloadFiles(msg.generated_files).length" class="entity-preview-actions">
                      <button v-for="f in getDownloadFiles(msg.generated_files)" :key="f.file_id ?? f.file_path" class="entity-action-btn" @click="downloadResultFile(f)">
                        {{ getFileExt(f.file_name) }} ↓
                      </button>
                    </div>
                  </div>
                  <div v-if="msg.tableFillingPreview?.previewData?.length" class="entity-table-wrapper">
                    <table class="entity-table">
                      <thead>
                        <tr>
                          <th v-for="col in tablePreviewColumns(msg.tableFillingPreview.previewData)" :key="col">{{ col }}</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr v-for="(row, ri) in msg.tableFillingPreview.previewData.slice(0, 50)" :key="ri">
                          <td v-for="col in tablePreviewColumns(msg.tableFillingPreview.previewData)" :key="col">
                            {{ formatTablePreviewCell(row && row[col] !== undefined ? row[col] : '') }}
                          </td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                  <div v-else class="entity-preview-more">
                    已生成混合填表文件，请使用下载按钮查看完整结果。
                  </div>
                  <div v-if="(msg.tableFillingPreview?.previewData?.length ?? 0) > 50" class="entity-preview-more">
                    还有 {{ msg.tableFillingPreview.previewData.length - 50 }} 行未展示，请下载生成文件查看全部
                  </div>
                </div>
              </template>
              <!-- 非混合模式的实体提取结果：表格预览 -->
              <div v-else-if="msg.entitiesData?.length && msg.mixedSource !== 'merged'" class="entity-preview table-fill-preview">
                <div class="entity-preview-header">
                  <span class="entity-preview-title">📊 提取结果预览（共 {{ msg.entitiesData.length }} 条）</span>
                  <div class="entity-preview-actions">
                    <button v-for="f in getDownloadFiles(msg.generated_files)" :key="f.file_id ?? f.file_path" class="entity-action-btn" @click="downloadResultFile(f)">
                      {{ getFileExt(f.file_name) }} ↓
                    </button>
                  </div>
                </div>
                <div class="entity-table-wrapper">
                  <table class="entity-table">
                    <thead>
                      <tr>
                        <th v-for="h in getEntityHeaders(msg)" :key="h">{{ h }}</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="(entity, rowIdx) in msg.entitiesData.slice(0, 20)" :key="rowIdx">
                        <td v-for="h in getEntityHeaders(msg)" :key="h" :title="entity[h] != null ? String(entity[h]) : ''">
                          {{ getEntityCells(entity, h) }}
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <div v-if="msg.entitiesData.length > 20" class="entity-preview-more">
                  还有 {{ msg.entitiesData.length - 20 }} 条数据，下载完整文件查看全部
                </div>
              </div>
              <!-- 非混合模式的表格填表预览 -->
              <div v-if="msg.tableFillingPreview && msg.mixedSource !== 'merged'" class="entity-preview table-fill-preview">
                <div class="entity-preview-header">
                  <div>
                    <span class="entity-preview-title">📋 表格结果预览（{{ msg.tableFillingPreview.previewData?.length ?? msg.tableFillingPreview.matched_rows ?? 0 }} 行）</span>
                    <span v-if="msg.tableFillingPreview.matched_rows != null" class="table-fill-stats table-fill-stats-inline">
                      命中 {{ msg.tableFillingPreview.matched_rows }}/{{ msg.tableFillingPreview.total_rows ?? '—' }} 行
                    </span>
                  </div>
                </div>
                <div v-if="msg.tableFillingPreview.previewData?.length" class="entity-table-wrapper">
                  <table class="entity-table">
                    <thead>
                      <tr>
                        <th v-for="col in tablePreviewColumns(msg.tableFillingPreview.previewData)" :key="col">{{ col }}</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="(row, ri) in msg.tableFillingPreview.previewData.slice(0, 50)" :key="ri">
                        <td v-for="col in tablePreviewColumns(msg.tableFillingPreview.previewData)" :key="col">
                          {{ formatTablePreviewCell(row && row[col] !== undefined ? row[col] : '') }}
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <div v-if="(msg.tableFillingPreview.previewData?.length ?? 0) > 50" class="entity-preview-more">
                  还有 {{ msg.tableFillingPreview.previewData.length - 50 }} 行未展示，请下载生成文件查看全部
                </div>
              </div>
              <!-- 混合模式或非表格任务的文件下载：独立显示，不与 entitiesData 块冲突 -->
              <div
                v-if="getDownloadFiles(msg.generated_files).length && !getTableFillingData(msg) && msg.entitiesData?.length"
                class="entity-preview table-fill-preview table-fill-downloads-only"
              >
                <div class="entity-preview-header">
                  <span class="entity-preview-title">📥 表格数据下载</span>
                  <div class="entity-preview-actions">
                    <button v-for="f in getDownloadFiles(msg.generated_files)" :key="f.file_id ?? f.file_path" class="entity-action-btn" @click="downloadResultFile(f)">
                      {{ getFileExt(f.file_name) }} ↓
                    </button>
                  </div>
                </div>
              </div>
              <!-- 仅文件下载：实体提取等场景；表格填表已在上方标题栏处理，勿与 msg.generated_files 再渲一排 -->
              <div
                v-else-if="getDownloadFiles(msg.generated_files).length && !getTableFillingData(msg)"
                class="entity-preview table-fill-preview table-fill-downloads-only"
              >
                <div class="entity-preview-header">
                  <span class="entity-preview-title">📊 生成结果</span>
                  <div class="entity-preview-actions">
                    <button v-for="f in getDownloadFiles(msg.generated_files)" :key="f.file_id ?? f.file_path" class="entity-action-btn" @click="downloadResultFile(f)">
                      {{ getFileExt(f.file_name) }} ↓
                    </button>
                  </div>
                </div>
              </div>
            </div>
            <div class="message-time">{{ formatTime(msg.created_at) }}</div>
          </div>
        </div>

        <!-- 上传文件进度 -->
        <div v-if="sessionStore.isUploadingFiles" class="message system">
          <div class="message-avatar">⏳</div>
          <div class="message-content">
            <div class="message-bubble upload-progress">
              <span class="upload-icon">📤</span>
              <span class="upload-text">{{ sessionStore.uploadProgress || '正在上传文件...' }}</span>
            </div>
          </div>
        </div>

        <!-- 进度条（实体提取/表格填表） -->
        <div v-if="showProgress && (sessionStore.currentMode === 'entity_extraction' || sessionStore.currentMode === 'table_filling')" class="message assistant">
          <div class="message-avatar">⚙️</div>
          <div class="message-content">
            <div class="progress-card">
              <div class="progress-header">
                <span class="progress-title">任务处理中</span>
                <span class="progress-msg">{{ progressMsg }}</span>
                <span v-if="progressVal < 100" class="progress-indicator">●</span>
                <span v-else class="progress-done">完成</span>
              </div>
              <div class="progress-bar-container">
                <div class="progress-bar" :style="{ width: progressVal + '%' }"></div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="chat-input-area">
        <div class="chat-input-row">
          <div
            class="file-drop-zone"
            :class="{ dragover: isDragover }"
            @dragover="handleDragOver"
            @dragleave="handleDragLeave"
            @drop="handleDrop"
            @click="triggerFileInput"
          >
            <span class="file-drop-zone-icon">📎</span>
            <span class="file-drop-zone-text">
              拖拽文件或 <span @click.stop="triggerFileInput">浏览</span>
            </span>
            <button class="drop-library-btn" @click.stop="openLibraryPicker">
              从文档库选择
            </button>
            <div class="file-type-switcher">
              <button
                class="file-type-btn"
                :class="{ active: fileStore.currentFileType === 'data' }"
                data-type="data"
                @click.stop="switchFileType('data')"
              >
                数据文件
              </button>
              <button
                class="file-type-btn"
                :class="{ active: fileStore.currentFileType === 'template' }"
                data-type="template"
                @click.stop="switchFileType('template')"
              >
                模板文件
              </button>
            </div>
            <div class="file-count-badges">
              <span v-if="fileStore.hasDataFiles" class="file-badge data-badge">
                📄 {{ fileStore.dataCount }}
              </span>
              <span v-if="fileStore.hasTemplateFiles" class="file-badge template-badge">
                📋 {{ fileStore.templateCount }}
              </span>
            </div>
          </div>

          <div class="chat-input-wrapper">
            <div class="chat-input">
              <textarea
                ref="textareaRef"
                v-model="inputText"
                rows="1"
                placeholder="输入消息..."
                @keydown="handleKeyDown"
                @input="autoResize"
              ></textarea>
            </div>
            <button
              class="send-btn"
              :class="{ loading: sessionStore.isStreaming }"
              @click="sendMessage"
              :disabled="!inputText.trim() || sessionStore.isStreaming"
            >
              <span v-if="!sessionStore.isStreaming">➤</span>
              <span v-else class="send-spinner"></span>
            </button>
          </div>
        </div>

        <!-- Uploaded Files Panel -->
        <div class="uploaded-files-panel">
          <div class="panel-header" @click="fileStore.toggleFilesPanel">
            <span class="panel-title">
              已上传文件
              <span v-if="fileStore.dataCount + fileStore.templateCount > 0" class="file-count">
                ({{ fileStore.dataCount + fileStore.templateCount }})
              </span>
            </span>
            <button class="library-pick-btn" @click.stop="openLibraryPicker">
              从文档库添加
            </button>
            <button
              v-if="selectedFileCount > 0"
              class="library-pick-btn"
              @click.stop="sessionStore.clearAllSelectedFiles"
            >
              取消全选
            </button>
            <span class="panel-toggle" :class="{ collapsed: fileStore.filesPanelCollapsed }">
              {{ fileStore.filesPanelCollapsed ? '▶' : '▼' }}
            </span>
          </div>
          <div class="panel-content" :class="{ collapsed: fileStore.filesPanelCollapsed }">
            <div v-if="fileStore.dataCount + fileStore.templateCount === 0" class="files-empty">
              <span class="empty-icon">📂</span>
              <span class="empty-text">暂无文件，上传文件后可选中发送给 AI</span>
            </div>
            <div v-else class="files-row">
              <!-- Data Files -->
              <div v-if="fileStore.hasDataFiles" class="files-group">
                <span class="files-label">📄 数据文件:</span>
                <div class="files-tags">
                  <div
                    v-for="file in fileStore.tempFiles.data"
                    :key="file.id"
                    class="file-tag"
                    :class="{ selected: file.is_selected }"
                  >
                    <input
                      type="checkbox"
                      :checked="file.is_selected"
                      @change="sessionStore.toggleSessionFileSelection(file, 'data', $event.target.checked)"
                      class="file-checkbox"
                    />
                    <span class="file-icon-small">{{ fileStore.getFileIcon(file.file_name) }}</span>
                    <span class="file-tag-name" :title="file.file_name">{{ file.file_name }}</span>
                    <span class="file-size-small">{{ formatFileSize(file.file_size) }}</span>
                    <button class="file-tag-remove" @click.stop="removeFile(file, 'data')">×</button>
                  </div>
                </div>
              </div>

              <!-- Template Files -->
              <div v-if="fileStore.hasTemplateFiles" class="files-group">
                <span class="files-label">📋 模板文件:</span>
                <div class="files-tags">
                  <div
                    v-for="file in fileStore.tempFiles.template"
                    :key="file.id"
                    class="file-tag template"
                    :class="{ selected: file.is_selected }"
                  >
                    <input
                      type="checkbox"
                      :checked="file.is_selected"
                      @change="sessionStore.toggleSessionFileSelection(file, 'template', $event.target.checked)"
                      class="file-checkbox"
                    />
                    <span class="file-icon-small">{{ fileStore.getFileIcon(file.file_name) }}</span>
                    <span class="file-tag-name" :title="file.file_name">{{ file.file_name }}</span>
                    <span class="file-size-small">{{ formatFileSize(file.file_size) }}</span>
                    <button class="file-tag-remove" @click.stop="removeFile(file, 'template')">×</button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <Teleport to="body">
    <div v-if="showLibraryPicker" class="chat-library-modal" @click.self="closeLibraryPicker">
      <div class="chat-library-dialog">
        <div class="chat-library-header">
          <div>
            <div class="chat-library-title">从文档库添加文件</div>
            <div class="chat-library-subtitle">添加后会作为当前对话附件发送给AI</div>
          </div>
          <button class="chat-library-close" @click="closeLibraryPicker">×</button>
        </div>

        <div class="chat-library-toolbar">
          <select class="chat-library-select" :value="libraryPickerSpaceId" @change="changeLibraryPickerSpace">
            <option v-for="space in librarySpaces" :key="space.id" :value="space.id">
              {{ space.icon || '📁' }} {{ space.name }}
            </option>
          </select>
          <button class="chat-library-refresh" @click="loadLibrarySpacesForPicker">刷新</button>
        </div>

        <div v-if="libraryPickerError" class="chat-library-error">{{ libraryPickerError }}</div>

        <div class="chat-library-body">
          <div v-if="libraryPickerLoading" class="chat-library-empty">加载中...</div>
          <div v-else-if="libraryDocs.length === 0" class="chat-library-empty">当前空间暂无文档</div>
          <template v-else>
            <button
              v-for="doc in libraryDocs"
              :key="doc.id"
              class="chat-library-doc"
              :class="{ selected: libraryPickerSelectedIds.has(doc.id) }"
              @click="toggleLibraryPickerDoc(doc.id)"
            >
              <span class="chat-library-check">{{ libraryPickerSelectedIds.has(doc.id) ? '✓' : '' }}</span>
              <span class="chat-library-file-icon">{{ fileStore.getFileIcon(doc.name) }}</span>
              <span class="chat-library-file-name" :title="doc.name">{{ doc.name }}</span>
              <span class="chat-library-file-size">{{ formatFileSize(doc.file_size) }}</span>
            </button>
          </template>
        </div>

        <div class="chat-library-footer">
          <button class="chat-library-cancel" @click="closeLibraryPicker">取消</button>
          <button
            class="chat-library-confirm"
            :disabled="libraryPickerSelectedIds.size === 0"
            @click="confirmLibraryPicker"
          >
            添加{{ libraryPickerSelectedIds.size }}个文件
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
/* 进度条 */
.progress-card {
  background: #f9fafb;
  border-radius: 8px;
  padding: 12px 16px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.library-pick-btn {
  margin-left: auto;
  padding: 6px 10px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: rgba(99, 102, 241, 0.12);
  color: var(--text-primary);
  font-size: 12px;
  cursor: pointer;
}

.library-pick-btn:hover {
  border-color: var(--accent-primary);
  background: rgba(99, 102, 241, 0.2);
}

.chat-library-modal {
  position: fixed;
  inset: 0;
  z-index: 10000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.68);
}

.chat-library-dialog {
  width: min(720px, calc(100vw - 40px));
  max-height: min(720px, calc(100vh - 40px));
  display: flex;
  flex-direction: column;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 14px;
  box-shadow: 0 24px 80px rgba(0, 0, 0, 0.55);
  overflow: hidden;
}

.chat-library-header,
.chat-library-toolbar,
.chat-library-footer {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 18px;
  border-bottom: 1px solid var(--border-color);
}

.chat-library-footer {
  justify-content: flex-end;
  border-top: 1px solid var(--border-color);
  border-bottom: 0;
}

.chat-library-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
}

.chat-library-subtitle {
  margin-top: 4px;
  font-size: 12px;
  color: var(--text-muted);
}

.chat-library-close {
  margin-left: auto;
  width: 32px;
  height: 32px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--text-muted);
  font-size: 22px;
  cursor: pointer;
}

.chat-library-close:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.chat-library-select {
  flex: 1;
  min-width: 0;
  padding: 9px 12px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.chat-library-refresh,
.chat-library-cancel,
.chat-library-confirm {
  padding: 9px 14px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-tertiary);
  color: var(--text-primary);
  cursor: pointer;
}

.chat-library-confirm {
  border-color: transparent;
  background: var(--gradient-primary);
  color: white;
  font-weight: 700;
}

.chat-library-confirm:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.chat-library-error {
  margin: 12px 18px 0;
  padding: 10px 12px;
  border: 1px solid rgba(239, 68, 68, 0.35);
  border-radius: 8px;
  background: rgba(239, 68, 68, 0.12);
  color: #ef4444;
  font-size: 13px;
}

.chat-library-body {
  padding: 14px 18px;
  overflow-y: auto;
  display: grid;
  gap: 10px;
}

.chat-library-empty {
  padding: 36px;
  text-align: center;
  color: var(--text-muted);
}

.chat-library-doc {
  display: grid;
  grid-template-columns: 24px 28px minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 11px 12px;
  border: 1px solid var(--border-color);
  border-radius: 10px;
  background: var(--bg-tertiary);
  color: var(--text-primary);
  text-align: left;
  cursor: pointer;
}

.chat-library-doc:hover,
.chat-library-doc.selected {
  border-color: var(--accent-primary);
  background: rgba(99, 102, 241, 0.14);
}

.chat-library-check {
  width: 20px;
  height: 20px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  color: var(--accent-primary);
  font-weight: 800;
}

.chat-library-file-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chat-library-file-size {
  color: var(--text-muted);
  font-size: 12px;
}

.progress-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.progress-title {
  font-size: 14px;
  font-weight: 500;
  color: #374151;
}

.progress-msg {
  font-size: 12px;
  color: #9ca3af;
  flex: 1;
}

.progress-indicator {
  font-size: 12px;
  color: #9ca3af;
  animation: pulse 1s infinite;
}

.progress-done {
  font-size: 12px;
  color: #10b981;
  font-weight: 500;
}

.progress-bar-container {
  height: 8px;
  background: #e5e7eb;
  border-radius: 4px;
  overflow: hidden;
}

.progress-bar {
  height: 100%;
  background: linear-gradient(90deg, #10b981, #34d399);
  border-radius: 4px;
  transition: width 0.3s ease;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

/* ============ 实体提取表格预览 ============ */
.entity-preview {
  margin-top: 12px;
  border: 1px solid rgba(129, 140, 248, 0.18);
  border-radius: 12px;
  overflow: hidden;
  background: linear-gradient(180deg, rgba(15, 23, 42, 0.94) 0%, rgba(17, 24, 39, 0.98) 100%);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
}

.entity-preview-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 12px 14px;
  background: rgba(30, 41, 59, 0.72);
  border-bottom: 1px solid rgba(129, 140, 248, 0.12);
}

.entity-preview-title {
  font-size: 13px;
  font-weight: 600;
  color: #e5eefb;
  letter-spacing: 0;
}

.entity-preview-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  justify-content: flex-end;
}

.entity-action-btn {
  min-width: 68px;
  height: 28px;
  padding: 0 12px;
  background: linear-gradient(135deg, rgba(59, 130, 246, 0.22) 0%, rgba(14, 165, 233, 0.26) 100%);
  color: #dbeafe;
  border: 1px solid rgba(96, 165, 250, 0.28);
  border-radius: 8px;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  transition: background 0.2s ease, border-color 0.2s ease, transform 0.2s ease, color 0.2s ease;
}

.entity-action-btn:hover {
  background: linear-gradient(135deg, rgba(59, 130, 246, 0.34) 0%, rgba(14, 165, 233, 0.4) 100%);
  border-color: rgba(96, 165, 250, 0.46);
  color: #eff6ff;
  transform: translateY(-1px);
}

.entity-table-wrapper {
  overflow-x: auto;
  max-height: 400px;
  overflow-y: auto;
}

.entity-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
  background: transparent;
}

.entity-table thead {
  position: sticky;
  top: 0;
  z-index: 1;
}

.entity-table th {
  background: rgba(15, 23, 42, 0.94);
  color: #dbeafe;
  font-weight: 600;
  padding: 8px 10px;
  text-align: left;
  white-space: nowrap;
  border-bottom: 1px solid rgba(129, 140, 248, 0.18);
  border-right: 1px solid rgba(51, 65, 85, 0.72);
}

.entity-table td {
  padding: 7px 10px;
  border-bottom: 1px solid rgba(30, 41, 59, 0.92);
  border-right: 1px solid rgba(30, 41, 59, 0.64);
  color: #cbd5e1;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  background: rgba(15, 23, 42, 0.52);
}

.entity-table tbody tr:hover td {
  background: rgba(30, 41, 59, 0.96);
}

.entity-preview-more {
  padding: 10px 12px;
  text-align: center;
  font-size: 12px;
  color: #94a3b8;
  background: rgba(15, 23, 42, 0.72);
  border-top: 1px solid rgba(129, 140, 248, 0.1);
}

.table-fill-preview {
  border-color: rgba(45, 212, 191, 0.22);
  background: linear-gradient(180deg, rgba(7, 23, 32, 0.98) 0%, rgba(15, 23, 42, 0.96) 100%);
}

.table-fill-preview .entity-preview-header {
  background: linear-gradient(90deg, rgba(13, 148, 136, 0.18) 0%, rgba(15, 23, 42, 0.85) 70%);
  border-bottom: 1px solid rgba(45, 212, 191, 0.16);
}

.table-fill-preview .entity-preview-title {
  color: #ccfbf1;
}

.table-fill-preview .entity-table th {
  background: rgba(6, 78, 59, 0.22);
  color: #ccfbf1;
  border-bottom: 1px solid rgba(45, 212, 191, 0.18);
  border-right: 1px solid rgba(15, 23, 42, 0.66);
}

.table-fill-preview .entity-table td {
  border-bottom: 1px solid rgba(19, 78, 74, 0.42);
  border-right: 1px solid rgba(15, 23, 42, 0.5);
  background: rgba(8, 30, 36, 0.54);
  color: #d5f5f2;
}

.table-fill-preview .entity-table tbody tr:hover td {
  background: rgba(15, 118, 110, 0.14);
}

.table-fill-preview .entity-preview-more {
  background: rgba(6, 78, 59, 0.14);
  border-top: 1px solid rgba(45, 212, 191, 0.12);
  color: #99f6e4;
}

.table-fill-stats {
  font-size: 12px;
  color: #99f6e4;
  white-space: nowrap;
}

.table-fill-stats-inline {
  margin-left: 8px;
  font-weight: 500;
}

/* Loading 动画 */
.typing-indicator {
  display: inline-flex !important;
  align-items: center;
  gap: 4px;
  margin-top: 8px;
  padding: 4px 0;
}

.typing-dot {
  width: 6px;
  height: 6px;
  background: #6b7280;
  border-radius: 50%;
  animation: typing-bounce 1.4s infinite ease-in-out both;
}

.typing-dot:nth-child(1) {
  animation-delay: -0.32s;
}

.typing-dot:nth-child(2) {
  animation-delay: -0.16s;
}

@keyframes typing-bounce {
  0%, 80%, 100% {
    transform: scale(0);
    opacity: 0.4;
  }
  40% {
    transform: scale(1);
    opacity: 1;
  }
}
</style>
