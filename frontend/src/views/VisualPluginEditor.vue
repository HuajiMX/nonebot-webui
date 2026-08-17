<template>
  <div class="editor-page">
    <div class="editor-head">
      <div class="editor-title">
        <el-button text :icon="ArrowLeft" @click="$router.push('/visual-plugins')">返回</el-button>
        <el-input v-model="plugin.name" class="name-input" size="large" placeholder="插件名称" />
        <el-input v-model="plugin.description" class="desc-input" placeholder="插件描述（可选）" />
      </div>
      <div class="editor-actions">
        <span v-if="dirty" class="muted">有未保存的修改</span>
        <el-button :loading="saving" @click="save">保存</el-button>
        <el-button type="primary" :loading="updating" @click="updatePlugins">更新插件</el-button>
      </div>
    </div>

    <div v-loading="loading" class="editor-body">
      <!-- 组件面板 -->
      <aside class="palette">
        <div class="palette-title">组件</div>
        <div v-for="group in paletteGroups" :key="group.cat" class="palette-group">
          <div class="palette-group-label">{{ group.label }}</div>
          <div
            v-for="item in group.items"
            :key="item.type"
            class="palette-item"
            :class="group.cat"
            draggable="true"
            @dragstart="onPaletteDragStart(item.type, $event)"
            @dblclick="addNodeAtCenter(item.type)"
          >
            <el-icon :size="16"><component :is="iconMap[item.type]" /></el-icon>
            <span>{{ item.label }}</span>
          </div>
        </div>
        <div class="palette-tip">拖入画布或双击添加</div>
      </aside>

      <!-- 画布 -->
      <div class="canvas-wrap">
        <div class="canvas-toolbar">
          <span class="canvas-hint">拖拽空白处平移画布 · 鼠标滚轮缩放（上滚放大） · 节点可拖动</span>
        </div>

        <div
          ref="canvasRef"
          class="canvas"
          :class="{ panning }"
          @pointerdown="onCanvasPointerDown"
          @click="onCanvasClick"
          @drop="onCanvasDrop"
          @wheel.prevent="onCanvasWheel"
          @dragover.prevent
        >
          <div
            class="world"
            :style="worldStyle"
          >
            <svg class="edges" :style="edgeStyle" :viewBox="edgeViewBox">
              <template v-for="line in pairLines" :key="line.key">
                <path :d="line.d" class="pair-line" />
              </template>
              <template v-for="edge in edgePaths" :key="edge.key">
                <path :d="edge.d" class="edge-line" :class="[edge.port, { selected: edge.key === edgeSelectedKey }]" />
                <path :d="edge.d" class="edge-hit" @click="selectEdge(edge)" />
                <g @click="selectEdge(edge)">
                  <circle
                    :cx="edge.mx"
                    :cy="edge.my"
                    r="7"
                    class="edge-dot"
                    :class="[edge.port, { selected: edge.key === edgeSelectedKey }]"
                  />
                  <text :x="edge.mx" :y="edge.my - 10" class="edge-label">{{ edge.portLabel }}</text>
                </g>
                <g v-if="edge.key === edgeSelectedKey" @click.stop="deleteEdge(edge)">
                  <circle :cx="edge.mx" :cy="edge.my" r="9" class="edge-del-bg" />
                  <text :x="edge.mx" :y="edge.my + 4" class="edge-del-x">×</text>
                </g>
              </template>
              <path
                v-if="tempConn"
                :d="tempPath"
                class="edge-line next temp"
              />
            </svg>

            <div
              v-for="node in flow.nodes"
              :key="node.id"
              class="node-card"
              :class="[node.type, { selected: node.id === selectedId }]"
              :data-id="node.id"
              :style="{ left: node.x + 'px', top: node.y + 'px' }"
              @click.stop="selectedId = node.id; edgeSelectedKey = null"
              @pointerdown="onNodePointerDown(node, $event)"
            >
              <div class="port-in" title="连接到此处" @pointerdown.stop @click.stop></div>
              <div class="node-head">
                <el-icon :size="15" class="node-icon">
                  <component :is="iconMap[node.type]" />
                </el-icon>
                <span class="node-type">{{ nodeLabel(node.type) }}</span>
              </div>
              <div class="node-summary">{{ nodeSummary(node) }}</div>
              <div
                v-for="port in outPorts(node)"
                :key="port.port"
                class="port-out"
                :class="port.port"
                :style="port.style"
                :title="port.title"
                @pointerdown.stop="onPortOutPointerDown(node, port.port, $event)"
              >
                {{ port.label }}
              </div>
            </div>
          </div>

          <div v-if="flow.nodes.length === 0" class="canvas-empty">
            从左侧拖入「监听对象」开始搭建流程
          </div>
        </div>

        <!-- 可用变量 -->
        <div class="var-bar">
          <span class="var-bar-label">可用变量</span>
          <el-tooltip v-for="v in availableVars" :key="v.name" :content="v.desc" placement="top">
            <span
              class="var-pill"
              draggable="true"
              @dragstart="onVarDragStart(v.name, $event)"
              @dblclick="insertVar(v.name)"
            >
              {{ v.name }}
            </span>
          </el-tooltip>
          <span class="var-tip">拖入输入框，或双击插入到最近聚焦的输入框</span>
        </div>
      </div>

      <!-- 配置面板 -->
      <aside class="config-panel">
        <div class="config-title">配置</div>
        <template v-if="selectedNode">
          <div class="config-node-name">
            <b>{{ nodeLabel(selectedNode.type) }}</b>
            <el-button size="small" type="danger" plain @click="removeNode(selectedNode.id)">删除节点</el-button>
          </div>

          <!-- 监听 -->
          <template v-if="selectedNode.type.startsWith('listener_')">
            <el-form label-position="top" size="small">
              <el-form-item label="监听类型">
                <el-select v-model="selectedNode.config.listener_type" style="width: 100%">
                  <el-option label="群聊" value="group" />
                  <el-option label="私信" value="private" />
                  <el-option label="WebHook" value="webhook" />
                </el-select>
              </el-form-item>
              <template v-if="selectedNode.config.listener_type === 'group'">
                <el-form-item label="指定群号（留空=全部，多个用逗号分隔）">
                  <el-input v-model="selectedNode.config.groups" placeholder="例如：123456,789012" />
                </el-form-item>
                <el-form-item label="触发条件">
                  <el-switch v-model="selectedNode.config.at_me" active-text="仅当@我时触发" />
                </el-form-item>
              </template>
              <template v-else-if="selectedNode.config.listener_type === 'private'">
                <el-form-item label="指定QQ号（留空=全部，多个用逗号分隔）">
                  <el-input v-model="selectedNode.config.users" placeholder="例如：10001,10002" />
                </el-form-item>
              </template>
              <template v-else>
                <el-form-item label="WebHook 路径">
                  <el-input v-model="selectedNode.config.path" placeholder="/webhook/xxx" />
                </el-form-item>
                <el-form-item label="保存到变量（请求体）">
                  <el-input v-model="selectedNode.config.var" placeholder="webhook" />
                </el-form-item>
              </template>
              <template v-if="selectedNode.config.listener_type !== 'webhook'">
                <el-form-item label="触发关键词（留空=任意消息，多个用逗号分隔）">
                  <el-input v-model="selectedNode.config.keywords" placeholder="例如：你好,在吗" />
                </el-form-item>
                <el-form-item label="匹配方式">
                  <el-select v-model="selectedNode.config.match" style="width: 100%">
                    <el-option label="包含关键词" value="contains" />
                    <el-option label="以关键词开头" value="starts_with" />
                    <el-option label="正则匹配" value="regex" />
                  </el-select>
                </el-form-item>
              </template>
            </el-form>
          </template>

          <!-- 条件判断（与/或/非） -->
          <template v-else-if="selectedNode.type === 'logic'">
            <el-form label-position="top" size="small">
              <el-form-item label="组合方式">
                <el-select v-model="selectedNode.config.combine" style="width: 100%">
                  <el-option label="全部满足（且）" value="and" />
                  <el-option label="任一满足（或）" value="or" />
                </el-select>
              </el-form-item>
              <el-form-item label="取反">
                <el-switch v-model="selectedNode.config.negate" active-text="结果取反" />
              </el-form-item>
              <div class="sub-label">条件列表（左值支持 {{变量}}）</div>
              <div v-for="(cond, idx) in selectedNode.config.conditions" :key="idx" class="cond-row">
                <el-input v-model="cond.left" v-var-drop placeholder="左值" />
                <el-select v-model="cond.op" style="width: 132px">
                  <el-option v-for="(label, op) in catalog.condition_ops" :key="op" :label="label" :value="op" />
                </el-select>
                <el-input v-if="!isEmptyOp(cond.op)" v-model="cond.right" v-var-drop placeholder="右值" />
                <el-button text type="danger" :icon="Delete" @click="selectedNode.config.conditions.splice(idx, 1)" />
              </div>
              <el-button size="small" :icon="Plus" @click="selectedNode.config.conditions.push({ left: '', op: 'contains', right: '' })">
                添加条件
              </el-button>
            </el-form>
          </template>

          <!-- 循环 -->
          <template v-else-if="selectedNode.type === 'loop'">
            <el-form label-position="top" size="small">
              <el-form-item label="遍历列表（{{变量}} 或表达式）">
                <el-input v-model="selectedNode.config.items" v-var-drop placeholder="例如：{{segments}} 或 [1,2,3]" />
              </el-form-item>
              <el-form-item label="元素变量名">
                <el-input v-model="selectedNode.config.var" placeholder="item" />
              </el-form-item>
              <el-form-item label="循环结束节点">
                <el-input :model-value="loopEndName(selectedNode)" disabled />
              </el-form-item>
            </el-form>
          </template>

          <!-- API请求 -->
          <template v-else-if="selectedNode.type === 'api'">
            <el-form label-position="top" size="small">
              <el-form-item label="请求方式">
                <el-select v-model="selectedNode.config.method" style="width: 100%">
                  <el-option v-for="m in ['GET', 'POST', 'PUT', 'DELETE', 'PATCH']" :key="m" :label="m" :value="m" />
                </el-select>
              </el-form-item>
              <el-form-item label="URL（支持 {{变量}}）">
                <el-input v-model="selectedNode.config.url" v-var-drop placeholder="https://api.example.com/data" />
              </el-form-item>
              <el-form-item label="请求头（值支持 {{变量}}）">
                <div v-for="(h, idx) in selectedNode.config.headers" :key="idx" class="cond-row">
                  <el-input v-model="h.key" placeholder="名称" />
                  <el-input v-model="h.value" v-var-drop placeholder="值" />
                  <el-button text type="danger" :icon="Delete" @click="selectedNode.config.headers.splice(idx, 1)" />
                </div>
                <el-button size="small" :icon="Plus" @click="selectedNode.config.headers.push({ key: '', value: '' })">
                  添加请求头
                </el-button>
              </el-form-item>
              <el-form-item label="请求体（JSON 以 { 或 [ 开头，支持 {{变量}}）">
                <el-input
                  v-model="selectedNode.config.body"
                  v-var-drop
                  type="textarea"
                  :rows="4"
                  placeholder='例如：{"question": "{{msg}}"}'
                />
              </el-form-item>
              <el-form-item label="保存到变量（响应）">
                <el-input v-model="selectedNode.config.var" placeholder="api_resp" />
              </el-form-item>
              <el-form-item label="超时（秒）">
                <el-input-number v-model="selectedNode.config.timeout" :min="1" :max="120" style="width: 100%" />
              </el-form-item>
              <el-alert type="info" :closable="false">
                响应存入变量：<code>status</code> 状态码、<code>data</code> 解析后的 JSON、<code>text</code> 原文、<code>headers</code> 响应头
              </el-alert>
            </el-form>
          </template>

          <!-- 定时任务 -->
          <template v-else-if="selectedNode.type === 'schedule'">
            <el-form label-position="top" size="small">
              <el-form-item label="触发模式">
                <el-select v-model="selectedNode.config.mode" style="width: 100%">
                  <el-option label="间隔触发（每隔多久触发一次）" value="interval" />
                  <el-option label="每天定点触发" value="daily" />
                  <el-option label="每周定点触发" value="weekly" />
                  <el-option label="每月定点触发" value="monthly" />
                </el-select>
              </el-form-item>
              <el-form-item v-if="selectedNode.config.mode === 'interval'" label="间隔（秒）">
                <el-input-number v-model="selectedNode.config.interval" :min="1" :max="86400" style="width: 100%" />
              </el-form-item>
              <template v-else>
                <el-form-item label="触发时间">
                  <el-time-select
                    v-model="selectedNode.config.time"
                    start="00:00"
                    end="23:30"
                    step="00:30"
                    placeholder="选择时间"
                    style="width: 100%"
                  />
                </el-form-item>
                <el-form-item v-if="selectedNode.config.mode === 'weekly'" label="星期几">
                  <el-select v-model="selectedNode.config.weekday" style="width: 100%">
                    <el-option v-for="(label, i) in weekdays" :key="i" :label="label" :value="i" />
                  </el-select>
                </el-form-item>
                <el-form-item v-else-if="selectedNode.config.mode === 'monthly'" label="每月几号">
                  <el-input-number v-model="selectedNode.config.day" :min="1" :max="31" style="width: 100%" />
                </el-form-item>
              </template>
            </el-form>
          </template>

          <!-- 自定义代码 -->
          <template v-else-if="selectedNode.type === 'code'">
            <el-form label-position="top" size="small">
              <el-form-item label="Python 代码">
                <el-input
                  v-model="selectedNode.config.code"
                  v-var-drop
                  type="textarea"
                  :rows="10"
                  class="code-input"
                  placeholder="可直接使用：msg、segments、sender、user_id、group_id、system、ctx、bot、event"
                />
              </el-form-item>
              <el-alert type="info" :closable="false">
                可用变量：<code>msg</code> <code>segments</code> <code>sender</code> <code>user_id</code>
                <code>group_id</code> <code>system</code> <code>bot</code> <code>event</code> <code>ctx</code>
                <code>reply</code> <code>webhook</code>；向 <code>ctx</code> 写入的值可在后续节点用
                <code>{{ varHint }}</code> 引用。
              </el-alert>
            </el-form>
          </template>

          <!-- 发送消息 -->
          <template v-else-if="selectedNode.type === 'send'">
            <el-form label-position="top" size="small">
              <el-form-item label="发送方式">
                <el-select v-model="selectedNode.config.mode" style="width: 100%">
                  <el-option label="发送消息并结束流程" value="finish" />
                  <el-option label="发送消息但继续流程" value="continue" />
                </el-select>
              </el-form-item>
              <el-form-item label="发送目标">
                <el-select v-model="selectedNode.config.target.type" style="width: 100%">
                  <el-option label="回复触发者" value="event" />
                  <el-option label="指定群聊" value="group" />
                  <el-option label="指定私聊" value="user" />
                </el-select>
              </el-form-item>
              <el-form-item v-if="selectedNode.config.target.type !== 'event'" :label="selectedNode.config.target.type === 'group' ? '群号' : 'QQ号'">
                <el-input v-model="selectedNode.config.target.id" placeholder="留空则使用当前消息来源" />
              </el-form-item>
              <div class="sub-label">消息内容（内容支持 {{变量}}）</div>
              <div v-for="(seg, idx) in selectedNode.config.messages" :key="idx" class="msg-row">
                <el-select v-model="seg.type" style="width: 120px">
                  <el-option v-for="(label, t) in catalog.message_types" :key="t" :label="label" :value="t" />
                </el-select>
                <el-input v-model="seg.value" v-var-drop :placeholder="segPlaceholder(seg.type)" />
                <el-button text type="danger" :icon="Delete" @click="selectedNode.config.messages.splice(idx, 1)" />
              </div>
              <el-button size="small" :icon="Plus" @click="selectedNode.config.messages.push({ type: 'text', value: '' })">
                添加消息
              </el-button>
            </el-form>
          </template>

          <!-- 会话 -->
          <template v-else-if="selectedNode.type === 'conversation_entry'">
            <el-form label-position="top" size="small">
              <el-form-item label="会话名称（可选）">
                <el-input v-model="selectedNode.config.session" placeholder="例如：问卷" />
              </el-form-item>
            </el-form>
            <el-alert type="info" :closable="false">
              在会话内收集的数据会被存储（不同群聊、不同用户独立存储），下次进入同一会话时可获取上次会话的数据，若不需要存储数据，可不添加「会话入口」，直接使用「信息收集」即可。
            </el-alert>
          </template>
          <template v-else-if="selectedNode.type === 'collect'">
            <el-form label-position="top" size="small">
              <el-form-item label="变量名（用户回复存入）">
                <el-input v-model="selectedNode.config.key" placeholder="reply" />
              </el-form-item>
              <el-form-item label="提示语">
                <el-input v-model="selectedNode.config.prompt" v-var-drop placeholder="例如：请输入你的名字" />
              </el-form-item>
            </el-form>
          </template>
          <template v-else-if="selectedNode.type === 'choice'">
            <el-form label-position="top" size="small">
              <el-form-item label="提示文本">
                <el-input v-model="selectedNode.config.prompt" v-var-drop type="textarea" :rows="2" placeholder="例如：请选择你要的服务" />
              </el-form-item>
              <el-form-item label="选项列表（按 1、2、3… 排序发送，末尾自动带 [0] 退出）">
                <div v-for="(opt, idx) in selectedNode.config.options" :key="idx" class="msg-row">
                  <span class="opt-index">{{ idx + 1 }}</span>
                  <el-input v-model="selectedNode.config.options[idx]" v-var-drop placeholder="选项内容" />
                  <el-button text type="danger" :icon="Delete" @click="selectedNode.config.options.splice(idx, 1)" />
                </div>
                <el-button size="small" :icon="Plus" @click="selectedNode.config.options.push('')">
                  添加选项
                </el-button>
              </el-form-item>
              <el-form-item label="保存到变量（选择结果）">
                <el-input v-model="selectedNode.config.var" placeholder="choice" />
              </el-form-item>
              <el-alert type="info" :closable="false" title="用户输入不在选项内会要求重新输入；选择 0 退出并清除会话。">
              </el-alert>
            </el-form>
          </template>
          <template v-else-if="selectedNode.type === 'loop_end'">
            <el-alert type="info" :closable="false">
              与循环「{{ loopEndSource(selectedNode) }}」配对。流程到达此处时回到循环取下一个元素，循环结束后从下方出口继续。
            </el-alert>
          </template>
          <template v-else-if="selectedNode.type === 'session_end'">
            <el-alert type="info" :closable="false">
              与会话入口「{{ sessionEndSource(selectedNode) }}」配对。执行到此节点时结束并清除该会话存储。
            </el-alert>
          </template>

          <div class="connector">
            <div class="sub-label">流程连接（也可拖拽节点上的端口连线）</div>
            <div v-for="port in connectPorts(selectedNode)" :key="port.port" class="conn-row">
              <span class="conn-label">{{ port.label }}</span>
              <el-select
                :model-value="edgeTarget(selectedNode.id, port.port)"
                style="flex: 1"
                placeholder="选择下一节点"
                clearable
                @change="(val) => setEdgeTarget(selectedNode.id, port.port, val)"
              >
                <el-option
                  v-for="n in otherNodes(selectedNode.id)"
                  :key="n.id"
                  :label="`${nodeLabel(n.type)} · ${nodeSummary(n)}`"
                  :value="n.id"
                />
              </el-select>
            </div>
            <div v-if="selectedEdge" class="edge-tools">
              <el-button size="small" type="danger" plain @click="deleteEdge(selectedEdge)">删除选中连线</el-button>
            </div>
          </div>
        </template>
        <div v-else class="config-empty">
          点击画布中的节点进行配置
          <template v-if="edgeSelectedKey">（已选中连线，可在上方删除）</template>
        </div>
      </aside>
    </div>

  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import {
  ArrowLeft,
  Back,
  ChatDotRound,
  ChatLineRound,
  CircleClose,
  Connection,
  Delete,
  Document,
  Key,
  List,
  Link as LinkIcon,
  MessageBox,
  Operation,
  Plus,
  Promotion,
  RefreshRight,
  Share,
  Switch,
  Timer,
} from "@element-plus/icons-vue";
import api from "../api";

