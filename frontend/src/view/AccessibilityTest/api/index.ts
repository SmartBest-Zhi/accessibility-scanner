import request from "../../../utils/request";

export interface ApkMetadata {
  file_name: string;
  file_size_bytes: number;
  sha256: string;
  application_id: string | null;
  version_name: string | null;
  version_code: string | null;
  min_sdk: string | null;
  target_sdk: string | null;
  permissions: string[];
  apkanalyzer_available: boolean;
}

export interface FindingNode {
  index?: number;
  class?: string;
  class_name?: string;
  resource_id?: string;
  text?: string;
  content_desc?: string;
  bounds?: string | null;
  bounds_normal?: number[] | null;
  bounds_scaled?: number[] | null;
  width_dp?: number;
  height_dp?: number;
  height_ratio?: number;
}

export interface Finding {
  rule_id: string;
  severity: "warning" | "error" | "info";
  title: string;
  evidence: string;
  node: FindingNode;
  confidence: string;
  note: string;
}

export interface Scan {
  scan_id: string;
  label: string;
  captured_at: string;
  screenshot_url: string;
  image_width: number | null;
  image_height: number | null;
  current_package: string | null;
  current_activity: string | null;
  node_count?: number;
  finding_count?: number;
  ui_hierarchy_capture_error: string | null;
  limitations?: string[];
  findings: Finding[];
}

export interface SessionStatus {
  session_id: string | null;
  status: string;
  error?: string | null;
  avd_name?: string;
  udid?: string | null;
  stream_url?: string | null;
  scan_count?: number;
  finding_count?: number;
  apk_id?: string;
  log: { ts: string; status: string; message: string }[];
}

export interface SessionSummary {
  session_id: string;
  avd_name: string;
  started_at: string;
  ended_at: string | null;
  apk: ApkMetadata;
  device: Record<string, unknown>;
  scans: Scan[];
  totals: { scans: number; findings: number; by_rule: Record<string, number> };
}

const JSON_HEADERS = { "content-type": "application/json" };

export const getAvds = () => request({ url: "/api/avds", method: "get" });

export const uploadApk = (file: File) => {
  const formData = new FormData();
  formData.append("file", file);
  return request({ url: "/api/apk", method: "post", data: formData, timeout: 120000 });
};

export const startSession = (data: { avd_name: string; apk_id: string }) =>
  request({ url: "/api/session/start", method: "post", data, headers: JSON_HEADERS, timeout: 30000 });

export const getStatus = () => request({ url: "/api/session/status", method: "get" });

export const scan = (data: { label: string }) =>
  request({ url: "/api/session/scan", method: "post", data, headers: JSON_HEADERS, timeout: 90000 });

export const getScans = () => request({ url: "/api/session/scans", method: "get" });

export const endSession = () =>
  request({ url: "/api/session/end", method: "post", data: {}, headers: JSON_HEADERS, timeout: 90000 });

export const getSummary = () => request({ url: "/api/session/summary", method: "get" });
