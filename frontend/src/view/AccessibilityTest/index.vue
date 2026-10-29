<template>
  <div class="a11y-page">
    <!-- 1. APK 上传与信息 -->
    <a-card title="APK 上传与分析" size="small" class="block">
      <a-space align="start" wrap>
        <a-upload
          :before-upload="beforeUpload"
          :show-upload-list="false"
          accept=".apk"
          :disabled="uploading"
        >
          <a-button :loading="uploading">
            <upload-outlined /> 上传 APK
          </a-button>
        </a-upload>
        <span v-if="apkMeta" class="muted">{{ apkMeta.file_name }}（{{ formatSize(apkMeta.file_size_bytes) }}）</span>
      </a-space>

      <a-descriptions
        v-if="apkMeta"
        size="small"
        bordered
        :column="2"
        style="margin-top: 12px"
      >
        <a-descriptions-item label="包名">{{ apkMeta.application_id || '未知' }}</a-descriptions-item>
        <a-descriptions-item label="版本">
          {{ apkMeta.version_name || '未知' }}（code: {{ apkMeta.version_code || '未知' }}）
        </a-descriptions-item>
        <a-descriptions-item label="minSdk / targetSdk">
          {{ apkMeta.min_sdk || '?' }} / {{ apkMeta.target_sdk || '?' }}
        </a-descriptions-item>
        <a-descriptions-item label="SHA-256">
          <a-typography-text :copyable="{ text: apkMeta.sha256 }">
            {{ apkMeta.sha256.slice(0, 16) }}…
          </a-typography-text>
        </a-descriptions-item>
      </a-descriptions>
      <a-collapse v-if="apkMeta && apkMeta.permissions.length" ghost style="margin-top: 4px">
        <a-collapse-panel key="perms" :header="`权限列表（${apkMeta.permissions.length}）`">
          <div class="perm-list">
            <a-tag v-for="p in apkMeta.permissions" :key="p">{{ p }}</a-tag>
          </div>
        </a-collapse-panel>
      </a-collapse>
      <a-alert
        v-if="apkMeta && !apkMeta.apkanalyzer_available"
        type="warning"
        show-icon
        message="apkanalyzer 不可用，仅显示文件信息"
        style="margin-top: 8px"
      />
    </a-card>

    <!-- 2. 检测控制 -->
    <a-card size="small" class="block">
      <a-space wrap align="center">
        <span>AVD：</span>
        <a-select
          v-model:value="selectedAvd"
          :options="avdOptions"
          style="width: 220px"
          :disabled="sessionActive"
          placeholder="选择模拟器"
        />
        <a-button
          type="primary"
          :disabled="!apkMeta || sessionActive"
          :loading="isTransitional"
          @click="onStart"
        >
          开始检测
        </a-button>
        <a-button :disabled="status !== 'ready'" :loading="status === 'scanning'" @click="onScan">
          Scan
        </a-button>
        <a-button danger :disabled="!sessionActive" @click="onEnd">
          结束检测
        </a-button>
        <a-tag :color="statusColor">{{ statusText }}</a-tag>
        <span v-if="latestLog" class="muted">
          <a-spin v-if="isTransitional" size="small" style="margin-right: 6px" />{{ latestLog }}
        </span>
      </a-space>
      <a-alert
        v-if="sessionError"
        type="error"
        show-icon
        :message="sessionError"
        style="margin-top: 8px"
        closable
      />
    </a-card>

    <!-- 3. 汇总（结束后显示） -->
    <a-card v-if="summary && status === 'ended'" size="small" title="本次检测结果" class="block">
      <a-statistic
        title="扫描页面数 / 候选问题数"
        :value="`${summary.totals.scans} / ${summary.totals.findings}`"
        style="margin-bottom: 8px"
      />
      <div v-if="Object.keys(summary.totals.by_rule).length">
        <a-tag v-for="(count, rule) in summary.totals.by_rule" :key="rule" color="orange">
          {{ rule }}: {{ count }}
        </a-tag>
      </div>
      <a-empty v-else description="未发现候选问题（不代表页面完全无障碍）" />
    </a-card>

    <!-- 4. 实时画面 + 扫描结果 -->
    <a-row :gutter="12" class="block">
      <a-col :span="10">
        <a-card size="small" title="实时画面（ws-scrcpy）">
          <iframe
            v-if="streamUrl"
            :src="streamUrl"
            class="device-frame"
            allow="autoplay"
          />
          <a-empty v-else description="开始检测后此处显示 AVD 实时画面，可直接点击/滑动操作" />
        </a-card>
      </a-col>
      <a-col :span="14">
        <a-card size="small" :title="`扫描结果（${scans.length}）`">
          <a-alert
            v-if="limitations.length"
            type="info"
            show-icon
            style="margin-bottom: 8px"
            message="启发式扫描限制"
          >
            <template #description>
              <div v-for="(line, i) in limitations" :key="i" class="small">{{ line }}</div>
            </template>
          </a-alert>
          <a-empty v-if="!scans.length" description="在实时画面中操作 App 到目标页面后，点击 Scan" />
          <div v-for="scanItem in reversedScans" :key="scanItem.scan_id" class="scan-card">
            <div class="scan-head">
              <b>{{ scanItem.scan_id }}</b>
              <span v-if="scanItem.label" class="muted">· {{ scanItem.label }}</span>
              <span class="muted">· {{ scanItem.captured_at }}</span>
              <span v-if="scanItem.current_activity" class="muted">· {{ scanItem.current_activity }}</span>
              <a-tag v-if="scanItem.node_count != null" style="margin-left: auto">
                节点 {{ scanItem.node_count }} / 候选 {{ scanItem.finding_count ?? scanItem.findings.length }}
              </a-tag>
            </div>
            <div class="shot-wrap">
              <img :src="scanItem.screenshot_url" :alt="scanItem.scan_id" />
              <template v-for="(finding, i) in scanItem.findings" :key="i">
                <div
                  v-if="hasBounds(finding)"
                  class="finding-box"
                  :class="[finding.severity, { active: isActive(scanItem.scan_id, i) }]"
                  :style="boxStyle(finding, scanItem)"
                  :title="finding.title"
                  @click="selectFinding(scanItem.scan_id, i)"
                />
              </template>
            </div>
            <a-table
              v-if="scanItem.findings.length"
              :data-source="scanItem.findings"
              :columns="findingColumns"
              :pagination="false"
              size="small"
              :row-key="(_r: Finding, i?: number) => `${scanItem.scan_id}-${i}`"
              :row-class-name="(_r: Finding, i: number) => isActive(scanItem.scan_id, i) ? 'row-active' : ''"
              :custom-row="(_r: Finding, i?: number) => ({ onClick: () => selectFinding(scanItem.scan_id, i ?? 0) })"
            >
              <template #bodyCell="{ column, record }">
                <template v-if="column.key === 'severity'">
                  <a-tag :color="severityColor(record.severity)">{{ severityText(record.severity) }}</a-tag>
                </template>
                <template v-else-if="column.key === 'element'">
                  <div>{{ record.node?.text || record.node?.content_desc || '(无文本)' }}</div>
                  <div class="muted small">{{ record.node?.resource_id || record.node?.class_name || record.node?.class || '' }}</div>
                </template>
                <template v-else-if="column.key === 'evidence'">
                  <div>{{ record.evidence }}</div>
                  <div v-if="record.note" class="muted small">{{ record.note }}</div>
                </template>
              </template>
            </a-table>
            <p v-else class="muted">本页未命中规则（不代表页面完全无障碍）。</p>
          </div>
        </a-card>
      </a-col>
    </a-row>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import { UploadOutlined } from '@ant-design/icons-vue';
