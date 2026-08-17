import axios from "axios";
import { ElMessage } from "element-plus";
import router from "../router";

const api = axios.create({
  baseURL: "/api",
  timeout: 30000,
});

api.interceptors.response.use(
  (resp) => resp.data,
  (err) => {
    const detail = err.response?.data?.detail;
    if (err.response?.status === 401) {
      router.push({ name: "login", query: { redirect: router.currentRoute.value.fullPath } });
    } else if (detail) {
      ElMessage.error(typeof detail === "string" ? detail : "请求失败");
    } else if (!err.response) {
      ElMessage.error("网络错误，请检查服务是否启动");
    } else {
      ElMessage.error("请求失败");
    }
    return Promise.reject(err);
  }
);

export const wsUrl = (path, query = {}) => {
  const token = localStorage.getItem("nb_token") || "";
  const params = new URLSearchParams(query);
  if (token) params.set("token", token);
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  const qs = params.toString();
  return `${proto}//${location.host}${path}${qs ? `?${qs}` : ""}`;
};

export default api;
