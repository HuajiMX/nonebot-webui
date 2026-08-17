import { defineStore } from "pinia";
import api from "../api";

export const useAuthStore = defineStore("auth", {
  state: () => ({
    username: localStorage.getItem("nb_username") || "",
    initialized: true,
  }),
  actions: {
    async init() {
      try {
        const status = await api.get("/auth/status");
        this.initialized = status.initialized;
      } catch {
        this.initialized = true;
      }
      if (this.initialized) {
        try {
          const me = await api.get("/auth/me");
          this.username = me.username;
          localStorage.setItem("nb_username", me.username);
        } catch {
          this.username = "";
          localStorage.removeItem("nb_username");
        }
      }
    },
    async login(username, password) {
      const data = await api.post("/auth/login", { username, password });
      this.username = data.username;
      this.initialized = true;
      localStorage.setItem("nb_username", data.username);
    },
    async setup(username, password) {
      await api.post("/auth/setup", { username, password });
      this.username = username;
      this.initialized = true;
      localStorage.setItem("nb_username", username);
    },
    async logout() {
      try {
        await api.post("/auth/logout");
      } finally {
        this.username = "";
        localStorage.removeItem("nb_username");
      }
    },
  },
});
