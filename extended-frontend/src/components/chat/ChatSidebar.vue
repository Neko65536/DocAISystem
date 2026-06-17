<script setup>
import { ref, computed } from 'vue'
import { useSessionStore } from '../../stores/sessionStore'

const props = defineProps({
  collapsed: {
    type: Boolean,
    default: false
  }
})

const sessionStore = useSessionStore()

const editingSessionId = ref(null)
const editingTitle = ref('')
const savingTitle = ref(false)
const searchQuery = ref('')

const sortedSessions = computed(() => {
  const sorted = [...sessionStore.sessions].sort((a, b) => {
    const dateA = new Date(a.updated_at || a.created_at)
    const dateB = new Date(b.updated_at || b.created_at)
    const timeA = isNaN(dateA.getTime()) ? 0 : dateA.getTime()
    const timeB = isNaN(dateB.getTime()) ? 0 : dateB.getTime()
    return timeB - timeA
  })
  if (!searchQuery.value) return sorted
  const query = searchQuery.value.toLowerCase()
  return sorted.filter(s => (s.title || '').toLowerCase().includes(query))
})

const groupedSessions = computed(() => {
  const groups = {
    '今天': [],
    '昨天': [],
    '本周': [],
    '较早': []
  }
  const now = new Date()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const yesterday = new Date(today - 86400000)
  const weekAgo = new Date(today - 7 * 86400000)

  sortedSessions.value.forEach(session => {
    const date = new Date(session.updated_at || session.created_at)
    if (date >= today) {
      groups['今天'].push(session)
    } else if (date >= yesterday) {
      groups['昨天'].push(session)
    } else if (date >= weekAgo) {
      groups['本周'].push(session)
    } else {
      groups['较早'].push(session)
    }
  })
  return groups
})

function handleSearch(e) {
  searchQuery.value = e.target.value
}

function startRename(session) {
  editingSessionId.value = session.session_id
  editingTitle.value = session.title || ''
}

function cancelRename() {
  editingSessionId.value = null
  editingTitle.value = ''
}

async function saveRename(session) {
  if (savingTitle.value) return
  const title = (editingTitle.value || '').trim()
  if (!title) {
    cancelRename()
    return
  }
  if (title === (session.title || '')) {
    cancelRename()
    return
  }
  savingTitle.value = true
  try {
    await sessionStore.updateSessionTitle(session.session_id, title)
  } finally {
    savingTitle.value = false
    cancelRename()
  }
}
</script>

<template>
  <aside class="chat-sidebar" :class="{ collapsed: props.collapsed }">
    <!-- 收起按钮 - 在侧边栏内部 -->
    <button v-if="!props.collapsed" class="sidebar-toggle" @click="sessionStore.toggleSidebar" title="收起侧边栏">
      ←
    </button>

    <!-- Header -->
    <div class="chat-sidebar-header">
      <button class="new-session-btn" @click="sessionStore.createSession">
        <span>+</span>
        <span>新建会话</span>
      </button>
    </div>

    <!-- Search -->
    <div class="chat-search">
      <input
        type="text"
        placeholder="搜索会话..."
        :value="searchQuery"
        @input="handleSearch"
      />
    </div>

    <!-- Session List -->
    <div class="session-list">
      <!-- Loading state -->
      <div
        v-if="sessionStore.isInitializing && sessionStore.sessions.length === 0"
        class="session-empty"
      >
        加载会话...
      </div>

      <template v-for="(sessions, group) in groupedSessions" :key="group">
        <div v-if="sessions.length > 0" class="session-group">
          <div class="session-group-title">{{ group }}</div>
          <div
            v-for="session in sessions"
            :key="session.session_id"
            class="session-item"
            :class="{ active: sessionStore.currentSessionId === session.session_id }"
            @click="sessionStore.selectSession(session.session_id)"
          >
            <span class="session-icon">💬</span>
            <div class="session-info">
              <!-- 编辑模式 -->
              <div v-if="editingSessionId === session.session_id" class="session-edit" @click.stop>
                <input
                  v-model="editingTitle"
                  type="text"
                  class="session-edit-input"
                  :disabled="savingTitle"
                  @keydown.enter.prevent="saveRename(session)"
                  @keydown.esc.prevent="cancelRename"
                  @blur="saveRename(session)"
                  autofocus
                />
              </div>
              <!-- 显示模式 -->
              <template v-else>
                <span class="session-name">{{ session.title }}</span>
                <span class="session-time">{{ sessionStore.formatTime(session.updated_at) }}</span>
              </template>
            </div>
            <!-- 操作按钮 -->
            <div class="session-actions" @click.stop>
              <button
                class="session-action-btn"
                title="重命名"
                @click="startRename(session)"
              >
                ✏️
              </button>
              <button
                class="session-action-btn delete"
                title="删除会话"
                @click="sessionStore.deleteSession(session.session_id)"
              >
                🗑️
              </button>
            </div>
          </div>
        </div>
      </template>

      <!-- Empty state -->
      <div v-if="sortedSessions.length === 0" class="session-empty">
        暂无会话，点击上方按钮创建
      </div>
    </div>
  </aside>
</template>
