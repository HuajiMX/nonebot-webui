<template>
  <div class="page" v-loading="loading">
    <div class="detail-head">
      <div>
        <el-button :icon="ArrowLeft" text @click="$router.push('/bots')">返回</el-button>
        <span class="detail-title">{{ bot.name || "-" }}</span>
        <StatusTag :status="bot.status" />
      </div>
      <div class="detail-actions">
        <el-button
          :type="bot.status === 'running' ? 'warning' : 'success'"
          :loading="acting"
          @click="toggle"
        >
          {{ bot.status === "running" ? "暂停" : "启动" }}
        </el-button>
        <el-button type="primary" :loading="acting" @click="restart">重启</el-button>
      </div>
    </div>

    <el-tabs v-model="tab" class="detail-tabs">
      <el-tab-pane label="概览" name="overview">
        <div class="overview-grid">
          <div class="card">
            <h3 class="block-title">基本信息</h3>
            <div class="kv">
              <div class="kv-row"><span>名称</span><b>{{ bot.name }}</b></div>
              <div class="kv-row"><span>协议 / 适配器</span><b>{{ bot.adapter_label }}</b></div>
              <div class="kv-row"><span>目录</span><b class="path">{{ bot.directory }}</b></div>
              <div class="kv-row"><span>监听</span><b>{{ bot.host }}:{{ bot.port }}</b></div>
              <div class="kv-row"><span>虚拟环境</span><b class="path">{{ bot.venv || "-" }}</b></div>
              <div class="kv-row"><span>Python</span><b class="path">{{ bot.python || "-" }}</b></div>
              <div class="kv-row"><span>插件目录</span><b class="path">{{ bot.plugin_dir }}</b></div>
              <div class="kv-row"><span>创建时间</span><b>{{ fmtTime(bot.created_at) }}</b></div>
              <div class="kv-row"><span>管理模式</span><b>{{ bot.managed ? "WebUI 托管（完整支持插件启停）" : "现有项目（仅基础管理）" }}</b></div>
            </div>
          </div>

          <div class="card">
            <h3 class="block-title">编辑信息</h3>
            <el-form :model="editForm" label-width="130px">
              <el-form-item label="名称">
                <el-input v-model="editForm.name" />
              </el-form-item>
              <el-form-item label="监听地址">
                <el-input v-model="editForm.host" />
              </el-form-item>
              <el-form-item label="监听端口">
                <el-input-number v-model="editForm.port" :min="1" :max="65535" />
              </el-form-item>
              <el-form-item label="插件目录">
                <el-input v-model="editForm.plugin_dir" />
              </el-form-item>
              <el-form-item label="协议端终端命令">
                <el-input v-model="editForm.terminal_command" placeholder="例如 napcat / D:\napcat\napcat.exe" />
                <div class="muted">用于「终端」页的协议端终端</div>
              </el-form-item>
              <el-form-item label="自动启动">
                <el-switch v-model="editForm.auto_start" />
                <div class="muted auto-start-hint">勾选后，WebUI 每次启动都会自动拉起该机器人</div>
              </el-form-item>
              <el-form-item>
                <el-button type="primary" :loading="saving" @click="saveEdit">保存修改</el-button>
              </el-form-item>
            </el-form>
          </div>

          <div class="card danger-card">
            <h3 class="block-title danger-title">危险操作</h3>
            <p class="muted">删除机器人会停止其进程并移除注册信息。可选择同时删除机器人目录（不可恢复）。</p>
            <el-checkbox v-model="removeDir">同时删除机器人目录</el-checkbox>
            <div style="margin-top: 12px">
              <el-button type="danger" :loading="deleting" @click="confirmDelete">删除机器人</el-button>
            </div>
          </div>
        </div>
      </el-tab-pane>

      <el-tab-pane label="运行日志" name="logs">
        <LogPanel v-if="tab === 'logs'" :bot-id="id" />
      </el-tab-pane>

      <el-tab-pane label="插件管理" name="plugins">
        <PluginPanel v-if="tab === 'plugins'" :bot-id="id" />
      </el-tab-pane>

      <el-tab-pane label="终端" name="terminal">
        <TerminalPanel
          v-if="tab === 'terminal'"
          :bot-id="id"
          :protocol-command="bot.terminal_command"
        />
      </el-tab-pane>

      <el-tab-pane label="配置文件" name="config">
        <div class="card">
          <div class="config-head">
            <h3 class="block-title" style="margin: 0">.env 配置</h3>
            <el-button type="primary" :loading="savingEnv" @click="saveEnv">保存</el-button>
          </div>
          <p class="muted">修改后需重启机器人生效。可参考 NoneBot2 配置文档（HOST / PORT / DRIVER / SUPERUSERS 等）。</p>
          <el-input
            v-model="envContent"
            type="textarea"
            :rows="18"
            class="env-editor"
            spellcheck="false"
          />
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { ArrowLeft } from "@element-plus/icons-vue";
import api from "../api";
import StatusTag from "../components/StatusTag.vue";
import LogPanel from "../components/LogPanel.vue";
import PluginPanel from "../components/PluginPanel.vue";
import TerminalPanel from "../components/TerminalPanel.vue";