import {
  getAvds, uploadApk, startSession, getStatus, scan as apiScan,
  getScans, endSession, getSummary,
  type ApkMetadata, type Finding, type Scan, type SessionSummary,
} from './api';

const uploading = ref(false);
const apkMeta = ref<ApkMetadata | null>(null);
const apkId = ref('');

const avds = ref<string[]>([]);
const selectedAvd = ref<string>();
const avdOptions = computed(() => avds.value.map((name) => ({ value: name, label: name })));

const status = ref('idle');
const sessionError = ref<string | null>(null);
const streamUrl = ref<string | null>(null);
const latestLog = ref('');
const scans = ref<Scan[]>([]);
const summary = ref<SessionSummary | null>(null);
const lastScanCount = ref(0);

const activeFinding = ref<{ scanId: string; index: number } | null>(null);

const TRANSITIONAL = new Set(['starting', 'booting', 'installing', 'launching', 'scanning', 'ending']);
const isTransitional = computed(() => TRANSITIONAL.has(status.value) && status.value !== 'scanning');
const sessionActive = computed(() => TRANSITIONAL.has(status.value) || status.value === 'ready');
const statusText = computed(() => ({
  idle: '空闲', starting: '启动中', booting: 'AVD 冷启动中', installing: '安装 APK',
  launching: '启动应用', ready: '就绪', scanning: '扫描中', ending: '结束中',
  ended: '已结束', failed: '失败',
}[status.value] || status.value));
const statusColor = computed(() => ({
  ready: 'green', ended: 'default', failed: 'red', idle: 'default',
}[status.value] || 'processing'));

