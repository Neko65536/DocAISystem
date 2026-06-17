import client from './client'

export default {
  // ==================== 空间管理 ====================

  /** 获取所有文档空间 */
  getSpaces() {
    return client.get('/library/spaces')
  },

  /** 创建文档空间 */
  createSpace(data) {
    return client.post('/library/spaces', data)
  },

  /** 更新文档空间 */
  updateSpace(spaceId, data) {
    return client.put(`/library/spaces/${spaceId}`, data)
  },

  /** 删除文档空间 */
  deleteSpace(spaceId) {
    return client.delete(`/library/spaces/${spaceId}`)
  },

  // ==================== 文档管理 ====================

  /** 获取空间下的所有文档 */
  getDocs(spaceId) {
    return client.get(`/library/spaces/${spaceId}/docs`)
  },

  /** 上传文档到指定空间 */
  uploadDoc(spaceId, file) {
    const formData = new FormData()
    formData.append('file', file)
    return client.post(`/library/spaces/${spaceId}/docs`, formData)
  },

  /** 删除单个文档 */
  deleteDoc(docId) {
    return client.delete(`/library/docs/${docId}`)
  },

  /** 批量删除文档 */
  deleteDocsBatch(docIds) {
    return client.post('/library/docs/delete-batch', { doc_ids: docIds })
  },

  /** 下载文档 */
  async downloadDocsBatch(docIds) {
    const token = localStorage.getItem('access_token') || ''
    const res = await fetch('/api/library/docs/download-batch', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ doc_ids: docIds }),
    })
    if (!res.ok) {
      let message = '批量下载失败'
      try {
        const data = await res.json()
        message = data?.detail || data?.error?.message || message
      } catch (_) {}
      throw new Error(message)
    }
    return res.blob()
  },

  getBatchDownloadUrl(docIds) {
    const token = localStorage.getItem('access_token') || ''
    const params = new URLSearchParams()
    params.set('doc_ids', docIds.join(','))
    if (token) params.set('token', token)
    return `/api/library/docs/download-batch?${params.toString()}`
  },

  async downloadDoc(docId, fileName) {
    const token = localStorage.getItem('access_token') || ''
    const url = `${import.meta.env.VITE_API_BASE_URL || ''}/api/library/docs/${docId}/download`
    const res = await fetch(url, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
    if (!res.ok) throw new Error('下载失败')
    const blob = await res.blob()
    const objectUrl = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = objectUrl
    a.download = fileName
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(objectUrl)
  },
}