const props = defineProps({
  id: { type: String, required: true },
});
const router = useRouter();

const bot = ref({});
const tab = ref("overview");
const loading = ref(false);
const acting = ref(false);
const saving = ref(false);
const deleting = ref(false);
const removeDir = ref(false);
const savingEnv = ref(false);
const envContent = ref("");

const editForm = reactive({
  name: "",
  host: "",
  port: 8080,
  plugin_dir: "src/plugins",
  terminal_command: "",
  auto_start: false,
});

let pollTimer = null;

async function load() {
  loading.value = true;
  try {
    bot.value = await api.get(`/bots/${props.id}`);
    Object.assign(editForm, {
      name: bot.value.name,
      host: bot.value.host,
      port: bot.value.port,
      plugin_dir: bot.value.plugin_dir,
      terminal_command: bot.value.terminal_command || "",
      auto_start: bot.value.auto_start,
    });
  } finally {
    loading.value = false;
  }
}

function fmtTime(iso) {
  if (!iso) return "-";
  return new Date(iso).toLocaleString("zh-CN", { hour12: false });
}

async function toggle() {
  acting.value = true;
  try {
    if (bot.value.status === "running") {
      await api.post(`/bots/${props.id}/stop`);
      ElMessage.success("已暂停");
    } else {
      await api.post(`/bots/${props.id}/start`);
      ElMessage.success("已启动");
    }
    load();
  } finally {
    acting.value = false;
  }
}

async function restart() {
  acting.value = true;
  try {
    await api.post(`/bots/${props.id}/restart`);
    ElMessage.success("已重启");
    load();
  } finally {
    acting.value = false;
  }
}

async function saveEdit() {
  saving.value = true;
  try {
    const data = await api.patch(`/bots/${props.id}`, { ...editForm });
    bot.value = data;
    ElMessage.success("已保存");
  } finally {
    saving.value = false;
  }
}

async function confirmDelete() {
  try {
    await ElMessageBox.confirm(
      `确定删除机器人「${bot.value.name}」？${removeDir.value ? "机器人目录将被一并删除，此操作不可恢复！" : "注册信息将被移除。"}`,
      "删除机器人",
      { type: "warning", confirmButtonText: "删除", cancelButtonText: "取消" }
    );
    deleting.value = true;
    await api.delete(`/bots/${props.id}?remove_dir=${removeDir.value ? "true" : "false"}`);
    ElMessage.success("已删除");
    router.push({ name: "bots" });
  } catch {
    /* ignore */
  } finally {
    deleting.value = false;
  }
}

async function loadEnv() {
  const data = await api.get(`/bots/${props.id}/config`);
  envContent.value = data.env;
}

async function saveEnv() {
  savingEnv.value = true;
  try {
    await api.put(`/bots/${props.id}/config`, { content: envContent.value });
    ElMessage.success("配置已保存，重启后生效");
  } finally {
    savingEnv.value = false;
  }
}

onMounted(async () => {
  await load();
  loadEnv();
  pollTimer = setInterval(async () => {
    try {
      const data = await api.get(`/bots/${props.id}`);
      bot.value.status = data.status;
      bot.value.running = data.running;
    } catch {
      /* ignore */
    }
  }, 4000);
});

onBeforeUnmount(() => {
  if (pollTimer) clearInterval(pollTimer);
});
</script>

<style scoped>
.detail-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.detail-head > div:first-child {
  display: flex;
  align-items: center;
  gap: 12px;
}

.detail-title {
  font-size: 20px;
  font-weight: 700;
}

.detail-actions {
  display: flex;
  gap: 10px;
}

.auto-start-hint {
  flex-basis: 100%;
  margin-left: 0;
  margin-top: 4px;
}

.overview-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  align-items: start;
}

@media (max-width: 1100px) {
  .overview-grid {
    grid-template-columns: 1fr;
  }
}

.block-title {
  margin: 0 0 16px;
  font-size: 16px;
}

.danger-title {
  color: #f56c6c;
}

.kv {
  display: flex;
  flex-direction: column;
}

.kv-row {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  padding: 9px 0;
  border-bottom: 1px dashed var(--nb-border);
  font-size: 13.5px;
}

.kv-row:last-child {
  border-bottom: none;
}

.kv-row span {
  color: var(--nb-text-secondary);
  flex-shrink: 0;
}

.kv-row b {
  font-weight: 500;
  text-align: right;
  word-break: break-all;
}

.kv-row .path {
  font-family: Consolas, monospace;
  font-size: 12.5px;
}

.danger-card {
  grid-column: 1 / -1;
}

.config-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.env-editor :deep(textarea) {
  font-family: Consolas, "Courier New", monospace;
  font-size: 13px;
  line-height: 1.6;
  background: #1e1e1e;
  color: #d4d4d4;
  border-radius: 8px;
}
</style>