const reversedScans = computed(() => [...scans.value].reverse());

const findingColumns = [
  { title: '级别', key: 'severity', width: 90 },
  { title: '规则', dataIndex: 'title', key: 'title', width: 200 },
  { title: '元素', key: 'element', width: 220 },
  { title: '证据 / 备注', key: 'evidence' },
];

let pollTimer: ReturnType<typeof setInterval> | null = null;

function startPolling() {
  if (pollTimer) return;
  pollTimer = setInterval(refreshStatus, 1500);
}
function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

async function refreshStatus() {
  try {
    const res = await getStatus();
    const data = res.data;
    status.value = data.status || 'idle';
    sessionError.value = data.error || null;
    streamUrl.value = data.stream_url || null;
    const log = data.log || [];
    latestLog.value = log.length ? log[log.length - 1].message : '';
    if ((data.scan_count ?? 0) !== lastScanCount.value) {
      lastScanCount.value = data.scan_count ?? 0;
      await refreshScans();
    }
    if (status.value === 'ended') {
      await refreshSummary();
      stopPolling();
    }
    if (status.value === 'idle' || status.value === 'failed') {
      stopPolling();
    }
  } catch {
    /* 后端未启动等瞬时错误：保持上次状态 */
  }
}

async function refreshScans() {
  const res = await getScans();
  scans.value = res.data.scans || [];
}

async function refreshSummary() {
  try {
    const res = await getSummary();
    summary.value = res.data;
    scans.value = res.data.scans || scans.value;
  } catch { /* 会话已被清理 */ }
}

async function beforeUpload(file: File) {
  uploading.value = true;
  try {
    const res = await uploadApk(file);
    apkMeta.value = res.data.metadata;
    apkId.value = res.data.apk_id;
    summary.value = null;
    (window as any).message?.success(`已上传并解析：${res.data.metadata.file_name}`);
  } finally {
    uploading.value = false;
  }
  return false; // 手动上传
}

async function onStart() {
  if (!apkId.value || !selectedAvd.value) return;
  summary.value = null;
  scans.value = [];
  lastScanCount.value = 0;
  sessionError.value = null;
  try {
    await startSession({ avd_name: selectedAvd.value, apk_id: apkId.value });
    status.value = 'starting';
    startPolling();
  } catch { /* 拦截器已提示 */ }
}

async function onScan() {
  try {
    await apiScan({ label: '' });
    await refreshStatus();
    await refreshScans();
  } catch { /* 拦截器已提示 */ }
}

