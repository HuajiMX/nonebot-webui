<template>
  <div class="layout">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-logo">NB</div>
        <div class="brand-text">
          <b>NoneBot2</b>
          <span>WebUI</span>
        </div>
      </div>

      <nav class="nav">
        <router-link
          v-for="item in navs"
          :key="item.path"
          :to="item.path"
          class="nav-item"
          :class="{ active: isActive(item.path) }"
        >
          <el-icon :size="18"><component :is="item.icon" /></el-icon>
          <span>{{ item.label }}</span>
        </router-link>
      </nav>

      <div class="sidebar-footer">
        <div class="version">v{{ version }}</div>
        <div class="copyright">© 2026 HuajiMX</div>
      </div>
    </aside>

    <div class="main">
      <header class="topbar">
        <div class="topbar-title">{{ currentTitle }}</div>
        <el-dropdown trigger="click" @command="onCommand">
          <div class="user-chip">
            <el-avatar :size="30" class="user-avatar">{{ initial }}</el-avatar>
            <span>{{ auth.username }}</span>
            <el-icon><ArrowDown /></el-icon>
          </div>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="settings">系统设置</el-dropdown-item>
              <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </header>

      <main class="content">
        <div v-if="updateBanner" class="update-banner">
          <el-alert type="warning" :closable="false">
            <template #title>
              <div class="update-title">
                <span>发现新版本 v{{ updateBanner.latest }}（当前 v{{ updateBanner.current }}）</span>
                <div class="update-actions">
                  <el-button size="small" type="primary" :loading="updating" @click="doUpdate">立即更新</el-button>
                  <el-button size="small" @click="dismissUpdate">稍后</el-button>
                </div>
              </div>
              <div v-if="updateBanner.notes" class="update-notes">{{ updateBanner.notes }}</div>
            </template>
          </el-alert>
        </div>
        <router-view />
      </main>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { useAuthStore } from "../stores/auth";
import api from "../api";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const version = ref("0.1.0");
const updateBanner = ref(null);
const updating = ref(false);

const navs = [
  { path: "/", label: "仪表盘", icon: "Odometer" },
  { path: "/bots", label: "机器人管理", icon: "Cpu" },
  { path: "/visual-plugins", label: "可视化插件编写", icon: "MagicStick" },
  { path: "/settings", label: "系统设置", icon: "Setting" },
];

const currentTitle = computed(() => {
  if (route.name === "bot-detail") return "机器人详情";
  if (route.name === "visual-plugin-editor") return "可视化插件编写";
  const item = navs.find((n) => route.path.startsWith(n.path));
  return item ? item.label : "NoneBot2 WebUI";
});

const initial = computed(() => (auth.username ? auth.username[0].toUpperCase() : "U"));

function isActive(path) {
  if (path === "/") return route.path === "/";
  return route.path.startsWith(path);
}

async function onCommand(cmd) {
  if (cmd === "logout") {
    await auth.logout();
    router.push({ name: "login" });
  } else if (cmd === "settings") {
    router.push({ name: "settings" });
  }
}

async function loadUpdate() {
  try {
    const info = await api.get("/update/status");
    if (
      info.has_update &&
      info.latest !== localStorage.getItem("nb_update_dismissed")
    ) {
      updateBanner.value = info;
    }
  } catch {
    /* ignore */
  }
}

function dismissUpdate() {
  if (updateBanner.value) {
    localStorage.setItem("nb_update_dismissed", updateBanner.value.latest);
  }
  updateBanner.value = null;
}

async function doUpdate() {
  updating.value = true;
  try {
    const res = await api.post("/update");
    updateBanner.value = null;
    ElMessage.success(res.detail || "更新已开始，服务将自动重启，请稍后刷新页面");
  } catch {
    /* ignore */
  } finally {
    updating.value = false;
  }
}

onMounted(async () => {
  try {
    const health = await api.get("/health");
    version.value = health.version || version.value;
  } catch {
    /* ignore */
  }
  loadUpdate();
});
</script>

<style scoped>
.layout {
  display: flex;
  height: 100%;
}

.sidebar {
  width: 220px;
  background: #fff;
  border-right: 1px solid var(--nb-border);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 20px 18px;
}

.brand-logo {
  width: 38px;
  height: 38px;
  border-radius: 10px;
  background: var(--nb-orange);
  color: #fff;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
}

.brand-text {
  display: flex;
  flex-direction: column;
  line-height: 1.25;
}

.brand-text b {
  font-size: 15px;
}

.brand-text span {
  font-size: 12px;
  color: var(--nb-text-secondary);
}

.nav {
  padding: 8px 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 11px 14px;
  border-radius: 8px;
  color: #4a4a4a;
  font-size: 14px;
  transition: all 0.18s;
}

.nav-item:hover {
  background: var(--nb-gray);
}

.nav-item.active {
  background: var(--nb-orange-light);
  color: var(--nb-orange);
  font-weight: 600;
}

.sidebar-footer {
  padding: 14px 20px;
  border-top: 1px solid var(--nb-border);
}

.version {
  font-size: 12px;
  color: var(--nb-text-secondary);
}

.copyright {
  margin-top: 4px;
  font-size: 12px;
  color: var(--nb-text-secondary);
}

.main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.topbar {
  height: 60px;
  background: #fff;
  border-bottom: 1px solid var(--nb-border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
}

.topbar-title {
  font-size: 16px;
  font-weight: 600;
}

.user-chip {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  padding: 6px 10px;
  border-radius: 8px;
  transition: background 0.18s;
  font-size: 14px;
}

.user-chip:hover {
  background: var(--nb-gray);
}

.user-avatar {
  background: var(--nb-orange);
  color: #fff;
  font-weight: 600;
}

.content {
  flex: 1;
  overflow: auto;
}

.update-banner {
  padding: 10px 16px 0;
}

.update-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.update-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.update-notes {
  margin-top: 6px;
  font-size: 12px;
  color: #606266;
  white-space: pre-line;
  max-height: 64px;
  overflow: auto;
}
</style>
