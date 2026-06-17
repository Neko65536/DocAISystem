<script setup>
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { useWorkflowStore } from '../../stores/workflowStore'

const workflowStore = useWorkflowStore()

const canvasAreaRef = ref(null)
const canvasInnerRef = ref(null)

const DROP_MIME = 'application/x-workflow-node'
const DEFAULT_NODE_X = 2250
const DEFAULT_NODE_Y = 2200

/** 是否允许从组件库拖入（放宽以兼容各浏览器 MIME 列表） */
function canAcceptToolboxDrag(e) {
  const types = [...(e.dataTransfer?.types || [])]
  return types.some(
    t =>
      t === DROP_MIME ||
      t === 'text/plain' ||
      t === 'Text'
  )
}

function parseDroppedToolboxItem(e) {
  let raw = ''
  try {
    raw = e.dataTransfer.getData(DROP_MIME)
  } catch (_) {
    /* ignore */
  }
  if (!raw) {
    try {
      raw = e.dataTransfer.getData('text/plain')
    } catch (_) {
      /* ignore */
    }
  }
  if (!raw || raw[0] !== '{') return null
  try {
    const o = JSON.parse(raw)
    if (o && typeof o.schemaKey === 'string' && o.title) return o
  } catch (_) {
    /* ignore */
  }
  return null
}

/** 将指针位置转为 canvas-inner 内坐标（与 node.x / node.y 一致） */
function pointerToInnerLocal(e) {
  const inner = canvasInnerRef.value
  if (!inner) return { x: 30, y: 160 }
  const rect = inner.getBoundingClientRect()
  return {
    x: e.clientX - rect.left,
    y: e.clientY - rect.top
  }
}

const dropZoneActive = ref(false)

function onCanvasDragEnter(e) {
  if (!canAcceptToolboxDrag(e)) return
  e.preventDefault()
  dropZoneActive.value = true
}

function onCanvasDragOver(e) {
  if (!canAcceptToolboxDrag(e)) return
  e.preventDefault()
  try {
    e.dataTransfer.dropEffect = 'copy'
  } catch (_) {
    /* ignore */
  }
}

function onCanvasDragLeave(e) {
  const el = canvasAreaRef.value
  if (el && e.relatedTarget && el.contains(e.relatedTarget)) return
  dropZoneActive.value = false
}

function onCanvasDrop(e) {
  dropZoneActive.value = false
  const item = parseDroppedToolboxItem(e)
  if (!item) return
  e.preventDefault()
  e.stopPropagation()
  const { x, y } = pointerToInnerLocal(e)
  const NODE_W = 200
  const NODE_H = 88
  workflowStore.addNodeAt(item, x - NODE_W / 2, y - NODE_H / 2)
}

// Transform-based pan state
const pan = ref({ x: 0, y: 0 })
const isPanning = ref(false)
const panStart = ref({ mouseX: 0, mouseY: 0, panX: 0, panY: 0 })
let hasCenteredInitialView = false

function centerInitialView() {
  const area = canvasAreaRef.value
  if (!area) return
  const rect = area.getBoundingClientRect()
  const targetX = workflowStore.canvasNodes[0]?.x ?? DEFAULT_NODE_X
  const targetY = workflowStore.canvasNodes[0]?.y ?? DEFAULT_NODE_Y
  pan.value = {
    x: Math.round(rect.width / 2 - targetX - 110),
    y: Math.round(rect.height / 2 - targetY - 60)
  }
}

onMounted(() => {
  nextTick(() => {
    centerInitialView()
    hasCenteredInitialView = true
  })
})

watch(
  () => workflowStore.currentWorkflowId,
  () => {
    hasCenteredInitialView = false
    nextTick(() => {
      centerInitialView()
      hasCenteredInitialView = true
    })
  }
)

watch(
  () => workflowStore.canvasNodes.length,
  (count, previous) => {
    if (!hasCenteredInitialView && count >= 0) {
      nextTick(() => {
        centerInitialView()
        hasCenteredInitialView = true
      })
      return
    }
    if (previous === 0 && count === 1) {
      nextTick(centerInitialView)
    }
  }
)

// Canvas style computed from pan transform
const canvasStyle = computed(() => ({
  transform: `translate(${pan.value.x}px, ${pan.value.y}px)`
}))

