<script setup>
import { ref, computed } from 'vue'
import { useWorkflowStore } from '../stores/workflowStore'

const props = defineProps({
  visible: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['close'])

const workflowStore = useWorkflowStore()

const isProcessing = ref(false)
const progress = ref(0)
const progressList = ref([])

const canStart = computed(() =>
  !isProcessing.value &&
  progress.value === 0 &&
  (workflowStore.selectedDocs.length > 0 || workflowStore.localFiles.length > 0)
)

const totalDocs = computed(() =>
  workflowStore.selectedDocs.length + workflowStore.localFiles.length
)

function closeModal() {
  if (!isProcessing.value) {
    emit('close')
  }
}

async function startProcess() {
  if (!canStart.value) return

  isProcessing.value = true
  progress.value = 0
  progressList.value = []

  const docs = [
    ...workflowStore.selectedDocs.map(d => ({ name: d.name, size: d.size })),
    ...workflowStore.localFiles.map(f => ({ name: f.name, size: f.size }))
  ]

  for (let i = 0; i < docs.length; i++) {
    const doc = docs[i]
    progressList.value.push({ name: doc.name, status: 'processing', icon: '⏳' })

    // 模拟处理（实际由后端执行）
    await new Promise(resolve => setTimeout(resolve, 600))

    progressList.value[i] = { name: doc.name, status: 'completed', icon: '✅' }
    progress.value = Math.round(((i + 1) / docs.length) * 100)
  }

  isProcessing.value = false
}

function getProgressText() {
  if (isProcessing.value) return '处理中...'
  if (progress.value === 100) return '处理完成！'
  return '准备就绪'
}

// 合并显示文档列表
const displayDocs = computed(() => {
  const list = [
    ...workflowStore.selectedDocs.map(d => ({ name: d.name, size: d.size })),
    ...workflowStore.localFiles.map(f => ({ name: f.name, size: _formatSize(f.size) }))
  ]
  return list
})

function _formatSize(bytes) {
  if (!bytes) return ''
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}
</script>

<template>
  <div class="modal-overlay" :class="{ active: visible }" @click.self="closeModal">
    <div class="modal">
      <!-- Header -->
      <div class="modal-header">
        <h2 class="modal-title">🔄 批量处理</h2>
        <button class="modal-close" @click="closeModal">×</button>
      </div>

      <!-- Body -->
      <div class="modal-body">
        <p class="modal-text">
          确定要使用 <strong>{{ workflowStore.workflowName }}</strong> 处理选中的文档吗？
        </p>

        <!-- Document List -->
        <div class="modal-docs" v-if="displayDocs.length > 0">
          <div
            v-for="(doc, i) in displayDocs"
            :key="i"
            class="modal-doc"
          >
            <span>📄</span>
            <span style="flex:1;">{{ doc.name }}</span>
            <span style="color: var(--text-muted); font-size: 12px;">{{ doc.size }}</span>
          </div>
          <div v-if="displayDocs.length === 0" class="modal-doc-empty">
            暂未选择任何文档，请先在配置面板中选择文档
          </div>
        </div>

        <div v-else class="modal-docs-empty">
          <div class="empty-icon">📭</div>
          <div class="empty-text">暂未选择文档</div>
          <div class="empty-hint">请先在配置面板中选择文档来源</div>
        </div>

        <!-- Progress -->
        <div class="batch-progress" v-if="isProcessing || progress > 0">
          <div class="progress-header">
            <span>{{ getProgressText() }}</span>
            <span>{{ progress }}%</span>
          </div>
          <div class="progress-bar">
            <div class="progress-fill" :style="{ width: progress + '%' }"></div>
          </div>
          <div class="progress-list">
            <div
              v-for="(item, index) in progressList"
              :key="index"
              class="progress-item"
              :class="item.status"
            >
              <span>{{ item.icon }}</span>
              <span>{{ item.name }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Footer -->
      <div class="modal-footer">
        <button class="modal-btn cancel" @click="closeModal">取消</button>
        <button
          class="modal-btn primary"
          @click="startProcess"
          :disabled="!canStart"
        >
          {{ isProcessing ? '处理中...' : `开始处理 (${totalDocs} 个文档)` }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.modal-docs-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 32px;
  background: var(--bg-tertiary);
  border-radius: var(--radius-md);
  border: 1px dashed var(--border-color);
}

.empty-icon {
  font-size: 40px;
  opacity: 0.4;
}

.empty-text {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-secondary);
}

.empty-hint {
  font-size: 13px;
  color: var(--text-muted);
}

.modal-doc-empty {
  padding: 16px;
  text-align: center;
  color: var(--text-muted);
  font-size: 14px;
}
</style>
