<template>
  <div class="page">
    <h2 class="page-title">系统设置</h2>

    <div class="settings-grid">
      <div class="card">
        <h3 class="block-title">修改密码</h3>
        <el-form :model="form" label-width="110px" style="max-width: 420px">
          <el-form-item label="当前密码">
            <el-input v-model="form.old_password" type="password" show-password />
          </el-form-item>
          <el-form-item label="新密码">
            <el-input v-model="form.new_password" type="password" show-password />
          </el-form-item>
          <el-form-item label="确认新密码">
            <el-input v-model="form.confirm" type="password" show-password />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" :loading="saving" @click="save">保存</el-button>
          </el-form-item>
        </el-form>
      </div>

      <div class="card">
        <h3 class="block-title">服务器信息</h3>
        <div class="kv">
          <div class="kv-row"><span>主机名</span><b>{{ snap.hostname || "-" }}</b></div>
          <div class="kv-row"><span>系统</span><b class="ellipsis">{{ snap.platform || "-" }}</b></div>
          <div class="kv-row"><span>Python</span><b>{{ snap.python || "-" }}</b></div>
          <div class="kv-row"><span>WebUI 版本</span><b>v{{ snap.webui_version || "-" }}</b></div>
          <div class="kv-row"><span>CPU 核心</span><b>{{ snap.cpu?.count || "-" }}</b></div>
          <div class="kv-row"><span>内存</span><b>{{ memText }}</b></div>
          <div class="kv-row"><span>磁盘</span><b>{{ diskText }}</b></div>
        </div>
      </div>
    </div>

    <div class="card">
      <h3 class="block-title">版本更新</h3>
      <div class="kv" style="max-width: 420px">
        <div class="kv-row"><span>当前版本</span><b>v{{ updateStore.current || "-" }}</b></div>
        <div class="kv-row">
          <span>最新版本</span>
          <b>{{ updateStore.checking ? "检查中…" : (updateStore.latest ? `v${updateStore.latest}` : "-") }}</b>
        </div>
        <div v-if="updateStore.hasUpdate && updateStore.notes" class="update-notes">{{ updateStore.notes }}</div>
        <div v-if="updateStore.latest && !updateStore.hasUpdate" class="update-hint">当前已是最新版本</div>
      </div>
      <div class="update-actions">
        <el-button :loading="updateStore.checking" @click="checkUpdate">检测更新</el-button>
        <el-button v-if="updateStore.hasUpdate" type="primary" :loading="updating" @click="startUpdate">
          立即更新
        </el-button>
      </div>
    </div>

    <div class="card">
      <h3 class="block-title">关于</h3>
      <p class="muted" style="line-height: 1.8">
        NoneBot2 WebUI 是一个面向 NoneBot2 的网页管理面板，支持机器人创建与管理、插件启停与安装、实时日志、
        内置终端与服务器监控。
      </p>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import api from "../api";
import { useUpdateStore } from "../stores/update";

const form = reactive({ old_password: "", new_password: "", confirm: "" });
const saving = ref(false);
const snap = ref({});
const updating = ref(false);
const updateStore = useUpdateStore();

const memText = computed(() => {
  const m = snap.value.memory;
  if (!m) return "-";
  return `${(m.used / 1024 / 1024 / 1024).toFixed(1)} / ${(m.total / 1024 / 1024 / 1024).toFixed(1)} GB`;
});

const diskText = computed(() => {
  const d = snap.value.disk;
  if (!d) return "-";
  return `${(d.used / 1024 / 1024 / 1024).toFixed(1)} / ${(d.total / 1024 / 1024 / 1024).toFixed(1)} GB`;
});

async function save() {
  if (!form.old_password || !form.new_password) {
    ElMessage.warning("请填写完整");
    return;
  }
  if (form.new_password.length < 6) {
    ElMessage.warning("新密码至少 6 位");
    return;
  }
  if (form.new_password !== form.confirm) {
    ElMessage.warning("两次输入的新密码不一致");
    return;
  }
  saving.value = true;
  try {
    await api.post("/auth/password", {
      old_password: form.old_password,
      new_password: form.new_password,
    });
    ElMessage.success("密码已修改，请重新登录");
    form.old_password = form.new_password = form.confirm = "";
  } catch {
    /* ignore */
  } finally {
    saving.value = false;
  }
}

async function checkUpdate() {
  try {
    const info = await updateStore.check(true);
    if (info.has_update) {
      ElMessage.success(`发现新版本 v${info.latest}`);
    } else if (info.latest) {
      ElMessage.success("当前已是最新版本");
    } else {
      ElMessage.warning("检查更新失败，请稍后重试");
    }
  } catch {
    ElMessage.error("检查更新失败");
  }
}

async function startUpdate() {
  updating.value = true;
  try {
    const res = await updateStore.startUpdate();
    if (res && res.started) {
      ElMessage.success(res.detail || "更新已开始");
    }
  } catch {
    /* ignore，失败状态由更新对话框展示 */
  } finally {
    updating.value = false;
  }
}

onMounted(async () => {
  try {
    snap.value = await api.get("/monitor");
  } catch {
    /* ignore */
  }
  try {
    await updateStore.check();
  } catch {
    /* ignore */
  }
});
</script>

<style scoped>
.settings-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-bottom: 16px;
}

@media (max-width: 1100px) {
  .settings-grid {
    grid-template-columns: 1fr;
  }
}

.block-title {
  margin: 0 0 16px;
  font-size: 16px;
}

.kv-row {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  padding: 9px 0;
  border-bottom: 1px dashed var(--nb-border);
  font-size: 13.5px;
}

.kv-row span {
  color: var(--nb-text-secondary);
  flex-shrink: 0;
}

.kv-row b {
  font-weight: 500;
  text-align: right;
}

.update-actions {
  margin-top: 14px;
  display: flex;
  gap: 10px;
}

.update-notes {
  margin-top: 10px;
  font-size: 12.5px;
  color: var(--nb-text-secondary);
  white-space: pre-line;
  max-height: 80px;
  overflow: auto;
}

.update-hint {
  margin-top: 10px;
  font-size: 12.5px;
  color: #67c23a;
}

.ellipsis {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
