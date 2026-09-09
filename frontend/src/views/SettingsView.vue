<template>
  <div class="page">
    <h2 class="page-title">系统设置</h2>

    <div class="settings-grid">
      <div class="card">
        <h3 class="block-title">修改密码</h3>
        <el-form :model="form" label-width="110px" style="max-width: 420px">
          <el-form-item label="当前密码">
            <el-input v-model="form.old_password" type="password" show-password />
          </el-form-item>
          <el-form-item label="新密码">
            <el-input v-model="form.new_password" type="password" show-password />
          </el-form-item>
          <el-form-item label="确认新密码">
            <el-input v-model="form.confirm" type="password" show-password />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" :loading="saving" @click="save">保存</el-button>
          </el-form-item>
        </el-form>
      </div>

      <div class="card update-card">
        <h3 class="block-title update-title">
          <span>版本更新</span>
          <el-tag
            v-if="updateStore.latest && !updateStore.checking"
            :type="updateStore.hasUpdate ? 'danger' : 'success'"
            size="small"
            effect="light"
            round
          >
            {{ updateStore.hasUpdate ? `发现新版本 v${updateStore.latest}` : "已是最新版本" }}
          </el-tag>
        </h3>

        <div class="version-row">
          <div class="version-item">
            <span class="version-label">当前版本</span>
            <span class="version-value">v{{ updateStore.current || "-" }}</span>
          </div>
          <el-icon class="version-arrow"><ArrowRight /></el-icon>
          <div class="version-item">
            <span class="version-label">最新版本</span>
            <span class="version-value" :class="{ newest: updateStore.hasUpdate }">
              {{ updateStore.checking ? "检查中…" : (updateStore.latest ? `v${updateStore.latest}` : "-") }}
            </span>
          </div>
        </div>

        <div v-if="updateStore.hasUpdate && updateStore.notes" class="update-notes">{{ updateStore.notes }}</div>

        <div class="update-actions">
          <el-button :loading="updateStore.checking" @click="checkUpdate">
            <el-icon v-if="!updateStore.checking"><Refresh /></el-icon>
            <span>检测更新</span>
          </el-button>
          <el-button v-if="updateStore.hasUpdate" type="primary" :loading="updating" @click="startUpdate">
            <el-icon v-if="!updating"><Download /></el-icon>
            <span>立即更新</span>
          </el-button>
        </div>
      </div>
    </div>

    <div class="card email-card">
      <h3 class="block-title">邮件通知</h3>
      <p class="muted email-desc">
        配置 SMTP 服务后，WebUI 可在机器人 QQ 断连、进程异常退出时发送系统通知；可视化插件的「发送邮件」组件也会复用此配置。
      </p>
      <el-form :model="email" label-width="120px" class="email-form">
        <el-form-item label="启用邮件通知">
          <el-switch v-model="email.enabled" />
          <span class="muted switch-hint">关闭后仍可使用「发送测试邮件」与插件发信</span>
        </el-form-item>

        <div class="email-grid">
          <el-form-item label="SMTP 服务器">
            <el-input v-model="email.host" placeholder="例如：smtp.qq.com" />
          </el-form-item>
          <el-form-item label="端口">
            <el-input-number v-model="email.port" :min="1" :max="65535" style="width: 100%" />
          </el-form-item>
          <el-form-item label="加密方式">
            <el-select v-model="email.security" style="width: 100%" @change="onSecurityChange">
              <el-option label="SSL（常用，465）" value="ssl" />
              <el-option label="STARTTLS（常用，587）" value="starttls" />
              <el-option label="不加密" value="none" />
            </el-select>
          </el-form-item>
          <el-form-item label="用户名">
            <el-input v-model="email.username" placeholder="通常是完整邮箱地址" />
          </el-form-item>
          <el-form-item label="密码 / 授权码">
            <el-input
              v-model="email.password"
              type="password"
              show-password
              @focus="onPasswordFocus"
              placeholder="邮箱授权码 / 登录密码（留空保留原密码）"
            />
          </el-form-item>
          <el-form-item label="发件人地址">
            <el-input v-model="email.from_addr" placeholder="留空则使用用户名" />
          </el-form-item>
          <el-form-item label="发件人名称">
            <el-input v-model="email.from_name" placeholder="NoneBot2 WebUI" />
          </el-form-item>
          <el-form-item label="超时（秒）">
            <el-input-number v-model="email.timeout" :min="3" :max="120" style="width: 100%" />
          </el-form-item>
        </div>

        <el-form-item label="通知收件邮箱">
          <el-input
            v-model="email.recipients"
            type="textarea"
            :rows="2"
            placeholder="系统通知的收件邮箱，多个用逗号、分号或换行分隔"
          />
        </el-form-item>

        <el-form-item>
          <el-button type="primary" :loading="emailSaving" @click="saveEmail">保存邮件配置</el-button>
          <el-button :loading="emailTesting" @click="testEmail">发送测试邮件</el-button>
        </el-form-item>
      </el-form>
    </div>

    <div class="card">
      <h3 class="block-title">关于</h3>
      <p class="muted" style="line-height: 1.8">
        NoneBot2 WebUI 是一个面向 NoneBot2 的网页管理面板，支持机器人创建与管理、插件启停与安装、实时日志、
        内置终端与服务器监控。
      </p>
    </div>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import api from "../api";
import { useUpdateStore } from "../stores/update";

const form = reactive({ old_password: "", new_password: "", confirm: "" });
const saving = ref(false);
const updating = ref(false);
const updateStore = useUpdateStore();

const email = reactive({
  enabled: false,
  host: "",
  port: 465,
  security: "ssl",
  username: "",
  password: "",
  from_addr: "",
  from_name: "NoneBot2 WebUI",
  recipients: "",
  timeout: 15,
});
const emailSaving = ref(false);
const emailTesting = ref(false);
const PASSWORD_MASK = "******";

