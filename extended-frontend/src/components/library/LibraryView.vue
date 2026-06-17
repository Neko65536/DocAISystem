<script setup>
import LibrarySidebar from './LibrarySidebar.vue'
import DocGrid from './DocGrid.vue'
import { useLibraryStore } from '../../stores/libraryStore'

const libraryStore = useLibraryStore()

function onSearch(event) {
  libraryStore.setSearchQuery(event.target.value)
}

function clearSearch() {
  libraryStore.setSearchQuery('')
}
</script>

<template>
  <div class="library-view">
    <!-- Toolbar -->
    <div class="library-toolbar">
      <div class="library-title">
        <span>📚</span>
        <span>文档库管理</span>
      </div>
      <div class="library-actions">
        <!-- 搜索框 -->
        <div class="search-box">
          <span class="search-icon">🔍</span>
          <input
            :value="libraryStore.searchQuery"
            class="search-input"
            placeholder="搜索文档..."
            @input="onSearch"
          />
          <button
            v-if="libraryStore.searchQuery"
            class="search-clear"
            type="button"
            @click="clearSearch"
          >
            ×
          </button>
        </div>

      </div>
    </div>

    <!-- Body: Sidebar + Content -->
    <div class="library-body">
      <LibrarySidebar />
      <DocGrid />
    </div>
  </div>
</template>

<style scoped>
.library-view {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--bg-primary);
}

/* Toolbar */
.library-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 32px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-color);
  flex-shrink: 0;
}

.library-title {
  font-size: 20px;
  font-weight: 700;
  display: flex;
  align-items: center;
  gap: 10px;
}

.library-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

/* Search Box */
.search-box {
  position: relative;
  display: flex;
  align-items: center;
}

.search-icon {
  position: absolute;
  left: 12px;
  font-size: 14px;
  color: var(--text-muted);
  pointer-events: none;
}

.search-input {
  padding: 9px 36px 9px 36px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  font-size: 13px;
  color: var(--text-primary);
  outline: none;
  width: 220px;
  transition: all 0.2s;
  font-family: inherit;
}

.search-input::placeholder {
  color: var(--text-muted);
}

.search-input:focus {
  border-color: var(--accent-primary);
  width: 280px;
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
}

.search-clear {
  position: absolute;
  right: 10px;
  background: transparent;
  border: none;
  cursor: pointer;
  color: var(--text-muted);
  font-size: 16px;
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  transition: all 0.2s;
}

.search-clear:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

/* Action Buttons */
.lib-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 18px;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
  cursor: pointer;
  transition: all 0.2s;
  font-family: inherit;
}

.lib-btn:hover {
  background: var(--bg-hover);
  border-color: var(--border-color-hover);
}

.lib-btn.primary {
  background: var(--gradient-primary);
  border: none;
  color: white;
}

.lib-btn.primary:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 16px rgba(99, 102, 241, 0.4);
}

/* Body */
.library-body {
  flex: 1;
  display: flex;
  overflow: hidden;
}
</style>
