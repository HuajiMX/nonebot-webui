<template>
  <div>
    <div class="plugin-toolbar">
      <el-button type="primary" :icon="Upload" @click="fileRef.click()">安装插件（.py / .zip）</el-button>
      <input
        ref="fileRef"
        type="file"
        accept=".py,.zip"
        multiple
        style="display: none"
        @change="onFiles"
      />
      <el-tag v-if="needsRestart" type="warning" size="small" effect="light">
        机器人运行中，启用/暂停将在重启后生效
      </el-tag>
      <div style="flex: 1"></div>
      <el-button size="small" :icon="Refresh" @click="load">刷新</el-button>
    </div>

    <el-table :data="plugins" v-loading="loading" style="width: 100%">
      <el-table-column label="插件名称" min-width="170">
        <template #default="{ row }">
          <b>{{ row.name }}</b>
          <el-tag v-if="row.kind === 'package'" size="small" type="info" effect="plain" style="margin-left: 8px">包</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="描述" min-width="220" show-overflow-tooltip>
        <template #default="{ row }">{{ row.description || "-" }}</template>
      </el-table-column>
      <el-table-column label="大小" width="90">
        <template #default="{ row }">{{ fmtSize(row.size) }}</template>
      </el-table-column>
      <el-table-column label="修改时间" width="170">
        <template #default="{ row }">{{ fmtTime(row.mtime) }}</template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="row.enabled ? 'success' : 'info'" size="small" effect="light">
            {{ row.enabled ? "启用" : "暂停" }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="120">
        <template #default="{ row }">
          <el-switch
            :model-value="row.enabled"
            :loading="switching === row.name"
            @change="(v) => toggle(row, v)"
          />
        </template>
      </el-table-column>
    </el-table>
    <el-empty v-if="!loading && plugins.length === 0" description="插件目录为空，可上传 .py 或 .zip 安装插件" />
  </div>
</template>

<script setup>
import { onMounted, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Refresh, Upload } from "@element-plus/icons-vue";
import api from "../api";

const props = defineProps({
  botId: { type: String, required: true },
});

const plugins = ref([]);
const needsRestart = ref(false);
const loading = ref(false);
const switching = ref("");
const fileRef = ref(null);

async function load() {
  loading.value = true;
  try {
    const data = await api.get(`/bots/${props.botId}/plugins`);
    plugins.value = data.plugins;
    needsRestart.value = data.needs_restart;
  } finally {
    loading.value = false;
  }
}

async function toggle(row, enabled) {
  switching.value = row.name;
  try {
    const label = enabled ? "启用" : "暂停";
    if (needsRestart.value) {
      await ElMessageBox.confirm(
        `机器人正在运行，「${label}」后 WebUI 将自动重启机器人以生效，是否继续？`,
        `${label}插件`,
        { type: "warning", confirmButtonText: "重启并应用", cancelButtonText: "取消" }
      );
    }
    const result = await api.put(
      `/bots/${props.botId}/plugins/${row.name}/enabled?enabled=${enabled}&auto_restart=true`
    );
    ElMessage.success(result.restarted ? `已${label}并重启机器人` : `已${label}，重启后生效`);
    load();
  } catch {
    /* ignore */
  } finally {
    switching.value = "";
  }
}

async function onFiles(ev) {
  const files = Array.from(ev.target.files || []);
  if (!files.length) return;
  for (const file of files) {
    const fd = new FormData();
    fd.append("file", file);
    try {
      const result = await api.post(`/bots/${props.botId}/plugins/upload`, fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      ElMessage.success(result.message || "安装成功");
    } catch {
      /* 拦截器已提示 */
    }
  }
  ev.target.value = "";
  load();
}

function fmtSize(bytes) {
  if (!bytes && bytes !== 0) return "-";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}

function fmtTime(ts) {
  if (!ts) return "-";
  return new Date(ts * 1000).toLocaleString("zh-CN", { hour12: false });
}

onMounted(load);
</script>

<style scoped>
.plugin-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 14px;
}
</style>
