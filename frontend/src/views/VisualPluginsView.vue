<template>
  <div class="page">
    <div class="head">
      <h2 class="page-title">可视化插件编写</h2>
      <el-button type="primary" :icon="Plus" @click="openCreate">新建插件</el-button>
    </div>
    <p class="muted" style="margin-top: -8px">
      拖拽组件拼装机器人流程，生成 OneBot 通用协议（V11）NoneBot 插件，可直接装配到机器人。
    </p>

    <div class="card">
      <el-table :data="plugins" v-loading="loading" style="width: 100%">
        <el-table-column label="名称" min-width="160">
          <template #default="{ row }">
            <a class="plugin-link" @click="$router.push(`/visual-plugins/${row.id}`)">{{ row.name }}</a>
          </template>
        </el-table-column>
        <el-table-column label="描述" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">{{ row.description || "-" }}</template>
        </el-table-column>
        <el-table-column label="节点数" prop="node_count" width="90" />
        <el-table-column label="已装配机器人" min-width="160">
          <template #default="{ row }">
            <template v-if="row.installed && row.installed.length">
              <el-tag
                v-for="item in row.installed"
                :key="item.bot_id"
                size="small"
                effect="plain"
                style="margin: 2px 4px 2px 0"
              >
                {{ item.bot_name }}
              </el-tag>
            </template>
            <span v-else class="muted">未装配</span>
          </template>
        </el-table-column>
        <el-table-column label="更新时间" width="170">
          <template #default="{ row }">{{ fmtTime(row.updated_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="380" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="$router.push(`/visual-plugins/${row.id}`)">编辑</el-button>
            <el-button size="small" @click="openStorage(row)">数据</el-button>
            <el-button size="small" type="primary" plain @click="openInstall(row)">装配到机器人</el-button>
            <el-button size="small" type="danger" plain @click="confirmDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!loading && plugins.length === 0" description="还没有可视化插件，点击右上角新建" />
    </div>

    <!-- 新建 -->
    <el-dialog v-model="createVisible" title="新建可视化插件" width="480px" :close-on-click-modal="false">
      <el-form :model="createForm" label-width="80px">
        <el-form-item label="名称" required>
          <el-input v-model="createForm.name" placeholder="例如：天气查询助手" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="createForm.description" type="textarea" :rows="2" placeholder="可选，一句话说明插件用途" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="submitCreate">创建并编辑</el-button>
      </template>
    </el-dialog>

    <!-- 装配 -->
    <el-dialog v-model="installVisible" title="装配到机器人" width="440px">
      <el-form label-width="80px">
        <el-form-item label="机器人">
          <el-select v-model="installBotId" placeholder="选择机器人" style="width: 100%">
            <el-option v-for="b in bots" :key="b.id" :label="b.name" :value="b.id" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="installVisible = false">取消</el-button>
        <el-button type="primary" :loading="installing" @click="submitInstall">安装</el-button>
      </template>
    </el-dialog>

    <!-- 数据存储 -->
    <el-drawer v-model="storageVisible" :title="`数据存储 · ${storageRow?.name || ''}`" size="720px">
      <div class="storage-head">
        <div class="storage-left">
          <el-select
            v-if="storageBots.length > 1"
            v-model="storageBotId"
            size="small"
            style="width: 170px"
            @change="loadStorage"
          >
            <el-option v-for="b in storageBots" :key="b.bot_id" :label="b.bot_name" :value="b.bot_id" />
          </el-select>
          <span class="storage-meta">
            {{ storageData.count }} 个键 · {{ fmtSize(storageData.size) }} / {{ fmtSize(storageData.limit_bytes) }}
            <template v-if="storageData.mtime"> · 更新于 {{ storageData.mtime }}</template>
          </span>
        </div>
        <div class="storage-actions">
          <el-button size="small" :icon="Refresh" @click="loadStorage">刷新</el-button>
          <el-button size="small" @click="openEdit(null)">新增键</el-button>
          <el-button size="small" type="danger" plain @click="confirmClear">清空全部</el-button>
        </div>
      </div>

      <el-table :data="storageData.items" v-loading="storageLoading" size="small" style="width: 100%">
        <el-table-column prop="key" label="键" min-width="120" show-overflow-tooltip />
        <el-table-column prop="type" label="类型" width="70" />
        <el-table-column label="大小" width="70">
          <template #default="{ row }">{{ fmtSize(row.size) }}</template>
        </el-table-column>
        <el-table-column prop="preview" label="值" min-width="150" show-overflow-tooltip />
        <el-table-column prop="updated" label="更新时间" width="145" />
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button size="small" text type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button size="small" text type="danger" @click="confirmDeleteKey(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty
        v-if="!storageLoading && storageData.items.length === 0"
        description="还没有数据。流程里用「数据存储」组件写入后，这里就能看到。"
        :image-size="80"
      />
    </el-drawer>

    <el-dialog
      v-model="editVisible"
      :title="editIsNew ? '新增键' : `编辑 · ${editForm.key}`"
      width="560px"
      :close-on-click-modal="false"
    >
      <el-form label-position="top">
        <el-form-item label="键名">
          <el-input
            v-model="editForm.key"
            :disabled="!editIsNew"
            placeholder="中英文、数字、下划线、短横线，最多 64 个字符"
          />
        </el-form-item>
        <el-form-item label="值（JSON）">
          <el-input v-model="editForm.text" type="textarea" :rows="10" class="storage-editor" />
        </el-form-item>
      </el-form>
      <el-alert
        type="info"
        :closable="false"
        title="按 JSON 写：字符串要带引号，数字、true/false、null 原样写。"
      />
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="editSaving" @click="saveEdit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Plus, Refresh } from "@element-plus/icons-vue";
import api from "../api";