// Node drag state
const isDraggingNode = ref(false)
const dragNodeId = ref(null)
const dragStart = ref({ mouseX: 0, mouseY: 0, nodeX: 0, nodeY: 0 })
const pendingConnectionSource = ref(null)

function handleNodeClick(event, nodeId) {
  event.stopPropagation()
  workflowStore.selectNode(nodeId)
}

function handleNodeDelete(event, nodeId) {
  event.stopPropagation()
  workflowStore.deleteNode(nodeId)
}

function handleOutputPortClick(event, nodeId) {
  event.stopPropagation()
  pendingConnectionSource.value = nodeId
  workflowStore.selectNode(nodeId)
}

function handleInputPortClick(event, nodeId) {
  event.stopPropagation()
  if (!pendingConnectionSource.value) return
  workflowStore.addEdge(pendingConnectionSource.value, nodeId)
  pendingConnectionSource.value = null
}

function cancelPendingConnection(event) {
  event?.stopPropagation?.()
  pendingConnectionSource.value = null
}

function handleConnectFrom(event, nodeId) {
  handleOutputPortClick(event, nodeId)
}

function handleConnectTo(event, nodeId) {
  handleInputPortClick(event, nodeId)
}

function handleEdgeDelete(event, edgeId) {
  event.stopPropagation()
  workflowStore.deleteEdge(edgeId)
}

// Canvas pan
function onCanvasMouseDown(event) {
  if (event.button !== 0) return
  if (event.target.closest('.workflow-node')) return
  isPanning.value = true
  panStart.value = {
    mouseX: event.clientX,
    mouseY: event.clientY,
    panX: pan.value.x,
    panY: pan.value.y
  }
  event.preventDefault()
}

function onCanvasMouseMove(event) {
  if (isPanning.value) {
    const dx = event.clientX - panStart.value.mouseX
    const dy = event.clientY - panStart.value.mouseY
    pan.value = {
      x: panStart.value.panX + dx,
      y: panStart.value.panY + dy
    }
  } else if (isDraggingNode.value && dragNodeId.value) {
    const dx = event.clientX - dragStart.value.mouseX
    const dy = event.clientY - dragStart.value.mouseY
    workflowStore.updateNodePosition(dragNodeId.value, dragStart.value.nodeX + dx, dragStart.value.nodeY + dy)
  }
}

function onCanvasMouseUp() {
  isPanning.value = false
  isDraggingNode.value = false
  dragNodeId.value = null
}

// Node drag
function onNodeMouseDown(event, nodeId) {
  event.stopPropagation()
  event.preventDefault()
  const node = workflowStore.canvasNodes.find(n => n.id === nodeId)
  if (!node) return
  isDraggingNode.value = true
  dragNodeId.value = nodeId
  dragStart.value = {
    mouseX: event.clientX,
    mouseY: event.clientY,
    nodeX: node.x,
    nodeY: node.y
  }
}

function handleCanvasClick(event) {
  if (event.target.classList.contains('canvas-area') || event.target.classList.contains('canvas-inner')) {
    workflowStore.selectNode(null)
    pendingConnectionSource.value = null
  }
}

/** 与节点占位一致：连线从右侧端口到下一节点左侧，纵坐标取卡片中线附近 */
const NODE_CONN_W = 220
function nodeOutPoint(n) {
  return { x: n.x + NODE_CONN_W, y: n.y + 76 }
}
function nodeInPoint(n) {
  return { x: n.x, y: n.y + 76 }
}

/**
 * 连接路径：原先用 Q 且控制点在水平线上会退化成直线；
 * - 有明显纵向偏移时用正交「折线」；
 * - 其余用三次贝塞尔近似水平出站/到站，弧线更自然；
 * - 大行距时仍可走平滑弧线。
 */
