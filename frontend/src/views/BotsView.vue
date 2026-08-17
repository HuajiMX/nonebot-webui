<template>
  <div class="page">
    <div class="head">
      <h2 class="page-title">机器人管理</h2>
      <el-button type="primary" :icon="Plus" @click="openCreate">创建机器人</el-button>
    </div>

    <div class="card">
      <el-table :data="bots" v-loading="loading" style="width: 100%">
        <el-table-column label="名称" min-width="150">
          <template #default="{ row }">
            <router-link :to="`/bots/${row.id}`" class="bot-link">{{ row.name }}</router-link>
          </template>
        </el-table-column>
        <el-table-column label="协议" width="140">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">{{ row.adapter_label || row.adapter }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="端口" prop="port" width="80" />
        <el-table-column label="目录" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">{{ row.directory }}</template>
        </el-table-column>
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <StatusTag :status="row.status" />
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="170">
          <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="280" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="$router.push(`/bots/${row.id}`)">详情</el-button>
            <el-button
              size="small"
              :type="row.status === 'running' ? 'warning' : 'success'"
              :loading="busy[row.id]"
              @click="toggle(row)"
            >
              {{ row.status === "running" ? "暂停" : "启动" }}
            </el-button>
            <el-button size="small" :loading="busy[row.id]" @click="restart(row)">重启</el-button>
            <el-button size="small" type="danger" plain @click="confirmDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!loading && bots.length === 0" description="还没有机器人，点击右上角创建" />
    </div>

    <!-- 创建对话框 -->
    <el-dialog v-model="createVisible" title="创建机器人" width="560px" :close-on-click-modal="false">
      <el-form :model="form" label-width="110px">
        <el-form-item label="名称" required>
          <el-input v-model="form.name" placeholder="例如：my-bot" />
        </el-form-item>
        <el-form-item label="机器人目录" required>
          <div class="dir-picker">
            <el-input v-model="form.directory" placeholder="例如：E:\bots\my-bot" />
            <el-button
              :icon="FolderOpened"
              :loading="pickingDir"
              @click="pickDirectory"
              title="打开系统文件夹选择对话框"
            >
              选择文件夹
            </el-button>
          </div>
        </el-form-item>
        <el-form-item label="协议 / 适配器">
          <el-select v-model="form.adapter" style="width: 100%">
            <el-option v-for="a in adapters" :key="a.value" :label="a.label" :value="a.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="监听端口">
          <el-input-number v-model="form.port" :min="1" :max="65535" />
          <span class="muted" style="margin-left: 10px">NoneBot 服务端口</span>
        </el-form-item>
        <el-form-item label="监听地址">
          <el-input v-model="form.host" placeholder="0.0.0.0" />
        </el-form-item>
        <el-form-item label="Python 路径">
          <el-input v-model="form.python" placeholder="留空使用 WebUI 所在 Python" />
        </el-form-item>
        <el-form-item label="目录不存在时">
          <el-switch v-model="form.create_dir" active-text="自动创建" />
        </el-form-item>
        <el-form-item label="创建后启动">
          <el-switch v-model="form.auto_start" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="submitCreate">开始创建</el-button>
      </template>
    </el-dialog>

    <!-- 创建进度 -->
    <el-dialog v-model="progressVisible" title="正在创建机器人" width="640px" :close-on-click-modal="false" :show-close="false">
      <div class="progress-box">
        <div v-for="(line, i) in progressLines" :key="i" class="line">{{ line }}</div>
      </div>
      <template #footer>
        <el-button type="primary" :disabled="creating" @click="finishProgress">完成</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { FolderOpened, Plus } from "@element-plus/icons-vue";
import api, { wsUrl } from "../api";
import StatusTag from "../components/StatusTag.vue";

const bots = ref([]);
const adapters = ref([]);
const loading = ref(false);
const busy = reactive({});
const createVisible = ref(false);
const creating = ref(false);
const pickingDir = ref(false);
const progressVisible = ref(false);
const progressLines = ref([]);
let progressWs = null;
let progressTimer = null;
let creatingBotId = null;

const form = reactive({
  name: "",
  directory: "",
  adapter: "onebot_v11",
  host: "0.0.0.0",
  port: 8080,
  python: "",
  create_dir: true,
  auto_start: false,
});

async function load() {
  loading.value = true;
  try {
    bots.value = await api.get("/bots");
  } finally {
    loading.value = false;
  }
}