const plugins = ref([]);
const bots = ref([]);
const loading = ref(false);

const createVisible = ref(false);
const creating = ref(false);
const createForm = ref({ name: "", description: "" });

const installVisible = ref(false);
const installing = ref(false);
const installBotId = ref("");
let installPluginId = "";

const storageVisible = ref(false);
const storageLoading = ref(false);
const storageRow = ref(null);
const storageBots = ref([]);
const storageBotId = ref("");
const storageData = ref({
  items: [],
  count: 0,
  size: 0,
  limit_bytes: 0,
  limit_keys: 0,
  mtime: "",
});

const editVisible = ref(false);
const editSaving = ref(false);
const editIsNew = ref(false);
const editForm = reactive({ key: "", text: "" });

async function load() {
  loading.value = true;
  try {
    const data = await api.get("/visual-plugins");
    plugins.value = data.plugins;
  } finally {
    loading.value = false;
  }
}

function fmtTime(iso) {
  if (!iso) return "-";
  return new Date(iso).toLocaleString("zh-CN", { hour12: false });
}

function openCreate() {
  createForm.value = { name: "", description: "" };
  createVisible.value = true;
}

async function submitCreate() {
  if (!createForm.value.name.trim()) {
    ElMessage.warning("请填写插件名称");
    return;
  }
  creating.value = true;
  try {
    const plugin = await api.post("/visual-plugins", { ...createForm.value });
    createVisible.value = false;
    ElMessage.success("已创建，开始搭建流程");
    load();
    window.location.href = `/visual-plugins/${plugin.id}`;
  } catch {
    /* ignore */
  } finally {
    creating.value = false;
  }
}

async function loadBots() {
  if (bots.value.length === 0) {
    bots.value = await api.get("/bots");
  }
}

function openInstall(row) {
  installPluginId = row.id;
  installBotId.value = "";
  loadBots().then(() => {
    installVisible.value = true;
  });
}

async function submitInstall() {
  if (!installBotId.value) {
    ElMessage.warning("请选择机器人");
    return;
  }
  installing.value = true;
  try {
    const result = await api.post(`/visual-plugins/${installPluginId}/install`, {
      bot_id: installBotId.value,
    });
    ElMessage.success(
      result.restarted ? "已安装并自动重启机器人" : "已安装，机器人下次启动时生效"
    );
    installVisible.value = false;
    load();
  } catch {
    /* ignore */
  } finally {
    installing.value = false;
  }
}