const props = defineProps({ pluginId: { type: String, required: true } });

const NODE_W = 240;
const NODE_H = 72;
const varHint = "{{变量名}}";
const weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"];

// 任何触发方式都可用
const ALWAYS_VARS = [
  { name: "bot_id", desc: "机器人 QQ 号" },
  { name: "bot_name", desc: "机器人名称" },
  { name: "system.cpu", desc: "CPU 占用百分比" },
  { name: "system.memory", desc: "内存占用百分比" },
  { name: "system.disk", desc: "磁盘占用百分比" },
  { name: "system.gpu", desc: "GPU 占用信息（utilization/memory_used/memory_total）" },
];

// 仅消息监听（群聊/私信）触发分支可用
const MSG_VARS = [
  { name: "msg", desc: "消息文本内容" },
  { name: "raw_msg", desc: "原始消息文本" },
  { name: "segments", desc: "消息段列表，如 {{segments.0.type}}" },
  { name: "user_id", desc: "发送人 QQ 号" },
  { name: "group_id", desc: "群号（私信为空）" },
  { name: "sender.nickname", desc: "发送人昵称" },
  { name: "sender.user_id", desc: "发送人 QQ 号" },
  { name: "sender.card", desc: "发送人群名片" },
  { name: "event", desc: "NoneBot 原生事件对象" },
  { name: "bot", desc: "NoneBot 机器人对象" },
];