function buildConnectionPath(p1, p2) {
  const x1 = p1.x
  const y1 = p1.y
  const x2 = p2.x
  const y2 = p2.y
  const dx = x2 - x1
  const dy = y2 - y1
  const adx = Math.abs(dx)
  const ady = Math.abs(dy)

  if (adx < 1 && ady < 1) {
    return `M ${x1} ${y1}`
  }

  // 近似同一行：画直线即可
  if (ady < 5) {
    return `M ${x1} ${y1} L ${x2} ${y2}`
  }

  // 纵向错位明显时用正交布线（可读「折弯」）
  const preferOrthogonal = ady >= 14 && ady >= adx * 0.22
  if (preferOrthogonal) {
    const midX = x1 + dx * 0.5
    return `M ${x1} ${y1} L ${midX} ${y1} L ${midX} ${y2} L ${x2} ${y2}`
  }

  // 顺滑弧线：两端沿水平方向伸出控制柄
  const tension = Math.min(160, Math.max(42, adx * 0.42))
  const sign = dx >= 0 ? 1 : -1
  const c1x = x1 + sign * tension
  const c2x = x2 - sign * tension
  return `M ${x1} ${y1} C ${c1x} ${y1} ${c2x} ${y2} ${x2} ${y2}`
}

const connPaths = computed(() => {
  const nodes = workflowStore.canvasNodes
  const nodeById = new Map(nodes.map(n => [n.id, n]))
  return (workflowStore.canvasEdges || []).map(edge => {
    const fromNode = nodeById.get(edge.source)
    const toNode = nodeById.get(edge.target)
    if (!fromNode || !toNode) return null
    const pOut = nodeOutPoint(fromNode)
    const pIn = nodeInPoint(toNode)
    return {
      d: buildConnectionPath(pOut, pIn),
      key: edge.id || `conn-${edge.source}-${edge.target}`,
      id: edge.id,
      fromId: fromNode.id,
      fromTitle: fromNode.title,
      toId: toNode.id,
      toTitle: toNode.title
    }
  }).filter(Boolean)
})

const pendingConnectionTitle = computed(() => {
  if (!pendingConnectionSource.value) return ''
  return workflowStore.canvasNodes.find(n => n.id === pendingConnectionSource.value)?.title || ''
})

const MINI_GRAPH_W = 720
const MINI_GRAPH_H = 118

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max)
}

function buildMiniPath(p1, p2) {
  const dx = p2.x - p1.x
  const tension = clamp(Math.abs(dx) * 0.45, 28, 90)
  const sign = dx >= 0 ? 1 : -1
  return `M ${p1.x} ${p1.y} C ${p1.x + sign * tension} ${p1.y} ${p2.x - sign * tension} ${p2.y} ${p2.x} ${p2.y}`
}

const miniGraph = computed(() => {
  const nodes = workflowStore.canvasNodes || []
  if (!nodes.length) return { width: MINI_GRAPH_W, height: MINI_GRAPH_H, nodes: [], edges: [] }

  const nodeIds = nodes.map(node => node.id)
  const orderIndex = new Map(nodeIds.map((id, idx) => [id, idx]))
  const outgoing = new Map(nodeIds.map(id => [id, []]))
  const indegree = new Map(nodeIds.map(id => [id, 0]))
  ;(workflowStore.canvasEdges || []).forEach(edge => {
    if (!outgoing.has(edge.source) || !indegree.has(edge.target)) return
    outgoing.get(edge.source).push(edge.target)
    indegree.set(edge.target, indegree.get(edge.target) + 1)
  })

  const level = new Map(nodeIds.map(id => [id, 0]))
  const ready = nodeIds
    .filter(id => indegree.get(id) === 0)
    .sort((a, b) => orderIndex.get(a) - orderIndex.get(b))
  const queue = [...ready]
  const indegreeWork = new Map(indegree)
  while (queue.length) {
    const current = queue.shift()
    ;(outgoing.get(current) || []).forEach(target => {
      level.set(target, Math.max(level.get(target) || 0, (level.get(current) || 0) + 1))
      indegreeWork.set(target, indegreeWork.get(target) - 1)
      if (indegreeWork.get(target) === 0) {
        queue.push(target)
        queue.sort((a, b) => orderIndex.get(a) - orderIndex.get(b))
      }
    })
  }

  const maxLevel = Math.max(...Array.from(level.values()), 0)
  const levels = new Map()
  nodes.forEach((node, idx) => {
    const nodeLevel = level.get(node.id) || 0
    if (!levels.has(nodeLevel)) levels.set(nodeLevel, [])
    levels.get(nodeLevel).push({ node, idx })
  })
  levels.forEach(items => items.sort((a, b) => Number(a.node.y || 0) - Number(b.node.y || 0) || a.idx - b.idx))

  const padX = 72
  const padY = 24
  const usableW = MINI_GRAPH_W - padX * 2
  const usableH = MINI_GRAPH_H - padY * 2
  const miniNodes = nodes.map((node, idx) => {
    const nodeLevel = level.get(node.id) || 0
    const items = levels.get(nodeLevel) || []
    const rowIndex = Math.max(items.findIndex(item => item.node.id === node.id), 0)
    const rowCount = Math.max(items.length, 1)
    return {
      id: node.id,
      title: node.title,
      index: idx + 1,
      x: maxLevel === 0 ? MINI_GRAPH_W / 2 : padX + (nodeLevel / maxLevel) * usableW,
      y: rowCount === 1 ? MINI_GRAPH_H / 2 : padY + (rowIndex / (rowCount - 1)) * usableH,
      status: getNodeRunState(node.id),
      selected: workflowStore.selectedNodeId === node.id,
    }
  })
  const byId = new Map(miniNodes.map(node => [node.id, node]))
  const miniEdges = (workflowStore.canvasEdges || [])
    .map(edge => {
      const from = byId.get(edge.source)
      const to = byId.get(edge.target)
      if (!from || !to) return null
      return {
        id: edge.id || `mini-${edge.source}-${edge.target}`,
        d: buildMiniPath(from, to),
        selected: workflowStore.selectedNodeId === from.id || workflowStore.selectedNodeId === to.id,
      }
    })
    .filter(Boolean)

  return { width: MINI_GRAPH_W, height: MINI_GRAPH_H, nodes: miniNodes, edges: miniEdges }
})