async function confirmDelete(row) {
  try {
    const installed = (row.installed || []).length;
    await ElMessageBox.confirm(
      installed
        ? `确定删除「${row.name}」？将同时从 ${installed} 个已装配的机器人中移除生成的插件。`
        : `确定删除「${row.name}」？`,
      "删除可视化插件",
      { type: "warning", confirmButtonText: "删除", cancelButtonText: "取消" }
    );
    await api.delete(`/visual-plugins/${row.id}`);
    ElMessage.success("已删除");
    load();
  } catch {
    /* cancel */
  }
}

function fmtSize(n) {
  const v = Number(n) || 0;
  if (v < 1024) return `${v} B`;
  if (v < 1024 * 1024) return `${(v / 1024).toFixed(1)} KB`;
  return `${(v / 1024 / 1024).toFixed(1)} MB`;
}

async function openStorage(row) {
  const list = row.installed || [];
  if (!list.length) {
    ElMessage.info("先把这个插件装配到机器人，才会有存储数据");
    return;
  }
  storageRow.value = row;
  storageBots.value = list;
  storageBotId.value = list[0].bot_id;
  storageVisible.value = true;
  await loadStorage();
}

async function loadStorage() {
  if (!storageRow.value || !storageBotId.value) return;
  storageLoading.value = true;
  try {
    storageData.value = await api.get(`/visual-plugins/${storageRow.value.id}/storage`, {
      params: { bot_id: storageBotId.value },
    });
  } catch {
    storageData.value = { items: [], count: 0, size: 0, limit_bytes: 0, limit_keys: 0, mtime: "" };
  } finally {
    storageLoading.value = false;
  }
}

function openEdit(row) {
  editIsNew.value = !row;
  editForm.key = row ? row.key : "";
  editForm.text = row ? row.json : "null";
  editVisible.value = true;
}

async function saveEdit() {
  const key = editForm.key.trim();
  if (!key) {
    ElMessage.warning("键名不能为空");
    return;
  }
  let value;
  try {
    value = JSON.parse(editForm.text);
  } catch (e) {
    ElMessage.error(`值不是合法的 JSON：${e.message}`);
    return;
  }
  editSaving.value = true;
  try {
    await api.put(`/visual-plugins/${storageRow.value.id}/storage`, {
      bot_id: storageBotId.value,
      key,
      value,
    });
    ElMessage.success("已保存，机器人下次读写时生效");
    editVisible.value = false;
    await loadStorage();
  } catch {
    /* 拦截器已提示 */
  } finally {
    editSaving.value = false;
  }
}

async function confirmDeleteKey(row) {
  try {
    await ElMessageBox.confirm(`确定删除键「${row.key}」？此操作不可恢复。`, "删除数据", {
      type: "warning",
      confirmButtonText: "删除",
      cancelButtonText: "取消",
    });
  } catch {
    return;
  }
  try {
    await api.delete(
      `/visual-plugins/${storageRow.value.id}/storage/${encodeURIComponent(row.key)}`,
      { params: { bot_id: storageBotId.value } }
    );
    ElMessage.success("已删除");
    await loadStorage();
  } catch {
    /* 拦截器已提示 */
  }
}

async function confirmClear() {
  try {
    await ElMessageBox.confirm(
      "将删除该插件在此机器人上的全部存储数据，无法恢复。确定继续？",
      "清空数据",
      {
        type: "warning",
        confirmButtonText: "清空",
        cancelButtonText: "取消",
        confirmButtonClass: "el-button--danger",
      }
    );
  } catch {
    return;
  }
  try {
    const result = await api.post(`/visual-plugins/${storageRow.value.id}/storage/clear`, {
      bot_id: storageBotId.value,
    });
    ElMessage.success(`已清空 ${result.cleared} 个键`);
    await loadStorage();
  } catch {
    /* 拦截器已提示 */
  }
}

onMounted(load);
</script>

<style scoped>
.head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.plugin-link {
  color: var(--nb-orange);
  font-weight: 500;
  cursor: pointer;
}

.storage-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.storage-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.storage-meta {
  font-size: 12px;
  color: var(--el-text-color-secondary, #909399);
}

.storage-actions {
  display: flex;
  gap: 8px;
}

.storage-editor :deep(textarea) {
  font-family: Consolas, Menlo, Monaco, monospace;
  font-size: 12px;
  line-height: 1.6;
}

</style>
