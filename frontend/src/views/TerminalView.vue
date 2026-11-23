<template>
  <div class="page">
    <div class="card term-card">
      <div class="term-card-head">
        <h3 class="block-title">系统终端</h3>
        <span class="muted">服务所在主机的普通终端，工作目录为用户主目录</span>
      </div>
      <TerminalPanel mode="system" height="calc(100vh - 245px)" />
    </div>
  </div>
</template>

<script setup>
import TerminalPanel from "../components/TerminalPanel.vue";
</script>

<style scoped>
.term-card {
  display: flex;
  flex-direction: column;
}

.term-card-head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-bottom: 10px;
}

.block-title {
  margin: 0;
  font-size: 16px;
}
</style>
