<template>
  <el-tag :type="tagType" size="small" effect="light" round>
    <span class="dot" :style="{ background: dotColor }"></span>
    {{ label }}
  </el-tag>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
  status: { type: String, default: "stopped" },
});

const map = {
  running: { label: "运行中", type: "success", dot: "#67c23a" },
  starting: { label: "启动中", type: "warning", dot: "#e6a23c" },
  creating: { label: "创建中", type: "warning", dot: "#e6a23c" },
  stopping: { label: "停止中", type: "warning", dot: "#e6a23c" },
  stopped: { label: "已停止", type: "info", dot: "#909399" },
  error: { label: "异常", type: "danger", dot: "#f56c6c" },
};

const cfg = computed(() => map[props.status] || map.stopped);
const label = computed(() => cfg.value.label);
const tagType = computed(() => cfg.value.type);
const dotColor = computed(() => cfg.value.dot);
</script>

<style scoped>
.dot {
  display: inline-block;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  margin-right: 5px;
}
</style>