function fmtTime(iso) {
  if (!iso) return "-";
  const d = new Date(iso);
  return d.toLocaleString("zh-CN", { hour12: false });
}

async function toggle(row) {
  busy[row.id] = true;
  try {
    if (row.status === "running") {
      await api.post(`/bots/${row.id}/stop`);
      ElMessage.success("已暂停");
    } else {
      await api.post(`/bots/${row.id}/start`);
      ElMessage.success("已启动");
    }
    await load();
  } catch {
    /* ignore */
  } finally {
    busy[row.id] = false;
  }
}

async function restart(row) {
  busy[row.id] = true;
  try {
    await api.post(`/bots/${row.id}/restart`);
    ElMessage.success("已重启");
  } catch {
    /* ignore */
  } finally {
    busy[row.id] = false;
  }
}

async function confirmDelete(row) {
  try {
    await ElMessageBox.confirm(
      `确定删除机器人「${row.name}」？删除后将无法恢复注册信息。`,
      "删除机器人",
      { type: "warning", confirmButtonText: "删除", cancelButtonText: "取消" }
    );
    await api.delete(`/bots/${row.id}`);
    ElMessage.success("已删除");
    load();
  } catch {
    /* cancel */
  }
}

async function openCreate() {
  if (adapters.value.length === 0) {
    const data = await api.get("/bots/adapters");
    adapters.value = data.adapters;
  }
  Object.assign(form, {
    name: "",
    directory: "",
    adapter: "onebot_v11",
    host: "0.0.0.0",
    port: 8080,
    python: "",
    create_dir: true,
    auto_start: false,
  });
  createVisible.value = true;
}

async function pickDirectory() {
  pickingDir.value = true;
  try {
    const result = await api.post("/bots/pick-directory");
    if (result.directory) {
      form.directory = result.directory;
    } else if (result.supported === false) {
      ElMessage.warning("当前系统不支持系统目录选择，请手动输入路径");
    }
  } catch {
    /* ignore */
  } finally {
    pickingDir.value = false;
  }
}

async function submitCreate() {
  if (!form.name || !form.directory) {
    ElMessage.warning("请填写名称与目录");
    return;
  }
  creating.value = true;
  try {
    const bot = await api.post("/bots", { ...form });
    creatingBotId = bot.id;
    createVisible.value = false;
    progressLines.value = [];
    progressVisible.value = true;
    startProgress(bot.id);
    progressTimer = setInterval(checkCreating, 2000);
  } catch {
    /* ignore */
  } finally {
    creating.value = false;
  }
}

function startProgress(botId) {
  progressWs = new WebSocket(wsUrl(`/api/bots/${botId}/log/ws`));
  progressWs.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data);
      if (msg.type === "log" && msg.data) {
        progressLines.value.push(msg.data);
        if (progressLines.value.length > 300) progressLines.value.shift();
      }
    } catch {
      /* ignore */
    }
  };
}

async function checkCreating() {
  if (!creatingBotId) return;
  try {
    const bot = await api.get(`/bots/${creatingBotId}`);
    if (bot.status !== "creating") {
      creating.value = false;
      clearInterval(progressTimer);
      if (progressWs) progressWs.close();
      if (bot.status === "error") {
        ElMessage.error(`创建失败：${bot.extra?.error || "未知错误"}`);
      } else {
        ElMessage.success(`机器人「${bot.name}」创建完成`);
        if (bot.auto_start) {
          await api.post(`/bots/${bot.id}/start`);
        }
        load();
      }
    }
  } catch {
    /* ignore */
  }
}

function finishProgress() {
  progressVisible.value = false;
  creatingBotId = null;
  load();
}

onMounted(load);
onBeforeUnmount(() => {
  if (progressTimer) clearInterval(progressTimer);
  if (progressWs) progressWs.close();
});
</script>

<style scoped>
.head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.bot-link {
  color: var(--nb-orange);
  font-weight: 500;
}

.progress-box {
  height: 300px;
  overflow: auto;
  background: #1e1e1e;
  border-radius: 8px;
  padding: 12px;
  font-family: Consolas, "Courier New", monospace;
  font-size: 12px;
  color: #d4d4d4;
}

.dir-picker {
  display: flex;
  gap: 8px;
  width: 100%;
}

.dir-picker .el-input {
  flex: 1;
}

.line {
  white-space: pre-wrap;
  word-break: break-all;
  line-height: 1.7;
}
</style>
