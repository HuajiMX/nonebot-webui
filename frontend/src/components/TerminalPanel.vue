<template>
  <div class="term-panel">
    <div class="term-head">
      <el-tabs v-model="active" @tab-change="onTabChange" class="term-tabs">
        <el-tab-pane label="机器人环境终端" name="bot" />
        <el-tab-pane label="协议端终端" name="protocol" />
        <el-tab-pane label="自定义终端" name="custom" />
      </el-tabs>

      <div class="term-actions">
        <el-button size="small" :icon="Refresh" @click="connect">重连</el-button>
        <el-button size="small" :icon="Close" @click="disconnect">断开</el-button>
      </div>
    </div>

    <div v-if="active === 'custom'" class="custom-bar">
      <el-input
        v-model="customCommand"
        placeholder="输入要执行的命令，例如：cmd /k 或 napcat"
        style="flex: 1"
        @keyup.enter="connect"
      />
      <el-button type="primary" @click="connect">连接</el-button>
    </div>

    <div v-if="active === 'protocol' && !hasProtocolCommand" class="protocol-hint">
      <el-alert
        type="warning"
        :closable="false"
        title="尚未配置协议端命令"
        description="请在「概览」页的 协议端终端命令 中填写协议端可执行文件或命令（例如 napcat / napcat.exe），保存后即可在此打开协议端终端。"
      />
    </div>

    <div ref="termEl" class="term-box"></div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import { Close, Refresh } from "@element-plus/icons-vue";
import "@xterm/xterm/css/xterm.css";
import { wsUrl } from "../api";

const props = defineProps({
  botId: { type: String, required: true },
  protocolCommand: { type: String, default: "" },
});

const active = ref("bot");
const customCommand = ref("");
const termEl = ref(null);
let term = null;
let fit = null;
let ws = null;
let disposed = false;

const hasProtocolCommand = computed(() => !!props.protocolCommand?.trim());

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
    scrollback: 3000,
  });
  fit = new FitAddon();
  term.loadAddon(fit);
  term.open(termEl.value);
  term.onData((data) => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "input", data }));
    }
  });
  setTimeout(fitTerm, 50);
  window.addEventListener("resize", onResize);
}

function fitTerm() {
  if (!fit) return;
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

function onResize() {
  setTimeout(fitTerm, 100);
}

function connect() {
  initTerm();
  term.reset();
  disconnect();

  const params = { bot_id: props.botId, rows: term.rows, cols: term.cols };
  if (active.value === "bot") {
    params.type = "bot";
  } else if (active.value === "protocol") {
    params.type = "protocol";
  } else {
    params.type = "custom";
    if (!customCommand.value.trim()) {
      term.writeln("\x1b[33m请输入要执行的命令\x1b[0m");
      return;
    }
    params.command = customCommand.value.trim();
  }

  term.writeln("\x1b[90m正在连接终端...\x1b[0m");
  ws = new WebSocket(wsUrl("/api/terminal/ws", params));
  ws.onopen = () => {
    term.writeln("");
  };
  ws.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data);
      if (msg.type === "output") {
        term.write(msg.data);
      } else if (msg.type === "exit") {
        term.writeln(`\r\n\x1b[33m${msg.data || "[会话已结束]"}\x1b[0m`);
      } else if (msg.type === "error") {
        term.writeln(`\r\n\x1b[31m${msg.data}\x1b[0m`);
      }
    } catch {
      /* ignore */
    }
  };
  ws.onclose = () => {
    term.writeln("\x1b[90m[连接已断开]\x1b[0m");
  };
  ws.onerror = () => ws.close();
  setTimeout(fitTerm, 80);
}

function disconnect() {
  if (ws) {
    ws.onclose = null;
    ws.close();
    ws = null;
  }
}

function onTabChange() {
  connect();
}

onMounted(() => {
  initTerm();
  connect();
});

onBeforeUnmount(() => {
  disposed = true;
  disconnect();
  window.removeEventListener("resize", onResize);
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
  height: calc(100vh - 210px);
}

.term-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.term-tabs {
  flex: 1;
}

.term-actions {
  display: flex;
  gap: 8px;
}

.custom-bar {
  display: flex;
  gap: 10px;
  margin-bottom: 10px;
}

.protocol-hint {
  margin-bottom: 10px;
}

.term-box {
  flex: 1;
  background: #1e1e1e;
  border-radius: 10px;
  padding: 10px;
  overflow: hidden;
}
</style>