// 仅 WebHook 触发分支可用
const WEBHOOK_VARS = [
  { name: "webhook", desc: "WebHook 请求负载" },
];

const catalog = ref({ nodes: {}, condition_ops: {}, message_types: {} });
const plugin = reactive({ name: "", description: "" });
const flow = reactive({ nodes: [], edges: [] });
const selectedId = ref(null);
const edgeSelectedKey = ref(null);
const loading = ref(true);
const saving = ref(false);
const dirty = ref(false);
const canvasRef = ref(null);

const pan = reactive({ x: 0, y: 0 });
const zoom = ref(1);
const panning = ref(false);
const tempConn = ref(null);
let connState = null;

const installed = ref([]);
const updating = ref(false);
const bots = ref([]);

const iconMap = {
  listener_group: ChatDotRound,
  listener_private: ChatLineRound,
  listener_webhook: LinkIcon,
  logic: Switch,
  loop: RefreshRight,
  schedule: Timer,
  api: Connection,
  code: Document,
  send: Promotion,
  conversation_entry: MessageBox,
  collect: Key,
  choice: List,
  loop_end: Back,
  session_end: CircleClose,
};

const paletteGroups = computed(() => {
  const order = ["listener", "basic", "feature", "action", "session"];
  const labels = {
    listener: "触发方式",
    basic: "基本组件",
    feature: "功能",
    action: "机器人",
    session: "会话控制",
  };
  const groups = [];
  for (const cat of order) {
    const items = Object.entries(catalog.value.nodes || {})
      .filter(([, v]) => v.category === cat && !v.hidden)
      .map(([type, v]) => ({ type, label: v.label }));
    if (items.length) groups.push({ cat, label: labels[cat], items });
  }
  return groups;
});

