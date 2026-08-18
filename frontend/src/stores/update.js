import { defineStore } from "pinia";
import api from "../api";

async function fetchRaw(path) {
  try {
    const resp = await fetch(path);
    if (!resp.ok) return null;
    return await resp.json();
  } catch {
    return null;
  }
}

export const useUpdateStore = defineStore("update", {
  state: () => ({
    current: "",
    latest: "",
    hasUpdate: false,
    notes: "",
    checking: false,
    // 更新进度
    visible: false,
    phase: "running", // running | done | failed
    lines: [],
    baseline: 0,
    pollTimers: [],
  }),
  actions: {
    async check(force = false) {
      this.checking = true;
      try {
        const info = await api.get(`/update/status${force ? "?force=true" : ""}`);
        this.current = info.current || this.current;
        this.latest = info.latest || "";
        this.hasUpdate = !!info.has_update;
        this.notes = info.notes || "";
        return info;
      } finally {
        this.checking = false;
      }
    },
    async startUpdate() {
      this.baseline = 0;
      const pre = await fetchRaw("/api/update/log");
      if (pre && pre.lines) this.baseline = pre.lines.length;
      this.lines = [];
      this.phase = "running";
      this.visible = true;
      this.stopPolling();
      this.pollTimers.push(setInterval(() => this.pollLog(), 1500));
      try {
        const res = await api.post("/update");
        if (!res.started) {
          this.finish(true);
          this.lines = [res.detail || "当前已是最新版本"];
        }
        return res;
      } catch (err) {
        this.finish(false);
        throw err;
      }
    },
    async pollLog() {
      const data = await fetchRaw("/api/update/log");
      if (!data) {
        // 服务已停止或会话失效：健康检查可用说明新服务已起来
        if (await fetchRaw("/api/health")) this.finish(true);
        return;
      }
      this.lines = (data.lines || []).slice(this.baseline);
      if (data.state === "failed") this.finish(false);
      else if (data.state === "done") this.finish(true);
    },
    finish(ok) {
      this.phase = ok ? "done" : "failed";
      this.stopPolling();
    },
    stopPolling() {
      this.pollTimers.forEach((t) => clearInterval(t));
      this.pollTimers = [];
    },
  },
});
