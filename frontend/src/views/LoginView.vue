<template>
  <div class="auth-page">
    <div class="auth-card">
      <div class="auth-brand">
        <div class="logo">NB</div>
        <h1>NoneBot2 WebUI</h1>
        <p>机器人管理 · 插件管理 · 内置终端 · 服务器监控</p>
      </div>
      <el-form @submit.prevent="onLogin" class="auth-form">
        <el-form-item>
          <el-input
            v-model="form.username"
            size="large"
            placeholder="用户名"
            :prefix-icon="User"
          />
        </el-form-item>
        <el-form-item>
          <el-input
            v-model="form.password"
            type="password"
            size="large"
            placeholder="密码"
            show-password
            :prefix-icon="Lock"
            @keyup.enter="onLogin"
          />
        </el-form-item>
        <el-button
          type="primary"
          size="large"
          class="login-btn"
          :loading="loading"
          @click="onLogin"
        >
          登 录
        </el-button>
      </el-form>
      <div class="auth-tip">首次使用请在安装时设置管理员账号，或在系统设置中初始化</div>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { Lock, User } from "@element-plus/icons-vue";
import { useAuthStore } from "../stores/auth";

const auth = useAuthStore();
const router = useRouter();
const route = useRoute();
const loading = ref(false);
const form = reactive({ username: "", password: "" });

async function onLogin() {
  if (!form.username || !form.password) {
    ElMessage.warning("请输入用户名和密码");
    return;
  }
  loading.value = true;
  try {
    await auth.login(form.username, form.password);
    router.push(route.query.redirect || "/");
  } catch {
    /* 拦截器已提示 */
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped>
.auth-page {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #fff 0%, #fdeeee 55%, #f7d7d7 100%);
}

.auth-card {
  width: 400px;
  background: #fff;
  border-radius: 16px;
  padding: 40px 36px 28px;
  box-shadow: 0 12px 40px rgba(234, 82, 82, 0.12);
}

.auth-brand {
  text-align: center;
  margin-bottom: 28px;
}

.logo {
  width: 54px;
  height: 54px;
  border-radius: 14px;
  background: var(--nb-orange);
  color: #fff;
  font-size: 22px;
  font-weight: 700;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.auth-brand h1 {
  margin: 14px 0 6px;
  font-size: 22px;
}

.auth-brand p {
  margin: 0;
  color: var(--nb-text-secondary);
  font-size: 13px;
}

.login-btn {
  width: 100%;
  margin-top: 4px;
}

.auth-tip {
  margin-top: 18px;
  text-align: center;
  font-size: 12px;
  color: var(--nb-text-secondary);
}
</style>
