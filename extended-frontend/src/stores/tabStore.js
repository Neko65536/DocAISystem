import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useTabStore = defineStore('tab', () => {
  const currentTab = ref('library')

  const tabs = [
    { id: 'library', label: '文档库', icon: '📚' },
    { id: 'chat', label: '智能对话', icon: '💬' },
    { id: 'workflow', label: '工作流编排', icon: '🔄' }
  ]

  function switchTab(tabId) {
    currentTab.value = tabId
  }

  return {
    currentTab,
    tabs,
    switchTab
  }
})
