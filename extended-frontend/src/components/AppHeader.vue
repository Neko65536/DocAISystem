<script setup>
import { useTabStore } from '../stores/tabStore'
import { useAuthStore } from '../stores/authStore'
import { useSessionStore } from '../stores/sessionStore'

const tabStore = useTabStore()
const authStore = useAuthStore()
const sessionStore = useSessionStore()

function handleTabClick(tabId) {
  tabStore.switchTab(tabId)
}

async function handleLogout() {
  await sessionStore.disconnectWebSocket()
  await authStore.logout()
}
</script>

<template>
  <header class="header">
    <div class="header-left">
      <!-- Logo -->
      <div class="logo">
        <div class="logo-icon" aria-hidden="true">
          <span class="logo-doc">
            <span></span>
            <span></span>
            <span></span>
          </span>
          <span class="logo-ai-dot dot-1"></span>
          <span class="logo-ai-dot dot-2"></span>
          <span class="logo-ai-dot dot-3"></span>
        </div>
        <span>文档智能系统</span>
      </div>

      <!-- Main Navigation -->
      <nav class="main-nav">
        <button
          v-for="tab in tabStore.tabs"
          :key="tab.id"
          class="nav-tab"
          :class="{ active: tabStore.currentTab === tab.id }"
          :data-tab="tab.id"
          @click="handleTabClick(tab.id)"
        >
          <span class="nav-tab-icon">{{ tab.icon }}</span>
          <span>{{ tab.label }}</span>
        </button>
      </nav>
    </div>

    <div class="header-right">
      <button class="header-btn" title="通知">
        🔔
      </button>
      <button class="header-btn" title="设置">
        ⚙️
      </button>

      <!-- 用户信息区域 -->
      <div class="header-user">
        <div class="user-info">
          <span class="user-name">{{ authStore.userDisplayName }}</span>
          <button class="logout-btn" @click="handleLogout" title="退出登录">
            退出
          </button>
        </div>
        <div class="user-avatar" :title="authStore.userDisplayName">
          {{ authStore.userAvatar }}
        </div>
      </div>
    </div>
  </header>
</template>