const nodeProgressById = computed(() => {
  const map = {}
  ;(workflowStore.nodeProgress || []).forEach(item => {
    if (item?.id) map[item.id] = item
  })
  return map
})

function getNodeRunState(nodeId) {
  return nodeProgressById.value[nodeId]?.status || 'idle'
}

// 当前选中节点在数组中的索引
const selectedIndex = computed(() => {
  if (!workflowStore.selectedNodeId) return -1
  return workflowStore.canvasNodes.findIndex(n => n.id === workflowStore.selectedNodeId)
})
</script>

<template>
  <div class="workflow-canvas">
    <!-- Canvas Area -->
    <div
      ref="canvasAreaRef"
      class="canvas-area"
      :class="{ 'is-panning': isPanning, 'canvas-area--drop-target': dropZoneActive }"
      @click="handleCanvasClick"
      @mousedown="onCanvasMouseDown"
      @mousemove="onCanvasMouseMove"
      @mouseup="onCanvasMouseUp"
      @mouseleave="onCanvasMouseUp"
      @dragenter="onCanvasDragEnter"
      @dragover="onCanvasDragOver"
      @dragleave="onCanvasDragLeave"
      @drop="onCanvasDrop"
    >
      <!-- Mini graph overview (outside transform, stays fixed at top) -->
      <div class="canvas-step-bar">
        <svg
          class="mini-graph-svg"
          :viewBox="`0 0 ${miniGraph.width} ${miniGraph.height}`"
          preserveAspectRatio="none"
        >
          <path
            v-for="edge in miniGraph.edges"
            :key="edge.id"
            :d="edge.d"
            class="mini-graph-edge"
            :class="{ selected: edge.selected }"
          />
        </svg>
        <button
          v-for="node in miniGraph.nodes"
          :key="'mini-node-' + node.id"
          type="button"
          class="mini-graph-node"
          :class="{
            selected: node.selected,
            ['run-' + node.status]: true
          }"
          :style="{ left: node.x + 'px', top: node.y + 'px' }"
          @click.stop="workflowStore.selectNode(node.id)"
        >
          <span class="mini-graph-num">{{ node.index }}</span>
          <span class="mini-graph-name">{{ node.title }}</span>
        </button>
        <template v-if="!miniGraph.nodes.length">
          <div
            class="step-item"
          >
            <div class="step-name">暂无节点</div>
          </div>
        </template>
      </div>

      <div
        v-if="pendingConnectionSource || workflowStore.canvasEdges.length"
        class="canvas-link-toolbar"
        @mousedown.stop
        @click.stop
      >
        <template v-if="pendingConnectionSource">
          <span class="link-toolbar-dot"></span>
          <span>正在从「{{ pendingConnectionTitle }}」创建连线，点击目标节点的“接入”</span>
          <button type="button" class="link-toolbar-btn" @click="cancelPendingConnection($event)">取消</button>
        </template>
        <template v-else>
          <span class="link-toolbar-dot idle"></span>
          <span>当前{{ workflowStore.canvasEdges.length }}条连线，双击连线可删除</span>
        </template>
      </div>

      <!-- Inner transformable container (nodes + connections move) -->
      <div ref="canvasInnerRef" class="canvas-inner" :style="canvasStyle">
        <!-- SVG Connections -->
        <svg class="connections-svg">
          <path
            v-for="cp in connPaths"
            :key="'hit-' + cp.key"
            :d="cp.d"
            class="conn-hit-path"
            @dblclick="handleEdgeDelete($event, cp.id)"
          />
          <path
            v-for="cp in connPaths"
            :key="cp.key"
            :d="cp.d"
            class="conn-path"
            :class="{
              'conn-selected':
                workflowStore.selectedNodeId === cp.fromId ||
                workflowStore.selectedNodeId === cp.toId
            }"
            @dblclick="handleEdgeDelete($event, cp.id)"
          />
        </svg>

        <!-- Nodes -->
        <div
          v-for="(node, i) in workflowStore.canvasNodes"
          :key="node.id"
          class="workflow-node"
          :class="{ selected: workflowStore.selectedNodeId === node.id, ['type-' + node.type]: true, ['run-' + getNodeRunState(node.id)]: true }"
          :style="{ left: node.x + 'px', top: node.y + 'px' }"
          @click="handleNodeClick($event, node.id)"
          @mousedown="onNodeMouseDown($event, node.id)"
        >
          <div class="node-selected-badge">当前选中</div>
          <div
            class="node-port input-port"
            title="连接到此节点"
            @mousedown.stop
            @click="handleInputPortClick($event, node.id)"
          ></div>
          <div class="node-header">
            <div class="node-icon" :class="node.type + '-icon'">{{ node.icon }}</div>
            <span class="node-title">{{ node.title }}</span>
            <span class="node-step-tag">Step {{ i + 1 }}</span>
            <div
              v-if="workflowStore.canvasNodes.length > 1"
              class="node-seq-actions"
              @mousedown.stop
              @click.stop
            >
              <button
                type="button"
                class="node-seq-btn"
                :disabled="i === 0"
                title="前移（更早执行）"
                @click="workflowStore.moveNodeEarlier(node.id)"
              >◀</button>
              <button
                type="button"
                class="node-seq-btn"
                :disabled="i >= workflowStore.canvasNodes.length - 1"
                title="后移（更晚执行）"
                @click="workflowStore.moveNodeLater(node.id)"
              >▶</button>
            </div>
            <button
              class="node-delete-btn"
              title="删除节点"
              @click.stop="handleNodeDelete($event, node.id)"
            >×</button>
          </div>
          <div class="node-body">{{ node.body }}</div>
          <div
            class="node-link-actions"
            @mousedown.stop
            @click.stop
          >
            <button
              type="button"
              class="node-link-btn"
              :class="{ active: pendingConnectionSource === node.id }"
              @click="handleConnectFrom($event, node.id)"
            >从此连线</button>
            <button
              v-if="pendingConnectionSource && pendingConnectionSource !== node.id"
              type="button"
              class="node-link-btn primary"
              @click="handleConnectTo($event, node.id)"
            >接入</button>
            <button
              v-else-if="pendingConnectionSource === node.id"
              type="button"
              class="node-link-btn"
              @click="cancelPendingConnection($event)"
            >取消</button>
          </div>
          <div v-if="getNodeRunState(node.id) !== 'idle'" class="node-run-status">
            <span class="node-run-dot"></span>
            <span>{{ nodeProgressById[node.id]?.message || nodeProgressById[node.id]?.status }}</span>
          </div>
          <div
            class="node-port output-port"
            :class="{ 'is-connecting': pendingConnectionSource === node.id }"
            title="从此节点创建连线"
            @mousedown.stop
            @click="handleOutputPortClick($event, node.id)"
          ></div>
        </div>
      </div>
    </div>
  </div>
</template>
