<template>
  <div class="auth-page">
    <div class="auth-card">
      <div class="auth-brand">
        <div class="logo">NB</div>
        <h1>初始化系统</h1>
        <p>首次使用，请设置管理员账号</p>
      </div>
      <el-form @submit.prevent="onSetup" class="auth-form">
        <el-form-item>
          <el-input v-model="form.username" size="large" placeholder="管理员用户名" :prefix-icon="User" />
        </el-form-item>
        <el-form-item>
          <el-input
            v-model="form.password"
            type="password"
            size="large"
            placeholder="密码（至少 6 位）"
            show-password
            :prefix-icon="Lock"
          />
        </el-form-item>
        <el-form-item>
          <el-input
            v-model="form.confirm"
            type="password"
            size="large"
            placeholder="确认密码"
            show-password
            :prefix-icon="Lock"
            @keyup.enter="onSetup"
          />
        </el-form-item>
        <el-button type="primary" size="large" class="login-btn" :loading="loading" @click="onSetup">
          完成初始化
        </el-button>
      </el-form>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { Lock, User } from "@element-plus/icons-vue";
import { useAuthStore } from "../stores/auth";

const auth = useAuthStore();
const router = useRouter();
const loading = ref(false);
const form = reactive({ username: "", password: "", confirm: "" });

async function onSetup() {
  if (!form.username) {
    ElMessage.warning("请输入用户名");
    return;
  }
  if (form.password.length < 6) {
    ElMessage.warning("密码至少 6 位");
    return;
  }
  if (form.password !== form.confirm) {
    ElMessage.warning("两次输入的密码不一致");
    return;
  }
  loading.value = true;
  try {
    await auth.setup(form.username, form.password);
    ElMessage.success("初始化完成");
    router.push("/");
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
</style>