async function save() {
  if (!form.old_password || !form.new_password) {
    ElMessage.warning("请填写完整");
    return;
  }
  if (form.new_password.length < 6) {
    ElMessage.warning("新密码至少 6 位");
    return;
  }
  if (form.new_password !== form.confirm) {
    ElMessage.warning("两次输入的新密码不一致");
    return;
  }
  saving.value = true;
  try {
    await api.post("/auth/password", {
      old_password: form.old_password,
      new_password: form.new_password,
    });
    ElMessage.success("密码已修改，请重新登录");
    form.old_password = form.new_password = form.confirm = "";
  } catch {
    /* ignore */
  } finally {
    saving.value = false;
  }
}

async function checkUpdate() {
  try {
    const info = await updateStore.check(true);
    if (info.has_update) {
      ElMessage.success(`发现新版本 v${info.latest}`);
    } else if (info.latest) {
      ElMessage.success("当前已是最新版本");
    } else {
      ElMessage.warning("检查更新失败，请稍后重试");
    }
  } catch {
    ElMessage.error("检查更新失败");
  }
}

async function startUpdate() {
  updating.value = true;
  try {
    const res = await updateStore.startUpdate();
    if (res && res.started) {
      ElMessage.success(res.detail || "更新已开始");
    }
  } catch {
    /* ignore，失败状态由更新对话框展示 */
  } finally {
    updating.value = false;
  }
}

function splitRecipients(value) {
  return (value || "")
    .split(/[,;\s]+/)
    .map((x) => x.trim())
    .filter(Boolean);
}

function emailPayload() {
  return {
    enabled: email.enabled,
    host: email.host,
    port: email.port,
    security: email.security,
    username: email.username,
    password: email.password,
    from_addr: email.from_addr,
    from_name: email.from_name,
    recipients: splitRecipients(email.recipients),
    timeout: email.timeout,
  };
}

async function loadEmail() {
  try {
    const data = await api.get("/settings/email");
    email.enabled = !!data.enabled;
    email.host = data.host || "";
    email.port = data.port || 465;
    email.security = data.security || "ssl";
    email.username = data.username || "";
    email.password = data.password || "";
    email.from_addr = data.from_addr || "";
    email.from_name = data.from_name || "NoneBot2 WebUI";
    email.recipients = (data.recipients || []).join(", ");
    email.timeout = data.timeout || 15;
  } catch {
    /* 拦截器已提示错误 */
  }
}

function onSecurityChange(value) {
  const defaults = { ssl: 465, starttls: 587, none: 25 };
  if ([465, 587, 25].includes(email.port)) {
    email.port = defaults[value] || email.port;
  }
}

function onPasswordFocus(event) {
  // 聚焦时全选掩码，直接输入即可替换，避免把新密码追加到掩码后面
  if (email.password === PASSWORD_MASK) {
    event.target?.select?.();
  }
}

async function saveEmail() {
  emailSaving.value = true;
  try {
    const data = await api.put("/settings/email", emailPayload());
    email.password = data.password || "";
    email.recipients = (data.recipients || []).join(", ");
    ElMessage.success("邮件配置已保存");
  } catch {
    /* 拦截器已提示错误 */
  } finally {
    emailSaving.value = false;
  }
}

async function testEmail() {
  emailTesting.value = true;
  try {
    const data = await api.post("/settings/email/test", {
      to: splitRecipients(email.recipients),
      config: emailPayload(),
    });
    ElMessage.success(`测试邮件已发送至：${(data.recipients || []).join("、")}`);
  } catch {
    /* 拦截器已提示错误 */
  } finally {
    emailTesting.value = false;
  }
}

onMounted(async () => {
  await loadEmail();
  try {
    await updateStore.check();
  } catch {
    /* ignore */
  }
});
</script>

<style scoped>
.settings-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-bottom: 16px;
}

@media (max-width: 1100px) {
  .settings-grid {
    grid-template-columns: 1fr;
  }
}

.email-card {
  margin-bottom: 16px;
}

.email-desc {
  margin: -4px 0 18px;
  line-height: 1.7;
}

.email-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0 24px;
}

@media (max-width: 900px) {
  .email-grid {
    grid-template-columns: 1fr;
  }
}

.switch-hint {
  margin-left: 12px;
  font-size: 12px;
}

.block-title {
  margin: 0 0 16px;
  font-size: 16px;
}

.settings-grid .card {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.settings-grid .card .el-form {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.settings-grid .card .el-form .el-form-item:last-child {
  margin-top: auto;
}

.update-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}

.version-row {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 14px 16px;
  background: var(--nb-gray);
  border-radius: 10px;
}

.version-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 130px;
}

.version-label {
  font-size: 12px;
  color: var(--nb-text-secondary);
}

.version-value {
  font-size: 20px;
  font-weight: 600;
  color: var(--nb-text);
}

.version-value.newest {
  color: var(--nb-orange);
}

.version-arrow {
  color: #c0c4cc;
  font-size: 16px;
}

.update-actions {
  margin-top: auto;
  padding-top: 14px;
  display: flex;
  gap: 10px;
}

.update-actions .el-button + .el-button {
  margin-left: 0;
}

.update-notes {
  margin-top: 12px;
  padding: 10px 12px 10px 14px;
  background: #fafafa;
  border-left: 3px solid var(--nb-orange);
  border-radius: 0 8px 8px 0;
  font-size: 12.5px;
  color: var(--nb-text);
  white-space: pre-line;
  max-height: 96px;
  overflow: auto;
  line-height: 1.6;
}
</style>
