<template>
  <div class="term-panel">
    <div class="term-head">
      <div class="term-title">
        <span class="term-dot" :class="dotClass"></span>
        <span class="term-name">{{ title }}</span>
        <span class="term-status">{{ statusText }}</span>
      </div>
      <div class="term-actions">
        <el-button
          size="small"
          :icon="Refresh"
          :disabled="status === 'connecting'"
          @click="connect"
        >重新连接</el-button>
        <el-button size="small" :icon="Delete" @click="clearScreen">清屏</el-button>
        <el-button v-if="status === 'connected'" size="small" :icon="Close" @click="disconnect(true)">断开</el-button>
      </div>
    </div>

    <div ref="termEl" class="term-box" @mousedown="focusTerm" @contextmenu.prevent="pasteFromClipboard"></div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import { Close, Delete, Refresh } from "@element-plus/icons-vue";
import "@xterm/xterm/css/xterm.css";
import { wsUrl } from "../api";

const props = defineProps({
  /** bot = 机器人环境终端（需 botId）；system = 普通系统终端 */
  mode: { type: String, default: "bot" },
  botId: { type: String, default: "" },
  /** 终端区域高度 */
  height: { type: String, default: "calc(100vh - 215px)" },
});

const title = computed(() => (props.mode === "bot" ? "机器人环境终端" : "系统终端"));

const termEl = ref(null);
let term = null;
let fit = null;
let ws = null;
let resizeObserver = null;
let reconnectTimer = null;

// idle / connecting / connected / disconnected / ended
const status = ref("idle");
const statusText = computed(() => {
  switch (status.value) {
    case "connecting": return "连接中…";
    case "connected": return "已连接";
    case "ended": return "会话已结束，可点击「重新连接」";
    case "disconnected": return "已断开，可点击「重新连接」";
    default: return "未连接";
  }
});
const dotClass = computed(() => status.value);

function initTerm() {
  if (term) return;
  term = new Terminal({
    cursorBlink: true,
    fontSize: 13,
    fontFamily: "Consolas, 'Courier New', monospace",
    theme: {
      background: "#1e1e1e",
      foreground: "#d4d4d4",
      cursor: "#ea5252",
      selectionBackground: "rgba(234,82,82,0.35)",
    },
    scrollback: 5000,
  });
  fit = new FitAddon();
  term.loadAddon(fit);
  term.open(termEl.value);
  term.onData((data) => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "input", data }));
    }
  });
  // 容器尺寸变化（切换标签页、窗口缩放、侧栏折叠）都能自动适配
  resizeObserver = new ResizeObserver(() => fitTerm());
  resizeObserver.observe(termEl.value);
  setTimeout(() => {
    fitTerm();
    term.focus();
  }, 50);
}

function fitTerm() {
  if (!fit || !termEl.value) return;
  const { clientWidth, clientHeight } = termEl.value;
  if (clientWidth < 40 || clientHeight < 40) return;
  try {
    fit.fit();
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(
        JSON.stringify({ type: "resize", rows: term.rows, cols: term.cols })
      );
    }
  } catch {
    /* ignore */
  }
}

function focusTerm() {
  // 点击终端任意位置即聚焦，无需精确点到输入行
  setTimeout(() => term && term.focus(), 0);
}

async function pasteFromClipboard() {
  try {
    const text = await navigator.clipboard.readText();
    if (text && ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "input", data: text }));
    }
  } catch {
    /* 无剪贴板权限时忽略 */
  }
}

function connect() {
  initTerm();
  term.reset();
  disconnect();
  status.value = "connecting";

  const params = { rows: term.rows, cols: term.cols };
  if (props.mode === "bot") {
    params.type = "bot";
    params.bot_id = props.botId;
    term.writeln("\x1b[90m正在连接机器人环境终端（首次启动 shell 需要几秒）...\x1b[0m");
  } else {
    params.type = "system";
    term.writeln("\x1b[90m正在连接系统终端...\x1b[0m");
  }

  ws = new WebSocket(wsUrl("/api/terminal/ws", params));
  ws.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data);
      if (msg.type === "ready") {
        status.value = "connected";
      } else if (msg.type === "output") {
        term.write(msg.data);
      } else if (msg.type === "exit") {
        if (msg.data) {
          term.writeln(`\r\n\x1b[33m${msg.data}\x1b[0m`);
        }
        status.value = "ended";
      } else if (msg.type === "error") {
        term.writeln(`\r\n\x1b[31m${msg.data}\x1b[0m`);
      }
    } catch {
      /* ignore */
    }
  };
  ws.onclose = (ev) => {
    // 正常关闭（服务端主动结束）时已在 exit 分支提示
    if (status.value !== "ended") {
      status.value = "disconnected";
      term.writeln(`\r\n\x1b[90m[连接已断开${ev.reason ? `：${ev.reason}` : ""}]\x1b[0m`);
    }
    ws = null;
    scheduleAutoReconnect();
  };
  ws.onerror = () => {
    if (ws) ws.close();
  };
  setTimeout(fitTerm, 80);
}

/** 意外断开时 3 秒后自动重连一次，避免用户面对黑屏手动刷新 */
function scheduleAutoReconnect() {
  if (status.value !== "disconnected") return;
  if (reconnectTimer) clearTimeout(reconnectTimer);
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    if (status.value === "disconnected") connect();
  }, 3000);
}

function disconnect(manual = false) {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  if (ws) {
    ws.onclose = null;
    ws.onmessage = null;
    ws.onerror = null;
    ws.close();
    ws = null;
  }
  if (manual) status.value = "idle";
}

function clearScreen() {
  if (term) term.clear();
}

onMounted(() => {
  initTerm();
  connect();
});

onBeforeUnmount(() => {
  disconnect();
  if (resizeObserver) {
    resizeObserver.disconnect();
    resizeObserver = null;
  }
  if (term) {
    term.dispose();
    term = null;
    fit = null;
  }
});
</script>

<style scoped>
.term-panel {
  display: flex;
  flex-direction: column;
  height: v-bind("props.height");
}

.term-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.term-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  min-width: 0;
}

.term-name {
  font-weight: 600;
}

.term-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
  background: #909399;
}

.term-dot.connecting {
  background: #e6a23c;
  animation: term-pulse 1s infinite;
}

.term-dot.connected {
  background: #67c23a;
}

.term-dot.disconnected,
.term-dot.idle {
  background: #c0c4cc;
}

.term-dot.ended {
  background: #f56c6c;
}

.term-status {
  color: var(--nb-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.term-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.term-box {
  flex: 1;
  background: #1e1e1e;
  border-radius: 10px;
  padding: 10px;
  overflow: hidden;
  cursor: text;
}

@keyframes term-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}
</style>
