<template>
  <div class="page">
    <h2 class="page-title">仪表盘</h2>

    <!-- 服务器状态 -->
    <div class="grid cards">
      <div class="card stat">
        <div class="stat-label">CPU 占用</div>
        <div class="stat-value" :style="{ color: cpuColor }">{{ cpu }}%</div>
        <el-progress :percentage="cpu" :show-text="false" :stroke-width="8" :color="cpuColor" />
      </div>
      <div class="card stat">
        <div class="stat-label">内存占用</div>
        <div class="stat-value" :style="{ color: memColor }">{{ mem }}%</div>
        <el-progress :percentage="mem" :show-text="false" :stroke-width="8" :color="memColor" />
      </div>
      <div class="card stat">
        <div class="stat-label">磁盘占用</div>
        <div class="stat-value">{{ disk }}%</div>
        <el-progress :percentage="disk" :show-text="false" :stroke-width="8" />
      </div>
      <div class="card stat">
        <div class="stat-label">机器人</div>
        <div class="stat-value">{{ botRunning }} / {{ botTotal }}<span class="unit">运行中</span></div>
        <div class="muted">运行 / 总数</div>
      </div>
    </div>

    <!-- 趋势图 -->
    <div class="grid charts">
      <div class="card chart-card">
        <div class="chart-title">CPU 与内存趋势（近 2 分钟）</div>
        <div ref="chartEl" class="chart"></div>
      </div>
      <div class="card info-card">
        <div class="chart-title">服务器信息</div>
        <div class="info-rows">
          <div class="info-row"><span>主机名</span><b>{{ data.hostname || "-" }}</b></div>
          <div class="info-row"><span>系统</span><b class="ellipsis">{{ data.platform || "-" }}</b></div>
          <div class="info-row"><span>Python</span><b>{{ data.python || "-" }}</b></div>
          <div class="info-row"><span>WebUI 版本</span><b>v{{ data.webui_version || "-" }}</b></div>
          <div class="info-row"><span>运行时长</span><b>{{ uptimeText }}</b></div>
          <div class="info-row"><span>网络 ↑↓</span><b>{{ netText }}</b></div>
        </div>
      </div>
    </div>

    <!-- 机器人概览 -->
    <div class="card bots-card">
      <div class="card-head">
        <span class="chart-title">机器人概览</span>
        <el-button type="primary" size="small" @click="goBots">管理机器人</el-button>
      </div>
      <el-table :data="bots" size="default" style="width: 100%">
        <el-table-column label="名称" min-width="160">
          <template #default="{ row }">
            <router-link :to="`/bots/${row.id}`" class="bot-link">{{ row.name }}</router-link>
          </template>
        </el-table-column>
        <el-table-column label="协议" prop="adapter" width="130">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">{{ row.adapter }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="端口" prop="port" width="90" />
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <StatusTag :status="row.status" />
          </template>
        </el-table-column>
        <el-table-column label="目录" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">{{ row.directory }}</template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="toggle(row)">
              {{ row.status === "running" ? "暂停" : "启动" }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import * as echarts from "echarts";
import api, { wsUrl } from "../api";
import StatusTag from "../components/StatusTag.vue";

const router = useRouter();
const data = ref({});
const bots = ref([]);
const history = ref([]);
const chartEl = ref(null);
let chart = null;
let ws = null;

const cpu = computed(() => Math.round((data.value.cpu?.percent ?? 0) * 10) / 10);
const mem = computed(() => Math.round((data.value.memory?.percent ?? 0) * 10) / 10);
const disk = computed(() => Math.round((data.value.disk?.percent ?? 0) * 10) / 10);
const botTotal = computed(() => data.value.bots?.total ?? bots.value.length);
const botRunning = computed(() => data.value.bots?.running ?? 0);

const cpuColor = computed(() => (cpu.value > 80 ? "#d94545" : cpu.value > 60 ? "#e6a23c" : "#ea5252"));
const memColor = computed(() => (mem.value > 85 ? "#d94545" : mem.value > 70 ? "#e6a23c" : "#ea5252"));

const uptimeText = computed(() => {
  const s = data.value.uptime ?? 0;
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  return d > 0 ? `${d} 天 ${h} 小时` : `${h} 小时 ${m} 分`;
});

const netText = computed(() => {
  const n = data.value.network;
  if (!n) return "-";
  const fmt = (v) => (v >= 1024 * 1024 ? `${(v / 1024 / 1024).toFixed(1)} MB/s` : `${(v / 1024).toFixed(0)} KB/s`);
  return `↑ ${fmt(n.up)} / ↓ ${fmt(n.down)}`;
});

function renderChart() {
  if (!chart && chartEl.value) {
    chart = echarts.init(chartEl.value);
  }
  if (!chart) return;
  chart.setOption({
    grid: { left: 40, right: 16, top: 30, bottom: 28 },
    tooltip: { trigger: "axis" },
    legend: { data: ["CPU", "内存"], top: 0 },
    xAxis: {
      type: "category",
      data: history.value.map((h) => h.time),
      axisLabel: { fontSize: 10 },
    },
    yAxis: { type: "value", max: 100, axisLabel: { formatter: "{value}%" } },
    series: [
      {
        name: "CPU",
        type: "line",
        smooth: true,
        showSymbol: false,
        areaStyle: { opacity: 0.12 },
        lineStyle: { color: "#ea5252", width: 2 },
        itemStyle: { color: "#ea5252" },
        data: history.value.map((h) => h.cpu),
      },
      {
        name: "内存",
        type: "line",
        smooth: true,
        showSymbol: false,
        areaStyle: { opacity: 0.12 },
        lineStyle: { color: "#6aa8f0", width: 2 },
        itemStyle: { color: "#6aa8f0" },
        data: history.value.map((h) => h.mem),
      },
    ],
  });
}

function onSnapshot(snap) {
  data.value = snap;
  const t = new Date(snap.time * 1000);
  history.value.push({
    time: `${String(t.getHours()).padStart(2, "0")}:${String(t.getMinutes()).padStart(2, "0")}:${String(t.getSeconds()).padStart(2, "0")}`,
    cpu: snap.cpu?.percent ?? 0,
    mem: snap.memory?.percent ?? 0,
  });
  if (history.value.length > 60) history.value.shift();
  renderChart();
}

function connectMonitor() {
  ws = new WebSocket(wsUrl("/api/monitor/ws"));
  ws.onmessage = (ev) => {
    try {
      onSnapshot(JSON.parse(ev.data));
    } catch {
      /* ignore */
    }
  };
  ws.onclose = () => {
    setTimeout(connectMonitor, 3000);
  };
}

async function loadBots() {
  bots.value = await api.get("/bots");
}

async function toggle(row) {
  try {
    if (row.status === "running") {
      await api.post(`/bots/${row.id}/stop`);
      ElMessage.success("已暂停");
    } else {
      await api.post(`/bots/${row.id}/start`);
      ElMessage.success("已启动");
    }
    loadBots();
  } catch {
    /* 拦截器已提示 */
  }
}

function goBots() {
  router.push({ name: "bots" });
}

onMounted(() => {
  loadBots();
  connectMonitor();
});

onBeforeUnmount(() => {
  if (ws) ws.close();
  if (chart) chart.dispose();
});
</script>

<style scoped>
.grid {
  display: grid;
  gap: 16px;
  margin-bottom: 16px;
}

.cards {
  grid-template-columns: repeat(4, 1fr);
}

.charts {
  grid-template-columns: 1.6fr 1fr;
}

@media (max-width: 1100px) {
  .cards,
  .charts {
    grid-template-columns: repeat(2, 1fr);
  }
}

.stat-label {
  color: var(--nb-text-secondary);
  font-size: 13px;
  margin-bottom: 8px;
}

.stat-value {
  font-size: 30px;
  font-weight: 700;
  margin-bottom: 10px;
  color: var(--nb-orange);
}

.stat-value .unit {
  font-size: 13px;
  font-weight: 400;
  color: var(--nb-text-secondary);
  margin-left: 6px;
}

.chart-card {
  min-height: 300px;
}

.chart-title {
  font-size: 15px;
  font-weight: 600;
  margin-bottom: 12px;
}

.chart {
  height: 240px;
}

.info-rows {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.info-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  font-size: 13px;
}

.info-row span {
  color: var(--nb-text-secondary);
  flex-shrink: 0;
}

.info-row b {
  font-weight: 500;
  text-align: right;
}

.ellipsis {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-head .chart-title {
  margin-bottom: 0;
}

.bot-link {
  color: var(--nb-orange);
  font-weight: 500;
}

.bot-link:hover {
  text-decoration: underline;
}
</style>
