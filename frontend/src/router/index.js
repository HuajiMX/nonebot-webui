import { createRouter, createWebHistory } from "vue-router";
import { useAuthStore } from "../stores/auth";

const routes = [
  {
    path: "/setup",
    name: "setup",
    component: () => import("../views/SetupView.vue"),
    meta: { public: true },
  },
  {
    path: "/login",
    name: "login",
    component: () => import("../views/LoginView.vue"),
    meta: { public: true },
  },
  {
    path: "/",
    component: () => import("../layouts/MainLayout.vue"),
    children: [
      { path: "", name: "dashboard", component: () => import("../views/DashboardView.vue") },
      { path: "bots", name: "bots", component: () => import("../views/BotsView.vue") },
      { path: "bots/:id", name: "bot-detail", component: () => import("../views/BotDetailView.vue"), props: true },
      { path: "visual-plugins", name: "visual-plugins", component: () => import("../views/VisualPluginsView.vue") },
      {
        path: "visual-plugins/:id",
        name: "visual-plugin-editor",
        component: () => import("../views/VisualPluginEditor.vue"),
        props: (route) => ({ pluginId: route.params.id }),
      },
      { path: "settings", name: "settings", component: () => import("../views/SettingsView.vue") },
    ],
  },
  { path: "/:pathMatch(.*)*", redirect: "/" },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

router.beforeEach(async (to) => {
  if (to.meta.public) return true;
  const auth = useAuthStore();
  await auth.init();
  if (!auth.initialized) {
    return { name: "setup" };
  }
  if (!auth.username) {
    return { name: "login", query: { redirect: to.fullPath } };
  }
  return true;
});

export default router;