async function onEnd() {
  try {
    const res = await endSession();
    summary.value = res.data;
    scans.value = res.data.scans || [];
    status.value = 'ended';
    streamUrl.value = null;
    stopPolling();
  } catch { /* 拦截器已提示 */ }
}

function formatSize(bytes: number) {
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${(bytes / 1024).toFixed(1)} KB`;
}

const BOUNDS_RE = /\[(\d+),(\d+)\]\[(\d+),(\d+)\]/;

function findingBounds(finding: Finding): number[] | null {
  const b = finding.node?.bounds_normal;
  if (Array.isArray(b) && b.length === 4) return b;
  // 节点启发式规则同时带原始字符串边界 "[l,t][r,b]"
  const raw = finding.node?.bounds;
  if (typeof raw === 'string') {
    const m = BOUNDS_RE.exec(raw);
    if (m) return [Number(m[1]), Number(m[2]), Number(m[3]), Number(m[4])];
  }
  return null;
}

function hasBounds(finding: Finding) {
  return findingBounds(finding) !== null;
}

function boxStyle(finding: Finding, scanItem: Scan) {
  const b = findingBounds(finding) as number[];
  const w = scanItem.image_width || 1;
  const h = scanItem.image_height || 1;
  return {
    left: `${(b[0] / w) * 100}%`,
    top: `${(b[1] / h) * 100}%`,
    width: `${((b[2] - b[0]) / w) * 100}%`,
    height: `${((b[3] - b[1]) / h) * 100}%`,
  };
}

function selectFinding(scanId: string, index: number) {
  activeFinding.value = { scanId, index };
}
function isActive(scanId: string, index: number) {
  return activeFinding.value?.scanId === scanId && activeFinding.value?.index === index;
}

function severityColor(severity: string) {
  return severity === 'error' ? 'red' : severity === 'info' ? 'blue' : 'orange';
}
function severityText(severity: string) {
  return severity === 'error' ? '错误' : severity === 'info' ? '信息' : '待复核';
}

// 参考脚本的固定限制声明（扫描结果不是 WCAG 合规结论）
const limitations = computed(() => scans.value.find((s) => s.limitations?.length)?.limitations || []);

onMounted(async () => {
  try {
    const res = await getAvds();
    avds.value = res.data.avds || [];
    if (avds.value.includes('accessibility')) {
      selectedAvd.value = 'accessibility';
    } else if (avds.value.length) {
      selectedAvd.value = avds.value[0];
    }
  } catch { /* 后端未启动 */ }
  // 页面刷新后恢复进行中的会话状态
  await refreshStatus();
  if (sessionActive.value) startPolling();
  await refreshScans();
});

onBeforeUnmount(stopPolling);
</script>

<style scoped>
.a11y-page .block {
  margin-bottom: 12px;
}
.muted {
  color: #8c8c8c;
}
.small {
  font-size: 12px;
}
.perm-list {
  max-height: 120px;
  overflow: auto;
}
.device-frame {
  width: 100%;
  height: 70vh;
  border: 1px solid #d9d9d9;
  border-radius: 8px;
  background: #000;
}
.scan-card {
  border: 1px solid #f0f0f0;
  border-radius: 8px;
  padding: 8px;
  margin-bottom: 16px;
}
.scan-head {
  margin-bottom: 8px;
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
.shot-wrap {
  position: relative;
  display: inline-block;
  max-width: 100%;
  margin-bottom: 8px;
}
.shot-wrap img {
  display: block;
  max-width: 100%;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
}
.finding-box {
  position: absolute;
  border: 2px solid #fa8c16;
  background: rgba(250, 140, 22, 0.15);
  cursor: pointer;
  box-sizing: border-box;
}
.finding-box.error {
  border-color: #f5222d;
  background: rgba(245, 34, 45, 0.15);
}
.finding-box.active {
  border-width: 3px;
  box-shadow: 0 0 0 2px rgba(250, 140, 22, 0.4);
}
:deep(.row-active) td {
  background: #fff7e6 !important;
}
</style>
