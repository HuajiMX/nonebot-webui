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
        <el-table-column label="操作" width="300" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="$router.push(`/visual-plugins/${row.id}`)">编辑</el-button>
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
  </div>
</template>

<script setup>
import { onMounted, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Plus } from "@element-plus/icons-vue";
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

</style>