const selectedNode = computed(() => flow.nodes.find((n) => n.id === selectedId.value) || null);

const selectedEdge = computed(
  () => flow.edges.find((e) => `${e.from}-${e.port}-${e.to}` === edgeSelectedKey.value) || null
);

// ---------- 画布变换 ----------
// 世界画布随节点位置向四周扩展（允许负坐标），实现四向无限画布
const worldBounds = computed(() => {
  let minX = 0;
  let minY = 0;
  let maxX = 0;
  let maxY = 0;
  for (const n of flow.nodes) {
    minX = Math.min(minX, n.x);
    minY = Math.min(minY, n.y);
    maxX = Math.max(maxX, n.x + NODE_W);
    maxY = Math.max(maxY, n.y + NODE_H);
  }
  const margin = 400;
  return {
    x: minX - margin,
    y: minY - margin,
    w: maxX - minX + margin * 2,
    h: maxY - minY + margin * 2,
  };
});

const worldStyle = computed(() => ({
  width: worldBounds.value.w + "px",
  height: worldBounds.value.h + "px",
  transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom.value})`,
}));

const edgeStyle = computed(() => ({
  left: worldBounds.value.x + "px",
  top: worldBounds.value.y + "px",
  width: worldBounds.value.w + "px",
  height: worldBounds.value.h + "px",
}));

const edgeViewBox = computed(
  () =>
    `${worldBounds.value.x} ${worldBounds.value.y} ${worldBounds.value.w} ${worldBounds.value.h}`
);

function clientToWorld(cx, cy) {
  const rect = canvasRef.value.getBoundingClientRect();
  return {
    x: (cx - rect.left - pan.x) / zoom.value,
    y: (cy - rect.top - pan.y) / zoom.value,
  };
}

function onCanvasWheel(ev) {
  const rect = canvasRef.value.getBoundingClientRect();
  const mx = ev.clientX - rect.left;
  const my = ev.clientY - rect.top;
  // 锚点：缩放前后，鼠标下的世界坐标保持不动
  const wx = (mx - pan.x) / zoom.value;
  const wy = (my - pan.y) / zoom.value;
  const factor = ev.deltaY < 0 ? 1.1 : 1 / 1.1;
  const next = Math.min(1.5, Math.max(0.5, zoom.value * factor));
  if (next === zoom.value) return;
  pan.x = mx - wx * next;
  pan.y = my - wy * next;
  zoom.value = next;
}

function outPortPos(node, port) {
  let frac = 0.5;
  if (port === "true") frac = 0.25;
  else if (port === "false") frac = 0.75;
  else if (port.startsWith("opt_")) {
    const idx = parseInt(port.slice(4), 10);
    const count = (node.config.options || []).length + 1; // +1 为退出
    frac = (idx + 1) / (count + 1);
  }
  const x = node.x + NODE_W * frac;
  return { x, y: node.y + NODE_H };
}

function inPortPos(node) {
  return { x: node.x + NODE_W / 2, y: node.y };
}

const edgePaths = computed(() => {
  const byId = {};
  flow.nodes.forEach((n) => (byId[n.id] = n));
  const portLabels = { next: "", true: "是", false: "否" };
  return flow.edges
    .map((e) => {
      const src = byId[e.from];
      const dst = byId[e.to];
      if (!src || !dst) return null;
      const p1 = outPortPos(src, e.port);
      const p2 = inPortPos(dst);
      const dy = Math.max(24, Math.abs(p2.y - p1.y) / 2);
      const d = `M ${p1.x} ${p1.y} C ${p1.x} ${p1.y + dy}, ${p2.x} ${p2.y - dy}, ${p2.x} ${p2.y}`;
      return {
        key: `${e.from}-${e.port}-${e.to}`,
        d,
        mx: (p1.x + p2.x) / 2,
        my: (p1.y + p2.y) / 2,
        port: e.port,
        portLabel: portLabels[e.port] || "",
      };
    })
    .filter(Boolean);
});

// 配对连线（循环遍历-循环结束 / 会话入口-会话结束），左侧连接，不可删除
const pairLines = computed(() => {
  const byId = {};
  flow.nodes.forEach((n) => (byId[n.id] = n));
  const lines = [];
  for (const n of flow.nodes) {
    if (
      (n.type === "loop" || n.type === "conversation_entry") &&
      n.config.end
    ) {
      const end = byId[n.config.end];
      if (end) {
        const x1 = n.x;
        const y1 = n.y + NODE_H / 2;
        const x2 = end.x;
        const y2 = end.y + NODE_H / 2;
        lines.push({ key: `pair-${n.id}`, d: `M ${x1} ${y1} L ${x2} ${y2}` });
      }
    }
  }
  return lines;
});

const tempPath = computed(() => {
  const t = tempConn.value;
  if (!t) return "";
  const dy = Math.max(24, Math.abs(t.y2 - t.y) / 2);
  return `M ${t.x} ${t.y} C ${t.x} ${t.y + dy}, ${t.x2} ${t.y2 - dy}, ${t.x2} ${t.y2}`;
});

// ---------- 组件目录 ----------
let seq = 0;
function newId() {
  return `n${Date.now().toString(36)}${(seq++).toString(36)}`;
}

function nodeLabel(type) {
  return catalog.value.nodes[type]?.label || type;
}

function defaultConfig(type) {
  return JSON.parse(JSON.stringify(catalog.value.nodes[type]?.default || {}));
}

function opLabel(op) {
  return catalog.value.condition_ops?.[op] || op;
}

function isEmptyOp(op) {
  return op === "is_empty" || op === "not_empty";
}

function nodeSummary(node) {
  const cfg = node.config || {};
  switch (node.type) {
    case "listener_group":
      return `群聊 · ${cfg.keywords || "任意消息"}${cfg.at_me ? " · 仅@我" : ""}`;
    case "listener_private":
      return `私信 · ${cfg.keywords || "任意消息"}`;
    case "listener_webhook":
      return `${cfg.path || "/webhook/…"} → ${cfg.var || "webhook"}`;
    case "logic":
      return `${cfg.combine === "and" ? "且" : "或"}${cfg.negate ? " · 取反" : ""}（${(cfg.conditions || []).length} 条条件）`;
    case "loop":
      return `遍历 ${cfg.items || "…"} → ${cfg.var || "item"}`;
    case "schedule": {
      const mode = cfg.mode || "interval";
      if (mode === "interval") return `每 ${cfg.interval || 60} 秒`;
      if (mode === "daily") return `每天 ${cfg.time || "09:00"}`;
      if (mode === "weekly") return `每周${weekdays[cfg.weekday ?? 1]} ${cfg.time || "09:00"}`;
      return `每月${cfg.day || 1}号 ${cfg.time || "09:00"}`;
    }
    case "api":
      return `${cfg.method || "GET"} ${cfg.url || "…"} → ${cfg.var || "api_resp"}`;
    case "code":
      return (cfg.code || "").split("\n")[0] || "输入 Python 代码";
    case "send":
      return `${cfg.mode === "finish" ? "发送并结束" : "发送但继续"} · ${(cfg.messages || []).length} 条消息`;
    case "conversation_entry":
      return cfg.session || "新会话";
    case "collect":
      return `收集 → ${cfg.key || "reply"}`;
    case "choice":
      return `${cfg.prompt || "选择"} · ${(cfg.options || []).length} 个选项`;
    case "loop_end":
      return cfg.loop ? "回到循环" : "未配对";
    case "session_end":
      return cfg.entry ? "结束会话" : "未配对";
    default:
      return "";
  }
}

function loopEndName(node) {
  const end = flow.nodes.find((n) => n.id === node.config.end);
  return end ? `已自动配对（${nodeLabel(end.type)}）` : "未配对";
}

function loopEndSource(node) {
  const loop = flow.nodes.find((n) => n.id === node.config.loop);
  return loop ? `「${nodeSummary(loop)}」` : "未配对";
}

function sessionEndSource(node) {
  const entry = flow.nodes.find((n) => n.id === node.config.entry);
  return entry ? `「${nodeSummary(entry)}」` : "未配对";
}

function segPlaceholder(type) {
  return (
    {
      text: "文本内容，可用 {{变量}}",
      image: "图片 URL 或本地路径",
      face: "QQ 表情 id，例如 171",
      meme: "表情包图片 URL 或路径",
      at: "QQ 号，留空=艾特发送者",
      record: "语音 URL 或路径",
      video: "视频 URL 或路径",
    }[type] || "内容"
  );
}

// ---------- 组件拖入 ----------
function onPaletteDragStart(type, ev) {
  ev.dataTransfer.setData("text/visual-type", type);
  ev.dataTransfer.effectAllowed = "copy";
}

function addNode(type, x, y) {
  const node = { id: newId(), type, config: defaultConfig(type), x, y };
  flow.nodes.push(node);
  if (selectedNode.value) {
    const port = availablePort(selectedNode.value);
    if (port) {
      flow.edges.push({ from: selectedNode.value.id, to: node.id, port });
    }
  }
  if (type === "loop" || type === "conversation_entry") {
    // 自动创建配对节点（循环结束 / 会话结束），同生共死
    const endType = type === "loop" ? "loop_end" : "session_end";
    const end = {
      id: newId(),
      type: endType,
      config: defaultConfig(endType),
      x,
      y: y + NODE_H + 90,
    };
    end.config[type === "loop" ? "loop" : "entry"] = node.id;
    node.config.end = end.id;
    flow.nodes.push(end);
  }
  selectedId.value = node.id;
  edgeSelectedKey.value = null;
  dirty.value = true;
  return node;
}

function addNodeAtCenter(type) {
  const w = clientToWorld(canvasRef.value.clientWidth / 2, canvasRef.value.clientHeight / 2);
  addNode(type, w.x - NODE_W / 2, w.y - NODE_H / 2);
}

function onCanvasDrop(ev) {
  ev.preventDefault();
  const type = ev.dataTransfer.getData("text/visual-type");
  if (!type || !catalog.value.nodes[type]) return;
  const w = clientToWorld(ev.clientX, ev.clientY);
  addNode(type, w.x - NODE_W / 2, w.y - 20);
}

function hasEdge(from, port) {
  return flow.edges.some((e) => e.from === from && e.port === port);
}

function availablePort(node) {
  if (node.type === "logic") {
    if (!hasEdge(node.id, "true")) return "true";
    if (!hasEdge(node.id, "false")) return "false";
    return null;
  }
  if (node.type === "choice") {
    const count = (node.config.options || []).length;
    for (let i = 1; i <= count; i++) {
      if (!hasEdge(node.id, `opt_${i}`)) return `opt_${i}`;
    }
    if (!hasEdge(node.id, "opt_0")) return "opt_0";
    return null;
  }
  return hasEdge(node.id, "next") ? null : "next";
}

// ---------- 节点移动 ----------
let dragState = null;
function onNodePointerDown(node, ev) {
  if (ev.button !== 0) return;
  ev.stopPropagation();
  if (ev.target.closest(".port-in, .port-out, .el-button, .el-select, .el-input")) return;
  dragState = {
    id: node.id,
    startX: ev.clientX,
    startY: ev.clientY,
    origX: node.x,
    origY: node.y,
  };
  document.body.classList.add("no-select");
  window.addEventListener("pointermove", onNodePointerMove);
  window.addEventListener("pointerup", onNodePointerUp);
}

function onNodePointerMove(ev) {
  if (!dragState) return;
  const node = flow.nodes.find((n) => n.id === dragState.id);
  if (node) {
    node.x = dragState.origX + (ev.clientX - dragState.startX) / zoom.value;
    node.y = dragState.origY + (ev.clientY - dragState.startY) / zoom.value;
  }
}

function onNodePointerUp() {
  dragState = null;
  document.body.classList.remove("no-select");
  window.removeEventListener("pointermove", onNodePointerMove);
  window.removeEventListener("pointerup", onNodePointerUp);
}

// ---------- 画布平移 ----------
let panState = null;
function onCanvasPointerDown(ev) {
  if (ev.button !== 0) return;
  if (
    ev.target.closest(
      ".node-card, .edge-dot, .edge-hit, .port-in, .port-out, .el-button, .el-select, .el-input"
    )
  ) {
    return;
  }
  panState = { startX: ev.clientX, startY: ev.clientY, origX: pan.x, origY: pan.y };
  panning.value = true;
  window.addEventListener("pointermove", onCanvasPointerMove);
  window.addEventListener("pointerup", onCanvasPointerUp);
}

function onCanvasClick(ev) {
  if (
    ev.target.closest(
      ".node-card, .edge-dot, .edge-hit, .port-in, .port-out"
    )
  ) {
    return;
  }
  selectedId.value = null;
  edgeSelectedKey.value = null;
}

function onCanvasPointerMove(ev) {
  if (!panState) return;
  pan.x = panState.origX + (ev.clientX - panState.startX);
  pan.y = panState.origY + (ev.clientY - panState.startY);
}

function onCanvasPointerUp() {
  panState = null;
  panning.value = false;
  window.removeEventListener("pointermove", onCanvasPointerMove);
  window.removeEventListener("pointerup", onCanvasPointerUp);
}

// ---------- 端口连线 ----------
function outPorts(node) {
  if (node.type === "logic") {
    return [
      { port: "true", label: "是", title: "条件成立时连接到此出口" },
      { port: "false", label: "否", title: "条件不成立时连接到此出口" },
    ];
  }
  if (node.type === "choice") {
    const options = node.config.options || [];
    const count = options.length + 1;
    const ports = [];
    for (let i = 0; i < options.length; i++) {
      const frac = (i + 2) / (count + 1);
      ports.push({
        port: `opt_${i + 1}`,
        label: `${i + 1}`,
        title: `选择 ${i + 1} 时走此出口`,
        style: { left: `${(frac * 100).toFixed(1)}%` },
      });
    }
    ports.push({
      port: "opt_0",
      label: "0",
      title: "选择退出时走此出口",
      style: { left: `${(100 / (count + 1)).toFixed(1)}%` },
    });
    return ports;
  }
  return [{ port: "next", label: "", title: "拖到其它节点输入端口完成连线" }];
}

function onPortOutPointerDown(node, port, ev) {
  ev.stopPropagation();
  ev.preventDefault();
  const pos = outPortPos(node, port);
  connState = { from: node.id, port };
  tempConn.value = { x: pos.x, y: pos.y, x2: pos.x, y2: pos.y, port };
  window.addEventListener("pointermove", onConnMove);
  window.addEventListener("pointerup", onConnUp);
}

function onConnMove(ev) {
  if (!connState) return;
  const w = clientToWorld(ev.clientX, ev.clientY);
  tempConn.value = { ...tempConn.value, x2: w.x, y2: w.y };
}

function onConnUp(ev) {
  window.removeEventListener("pointermove", onConnMove);
  window.removeEventListener("pointerup", onConnUp);
  if (!connState) return;
  const el = document.elementFromPoint(ev.clientX, ev.clientY);
  const portIn = el?.closest?.(".port-in");
  const nodeEl = portIn?.closest?.(".node-card");
  const toId = nodeEl?.dataset?.id || null;
  if (toId && toId !== connState.from) {
    flow.edges = flow.edges.filter(
      (e) => !(e.from === connState.from && e.port === connState.port)
    );
    flow.edges = flow.edges.filter((e) => !(e.from === connState.from && e.to === toId));
    flow.edges.push({ from: connState.from, to: toId, port: connState.port });
    dirty.value = true;
  }
  connState = null;
  tempConn.value = null;
}

function removeNode(id) {
  const node = flow.nodes.find((n) => n.id === id);
  if (!node) return;
  // 同生共死：循环遍历↔循环结束、会话入口↔会话结束
  let pairId = null;
  if (node.type === "loop" || node.type === "conversation_entry") {
    pairId = node.config.end;
  } else if (node.type === "loop_end") {
    pairId = node.config.loop;
  } else if (node.type === "session_end") {
    pairId = node.config.entry;
  }
  const ids = new Set([id]);
  if (pairId && flow.nodes.some((n) => n.id === pairId)) ids.add(pairId);
  flow.nodes = flow.nodes.filter((n) => !ids.has(n.id));
  flow.edges = flow.edges.filter((e) => !ids.has(e.from) && !ids.has(e.to));
  if (selectedId.value && ids.has(selectedId.value)) selectedId.value = null;
  dirty.value = true;
}

// ---------- 连线管理 ----------
function otherNodes(id) {
  return flow.nodes.filter((n) => n.id !== id);
}

function connectPorts(node) {
  if (node.type === "logic") {
    return [
      { port: "true", label: "条件成立→" },
      { port: "false", label: "条件不成立→" },
    ];
  }
  if (node.type === "choice") {
    const options = node.config.options || [];
    const ports = [];
    for (let i = 0; i < options.length; i++) {
      ports.push({ port: `opt_${i + 1}`, label: `选择 ${i + 1}→` });
    }
    ports.push({ port: "opt_0", label: "退出(0)→" });
    return ports;
  }
  return [{ port: "next", label: "下一步→" }];
}

function edgeTarget(from, port) {
  const e = flow.edges.find((x) => x.from === from && x.port === port);
  return e ? e.to : "";
}

function setEdgeTarget(from, port, to) {
  flow.edges = flow.edges.filter((e) => !(e.from === from && e.port === port));
  if (to) {
    flow.edges = flow.edges.filter((e) => !(e.from === from && e.to === to));
    flow.edges.push({ from, to, port });
  }
  dirty.value = true;
}

function selectEdge(edge) {
  edgeSelectedKey.value = edge.key;
  selectedId.value = null;
}

function deleteEdge(edge) {
  flow.edges = flow.edges.filter((e) => `${e.from}-${e.port}-${e.to}` !== edge.key);
  edgeSelectedKey.value = null;
  dirty.value = true;
}

// ---------- 可用变量 ----------
// 节点是否处于某类触发分支（消息/WebHook/会话入口）的下游
const reachMap = computed(() => {
  const res = {};
  flow.nodes.forEach((n) => (res[n.id] = { msg: false, webhook: false, entry: false }));
  const entryKinds = {
    listener_group: "msg",
    listener_private: "msg",
    listener_webhook: "webhook",
    conversation_entry: "entry",
  };
  for (const n of flow.nodes) {
    const kind = entryKinds[n.type];
    if (!kind) continue;
    const stack = [];
    flow.edges.forEach((e) => {
      if (e.from === n.id) stack.push(e.to);
    });
    while (stack.length) {
      const id = stack.pop();
      if (!id || !res[id]) continue;
      if (!res[id][kind]) {
        res[id][kind] = true;
        flow.edges.forEach((e) => {
          if (e.from === id) stack.push(e.to);
        });
      }
    }
  }
  return res;
});

const flowVars = computed(() => {
  const map = {};
  const byId = {};
  flow.nodes.forEach((n) => (byId[n.id] = n));
  const defs = {};
  flow.nodes.forEach((n) => {
    const set = new Set();
    if (n.type === "collect") {
      set.add(n.config.key || "reply");
      set.add("reply");
    }
    if (n.type === "listener_webhook") {
      set.add(n.config.var || "webhook");
    }
    if (n.type === "api") {
      set.add(n.config.var || "api_resp");
    }
    if (n.type === "conversation_entry") {
      set.add("session");
    }
    if (n.type === "choice") {
      set.add(n.config.var || "choice");
    }
    defs[n.id] = set;
  });
  const bodies = {};
  flow.nodes.forEach((n) => {
    if (n.type !== "loop") return;
    const body = new Set();
    const stack = [edgeTarget(n.id, "next")];
    while (stack.length) {
      const id = stack.pop();
      if (!id || body.has(id)) continue;
      const nd = byId[id];
      if (!nd || nd.type === "loop_end") continue;
      body.add(id);
      flow.edges.forEach((e) => {
        if (e.from === id) stack.push(e.to);
      });
    }
    bodies[n.id] = body;
  });
  const defined = {};
  flow.nodes.forEach((n) => (defined[n.id] = new Set()));
  let changed = true;
  while (changed) {
    changed = false;
    flow.nodes.forEach((n) => {
      const out = new Set(defined[n.id]);
      defs[n.id].forEach((x) => out.add(x));
      Object.entries(bodies).forEach(([lid, bodySet]) => {
        if (bodySet.has(n.id)) out.add(byId[lid].config.var || "item");
      });
      flow.edges.forEach((e) => {
        if (e.from !== n.id) return;
        out.forEach((x) => {
          if (!defined[e.to].has(x)) {
            defined[e.to].add(x);
            changed = true;
          }
        });
      });
    });
  }
  flow.nodes.forEach((n) => {
    map[n.id] = [...defined[n.id]].map((name) => ({
      name,
      desc: "由前置节点产生的变量",
    }));
  });
  return map;
});

const availableVars = computed(() => {
  if (!selectedNode.value) return ALWAYS_VARS;
  const reach = reachMap.value[selectedNode.value.id] || {};
  const list = [...ALWAYS_VARS];
  if (reach.msg) list.push(...MSG_VARS);
  if (reach.webhook) list.push(...WEBHOOK_VARS);
  list.push(...(flowVars.value[selectedNode.value.id] || []));
  return list;
});

function onVarDragStart(name, ev) {
  ev.dataTransfer.setData("text/visual-var", name);
  ev.dataTransfer.effectAllowed = "copy";
}

let lastFocused = null;
function insertVar(name) {
  const target = lastFocused;
  if (!target) {
    ElMessage.info("请先点击要插入变量的输入框");
    return;
  }
  const tpl = "{{" + name + "}}";
  const start = target.selectionStart ?? target.value.length;
  const end = target.selectionEnd ?? target.value.length;
  target.value = target.value.slice(0, start) + tpl + target.value.slice(end);
  target.dispatchEvent(new Event("input", { bubbles: true }));
}

const vVarDrop = {
  mounted(el) {
    el.addEventListener("pointerdown", () => {
      const inner = el.tagName === "INPUT" || el.tagName === "TEXTAREA" ? el : el.querySelector("input, textarea");
      if (inner) lastFocused = inner;
    });
    el.addEventListener("dragover", (e) => e.preventDefault());
    el.addEventListener("drop", (e) => {
      e.preventDefault();
      const name = e.dataTransfer.getData("text/visual-var");
      if (!name) return;
      const target = el.tagName === "INPUT" || el.tagName === "TEXTAREA" ? el : el.querySelector("input, textarea");
      if (!target) return;
      const tpl = "{{" + name + "}}";
      const start = target.selectionStart ?? target.value.length;
      const end = target.selectionEnd ?? target.value.length;
      target.value = target.value.slice(0, start) + tpl + target.value.slice(end);
      target.dispatchEvent(new Event("input", { bubbles: true }));
    });
  },
};

// ---------- 保存 / 生成 / 装配 ----------
async function save() {
  if (!plugin.name.trim()) {
    ElMessage.warning("请填写插件名称");
    return;
  }
  saving.value = true;
  try {
    await api.put(`/visual-plugins/${props.pluginId}`, {
      name: plugin.name,
      description: plugin.description,
      flow: { nodes: flow.nodes, edges: flow.edges },
    });
    dirty.value = false;
    ElMessage.success("已保存");
  } finally {
    saving.value = false;
  }
}

async function updatePlugins() {
  try {
    await save();
  } catch {
    return;
  }
  if (!installed.value.length) {
    ElMessage.warning("该插件尚未装配到任何机器人，请先到插件列表页点击「装配到机器人」");
    return;
  }
  updating.value = true;
  try {
    const names = [];
    for (const entry of installed.value) {
      await api.post(`/visual-plugins/${props.pluginId}/install`, {
        bot_id: entry.bot_id,
      });
      const bot = bots.value.find((b) => b.id === entry.bot_id);
      names.push(bot ? bot.name : entry.bot_id);
    }
    ElMessage.success(`已更新并重新装配到：${names.join("、")}`);
  } catch {
    /* 拦截器已提示错误 */
  } finally {
    updating.value = false;
  }
}

onMounted(async () => {
  try {
    const [cat, pluginData] = await Promise.all([
      api.get("/visual-plugins/catalog"),
      api.get(`/visual-plugins/${props.pluginId}`),
    ]);
    catalog.value = cat;
    plugin.name = pluginData.name;
    plugin.description = pluginData.description || "";
    installed.value = pluginData.installed || [];
    flow.nodes = pluginData.flow.nodes || [];
    flow.edges = pluginData.flow.edges || [];
    for (const node of flow.nodes) {
      node.config = { ...defaultConfig(node.type), ...(node.config || {}) };
      if (node.type === "logic" && !(node.config.conditions || []).length) {
        node.config.conditions = [{ left: "", op: "contains", right: "" }];
      }
      if (node.x === undefined) node.x = 40;
      if (node.y === undefined) node.y = 40;
    }
    bots.value = await api.get("/bots");
  } catch {
    /* ignore */
  } finally {
    loading.value = false;
  }
});

onBeforeUnmount(() => {
  onNodePointerUp();
  onCanvasPointerUp();
  window.removeEventListener("pointermove", onConnMove);
  window.removeEventListener("pointerup", onConnUp);
});
</script>

<style scoped>
.editor-page {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 60px);
}

.editor-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 16px;
  background: #fff;
  border-bottom: 1px solid var(--nb-border);
}

.editor-title {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1;
  min-width: 0;
}

.name-input {
  width: 220px;
}

.desc-input {
  flex: 1;
  max-width: 420px;
}

.editor-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.editor-body {
  flex: 1;
  display: flex;
  min-height: 0;
}

.palette {
  width: 190px;
  flex-shrink: 0;
  background: #fff;
  border-right: 1px solid var(--nb-border);
  padding: 12px;
  overflow: auto;
}

.palette-title,
.config-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--nb-text-secondary);
  margin-bottom: 10px;
}

.palette-group {
  margin-bottom: 14px;
}

.palette-group-label {
  font-size: 12px;
  color: var(--nb-text-secondary);
  margin-bottom: 6px;
}

.palette-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  margin-bottom: 6px;
  border: 1px solid var(--nb-border);
  border-radius: 8px;
  font-size: 13px;
  cursor: grab;
  background: #fff;
  transition: all 0.15s;
}

.palette-item:hover {
  border-color: var(--nb-orange);
  color: var(--nb-orange);
  box-shadow: 0 2px 8px rgba(234, 82, 82, 0.12);
}

.palette-item.listener .el-icon {
  color: var(--nb-orange);
}

.palette-item.basic .el-icon {
  color: #409eff;
}

.palette-item.action .el-icon {
  color: #67c23a;
}

.palette-item.session .el-icon {
  color: #e6a23c;
}

.palette-tip {
  font-size: 12px;
  color: var(--nb-text-secondary);
  margin-top: 8px;
}

.canvas-wrap {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
}

.canvas-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 14px;
  background: #fff;
  border-bottom: 1px solid var(--nb-border);
  font-size: 13px;
}

.canvas-hint {
  color: #c0c4cc;
  font-size: 12px;
}

.canvas {
  flex: 1;
  position: relative;
  background: #fafafa;
  overflow: hidden;
  min-height: 0;
  touch-action: none;
  cursor: grab;
}

.canvas.panning {
  cursor: grabbing;
}

.world {
  position: absolute;
  top: 0;
  left: 0;
  transform-origin: 0 0;
}

.edges {
  position: absolute;
  pointer-events: none;
  overflow: visible;
}

.edge-line {
  fill: none;
  stroke-width: 2;
}

.edge-line.next {
  stroke: #909399;
}

.edge-line.true {
  stroke: #67c23a;
}

.edge-line.false {
  stroke: #f56c6c;
}

.edge-line.selected {
  stroke-width: 3;
  stroke: var(--nb-orange);
}

.edge-line.temp {
  stroke-dasharray: 6 4;
}

.edge-hit {
  fill: none;
  stroke: transparent;
  stroke-width: 14;
  pointer-events: stroke;
  cursor: pointer;
}

.edge-dot {
  stroke-width: 1;
  fill: #fff;
  pointer-events: auto;
  cursor: pointer;
}

.edge-dot.next {
  stroke: #909399;
}

.edge-dot.true {
  stroke: #67c23a;
}

.edge-dot.false {
  stroke: #f56c6c;
}

.edge-dot.selected {
  stroke: var(--nb-orange);
}

.edge-label {
  font-size: 10px;
  text-anchor: middle;
  fill: #606266;
  pointer-events: none;
}

.edge-del-bg {
  fill: var(--nb-orange);
  pointer-events: auto;
  cursor: pointer;
}

.edge-del-x {
  font-size: 13px;
  text-anchor: middle;
  fill: #fff;
  pointer-events: none;
}

.node-card {
  position: absolute;
  width: 240px;
  min-height: 72px;
  background: #fff;
  border: 1px solid var(--nb-border);
  border-left: 4px solid #909399;
  border-radius: 10px;
  padding: 10px 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  cursor: pointer;
  user-select: none;
}

.node-card:hover {
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.1);
}

.node-card.selected {
  border-color: var(--nb-orange);
  border-left-width: 4px;
  box-shadow: 0 0 0 2px rgba(234, 82, 82, 0.25);
}

.node-card.listener_group,
.node-card.listener_private,
.node-card.listener_webhook {
  border-left-color: var(--nb-orange);
}

.node-card.logic,
.node-card.loop,
.node-card.schedule,
.node-card.code {
  border-left-color: #409eff;
}

.node-card.send {
  border-left-color: #67c23a;
}

.node-card.conversation_entry,
.node-card.collect,
.node-card.loop_end,
.node-card.session_end {
  border-left-color: #e6a23c;
}

.pair-line {
  fill: none;
  stroke: #b37feb;
  stroke-width: 2;
  stroke-dasharray: 6 4;
  pointer-events: none;
}

.node-head {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
  font-size: 13px;
}

.node-icon {
  color: #606266;
}

.node-summary {
  margin-top: 6px;
  font-size: 12px;
  color: var(--nb-text-secondary);
  line-height: 1.4;
  word-break: break-all;
}

.port-in {
  position: absolute;
  top: -8px;
  left: 50%;
  transform: translateX(-50%);
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #fff;
  border: 2px solid #909399;
  cursor: crosshair;
  z-index: 5;
}

.port-in:hover {
  border-color: var(--nb-orange);
  background: var(--nb-orange-light);
}

.port-out {
  position: absolute;
  bottom: -14px;
  width: 26px;
  height: 26px;
  border-radius: 50%;
  background: #fff;
  border: 2px solid #909399;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  color: #606266;
  cursor: crosshair;
  z-index: 5;
  transform: translateX(-50%);
}

.port-out.next {
  left: 50%;
}

.port-out.true {
  left: 25%;
  border-color: #67c23a;
  color: #67c23a;
}

.port-out.false {
  left: 75%;
  border-color: #f56c6c;
  color: #f56c6c;
}

.port-out:hover {
  border-color: var(--nb-orange);
  background: var(--nb-orange-light);
}

.canvas-empty {
  position: absolute;
  top: 40%;
  left: 50%;
  transform: translate(-50%, -50%);
  color: var(--nb-text-secondary);
  font-size: 14px;
  pointer-events: none;
}

.var-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  padding: 8px 14px;
  background: #fff;
  border-top: 1px solid var(--nb-border);
  max-height: 92px;
  overflow: auto;
}

.var-bar-label {
  font-size: 12px;
  color: var(--nb-text-secondary);
  white-space: nowrap;
}

.var-pill {
  display: inline-flex;
  align-items: center;
  padding: 2px 10px;
  border-radius: 999px;
  background: var(--nb-orange-light);
  color: var(--nb-orange);
  font-size: 12px;
  cursor: grab;
  border: 1px solid transparent;
  user-select: none;
}

.var-pill:hover {
  border-color: var(--nb-orange);
}

.var-tip {
  font-size: 12px;
  color: #c0c4cc;
  margin-left: 6px;
}

.config-panel {
  width: 320px;
  flex-shrink: 0;
  background: #fff;
  border-left: 1px solid var(--nb-border);
  padding: 12px 14px;
  overflow: auto;
}

.config-node-name {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.config-empty {
  color: var(--nb-text-secondary);
  font-size: 13px;
  padding: 20px 0;
  text-align: center;
}

.sub-label {
  font-size: 12px;
  color: var(--nb-text-secondary);
  margin: 8px 0 6px;
}

.cond-row,
.msg-row {
  display: flex;
  gap: 6px;
  margin-bottom: 6px;
  align-items: center;
}

.opt-index {
  width: 20px;
  text-align: center;
  color: var(--nb-text-secondary);
  font-size: 12px;
  flex-shrink: 0;
}

.code-input :deep(textarea) {
  font-family: Consolas, "Courier New", monospace;
  font-size: 12px;
}

.connector {
  margin-top: 14px;
  border-top: 1px dashed var(--nb-border);
  padding-top: 10px;
}

.conn-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.conn-label {
  font-size: 12px;
  color: #606266;
  white-space: nowrap;
  width: 90px;
}

.edge-tools {
  margin-top: 8px;
}

</style>

<style>
body.no-select {
  user-select: none;
}
</style>
