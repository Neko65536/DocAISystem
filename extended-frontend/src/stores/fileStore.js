import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

/**
 * 聊天「文件上传区」纯属本地缓冲区：只做选中/预览，与后端会话文件列表无关。
 * 仅在用户发送消息且需要携带附件时，由 sessionStore 临时上传到当前会话。
 */
export const useFileStore = defineStore('file', () => {
  const currentFileType = ref('data')
  const filesPanelCollapsed = ref(true)
  const searchQuery = ref('')
  const isUploading = ref(false)

  const tempFiles = ref({
    data: [],
    template: []
  })

  const currentFiles = computed(() => tempFiles.value[currentFileType.value])

  const hasDataFiles = computed(() => tempFiles.value.data.length > 0)
  const hasTemplateFiles = computed(() => tempFiles.value.template.length > 0)
  const hasFiles = computed(() => hasDataFiles.value || hasTemplateFiles.value)

  const dataCount = computed(() => tempFiles.value.data.length)
  const templateCount = computed(() => tempFiles.value.template.length)

  function switchFileType(type) {
    currentFileType.value = type
  }

  function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B'
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
  }

  async function addFile(type, file) {
    const tempId = 'temp_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9)

    const fileUrl = URL.createObjectURL(file)

    const fileInfo = {
      id: tempId,
      file_name: file.name,
      file_size: file.size,
      file_type: type,
      file_url: fileUrl,
      original_file: file,
      is_selected: true,
      created_at: new Date().toISOString(),
    }

    tempFiles.value[type].push(fileInfo)
  }

  function addReferencedFiles(type, docs = []) {
    const target = tempFiles.value[type] || tempFiles.value.data
    docs.forEach(doc => {
      const storageKey = doc.storage_key || doc.file_path || doc.path || ''
      if (!storageKey) return
      const id = `library_${doc.id || storageKey}`
      const exists = target.some(f =>
        f.id === id ||
        f.storage_key === storageKey ||
        (f.file_name === (doc.name || doc.file_name) && f.file_size === (doc.size_bytes || doc.file_size))
      )
      if (exists) return
      target.push({
        id,
        file_name: doc.name || doc.file_name || 'library-file',
        file_size: doc.size_bytes || doc.file_size || 0,
        file_type: type,
        file_path: storageKey,
        storage_key: storageKey,
        source: 'library',
        is_selected: true,
        created_at: doc.created_at || new Date().toISOString(),
      })
    })
  }

  function setSessionFiles(dataFiles = [], templateFiles = [], { preservePending = false } = {}) {
    const normalize = (file, type) => ({
      id: file.id ?? file.file_id ?? `${type}_${file.storage_key || file.file_path || file.file_name}`,
      file_name: file.file_name || file.name || 'session-file',
      file_size: file.file_size || file.size_bytes || 0,
      file_type: type,
      file_path: file.file_path || file.storage_key || '',
      storage_key: file.storage_key || file.file_path || '',
      source: file.source || 'session',
      is_selected: file.is_selected !== false,
      created_at: file.created_at || new Date().toISOString(),
    })

    const pendingData = preservePending ? tempFiles.value.data.filter(f => f.original_file) : []
    const pendingTemplates = preservePending ? tempFiles.value.template.filter(f => f.original_file) : []
    tempFiles.value.data = [...pendingData, ...dataFiles.map(f => normalize(f, 'data'))]
    tempFiles.value.template = [...pendingTemplates, ...templateFiles.map(f => normalize(f, 'template'))]
  }

  async function removeFile(id, type) {
    const index = tempFiles.value[type].findIndex(f => f.id === id)
    if (index > -1) {
      const fileInfo = tempFiles.value[type][index]
      const url = fileInfo?.file_url
      if (url && String(url).startsWith('blob:')) {
        try {
          URL.revokeObjectURL(url)
        } catch (_) {}
      }
      tempFiles.value[type].splice(index, 1)
    }
    // 不从缓冲区调用后端删除；服务端副本仅在发送消息时按需创建
  }

  function toggleFileSelection(id, type, isSelected) {
    const tempIndex = tempFiles.value[type].findIndex(f => f.id === id)
    if (tempIndex > -1) {
      tempFiles.value[type][tempIndex].is_selected = isSelected
    }
  }

  function getFileIcon(filename) {
    const ext = filename.split('.').pop().toLowerCase()
    if (['pdf'].includes(ext)) return '📄'
    if (['doc', 'docx'].includes(ext)) return '📝'
    if (['xls', 'xlsx', 'csv'].includes(ext)) return '📊'
    if (['png', 'jpg', 'jpeg'].includes(ext)) return '🖼️'
    return '📎'
  }

  function getFileTypeLabel(filename) {
    const ext = filename.split('.').pop().toLowerCase()
    const map = {
      pdf: 'PDF',
      doc: 'DOC',
      docx: 'DOCX',
      xls: 'XLS',
      xlsx: 'XLSX',
      txt: 'TXT',
      md: 'MD',
      csv: 'CSV',
      png: 'PNG',
      jpg: 'JPG',
      jpeg: 'JPEG',
    }
    return map[ext] || ext.toUpperCase()
  }

  function toggleFilesPanel() {
    filesPanelCollapsed.value = !filesPanelCollapsed.value
  }

  return {
    currentFileType,
    filesPanelCollapsed,
    searchQuery,
    tempFiles,
    currentFiles,
    hasDataFiles,
    hasTemplateFiles,
    hasFiles,
    dataCount,
    templateCount,
    isUploading,
    switchFileType,
    addFile,
    addReferencedFiles,
    setSessionFiles,
    removeFile,
    toggleFileSelection,
    toggleFilesPanel,
    getFileIcon,
    getFileTypeLabel,
    setSearchQuery: (q) => { searchQuery.value = q }
  }
})
