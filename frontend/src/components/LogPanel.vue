<template>
  <div class="log-panel">
    <div class="log-toolbar">
      <el-switch v-model="follow" active-text="自动滚动" />
      <span class="muted" style="margin-left: 12px">
        {{ lines.length }} 条 · {{ connected ? "实时连接中" : "连接已断开，重连中..." }}
      </span>
      <div style="flex: 1"></div>
      <el-button size="small" :icon="Refresh" @click="clear">清空</el-button>
    </div>
    <div ref="boxEl" class="log-box" @click="follow = true">
      <template v-for="(item, i) in lines" :key="i">
        <div v-if="item.type === 'exit'" class="exit-line">{{ item.data }}</div>
        <div v-else class="log-line" :class="{ error: isError(item.data) }">{{ item.data }}</div>
      </template>
      <div v-if="lines.length === 0" class="empty">暂无日志</div>
    </div>
  </div>
</template>

<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { Refresh } from "@element-plus/icons-vue";
import { wsUrl } from "../api";

const props = defineProps({
  botId: { type: String, required: true },
});

const lines = ref([]);
const follow = ref(true);
const connected = ref(false);
const boxEl = ref(null);
let ws = null;
let retry = null;

function isError(text = "") {
  return /error|traceback|exception|失败|错误|warning|warn/i.test(text);
}

function scrollBottom() {
  if (follow.value && boxEl.value) {
    boxEl.value.scrollTop = boxEl.value.scrollHeight;
  }
}

function connect() {
  ws = new WebSocket(wsUrl(`/api/bots/${props.botId}/log/ws`));
  ws.onopen = () => {
    connected.value = true;
  };
  ws.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data);
      if (msg.type === "log" || msg.type === "exit") {
        lines.value.push(msg);
        if (lines.value.length > 2000) lines.value.splice(0, lines.value.length - 2000);
        nextTick(scrollBottom);
      }
    } catch {
      /* ignore */
    }
  };
  ws.onclose = () => {
    connected.value = false;
    retry = setTimeout(connect, 2500);
  };
  ws.onerror = () => ws.close();
}

function clear() {
  lines.value = [];
}

watch(
  () => props.botId,
  () => {
    if (ws) ws.close();
    if (retry) clearTimeout(retry);
    lines.value = [];
    connect();
  }
);

onMounted(connect);
onBeforeUnmount(() => {
  if (ws) ws.close();
  if (retry) clearTimeout(retry);
});
</script>

<style scoped>
.log-panel {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 210px);
}

.log-toolbar {
  display: flex;
  align-items: center;
  margin-bottom: 10px;
}

.log-box {
  flex: 1;
  overflow: auto;
  background: #1e1e1e;
  border-radius: 10px;
  padding: 14px;
  font-family: Consolas, "Courier New", monospace;
  font-size: 12.5px;
  color: #d4d4d4;
  cursor: text;
}

.log-line {
  white-space: pre-wrap;
  word-break: break-all;
  line-height: 1.65;
}

.log-line.error {
  color: #ff8f8f;
}

.exit-line {
  color: #e6a23c;
  margin-top: 4px;
  line-height: 1.6;
}

.empty {
  color: #666;
  text-align: center;
  margin-top: 40px;
}
</style>
