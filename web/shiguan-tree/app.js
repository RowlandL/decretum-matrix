const fields = [
  "id",
  "court_code",
  "ancient_lineage",
  "lineage_display",
  "lineage_key",
  "topic",
  "phase",
  "status",
  "time",
  "keywords",
  "key_actions",
  "summary",
  "evidence",
  "next",
  "memory_decision",
  "record_type",
  "risk_level",
  "knowledge_value",
  "priority_level",
  "memory_content",
  "memory_reason",
  "source",
];

const defaultGraphBounds = { x: 0, y: 0, width: 1200, height: 760 };
const graphSpacing = {
  topic: 104,
  leaf: 74,
  keyword: 94,
  treeY: 88,
};
const entryVirtualRowHeight = 124;
const entryVirtualOverscan = 7;
const entryFullRenderLimit = 180;
const graphViewportPadding = 170;
const classPalette = [
  "#14906f",
  "#c98419",
  "#2f7fcb",
  "#c94f3d",
  "#7b62b5",
  "#7aa12f",
  "#b36a2f",
  "#168aa3",
];

const colorModeOrder = ["chain", "level", "off"];
const colorModeLabels = {
  chain: "链路色",
  level: "层级色",
  off: "素色",
};
const orbitRotationSpeed = 7.5;
const orbitEllipseRatio = 0.78;
const orbitPhysicsCellSize = 72;
const orbitPhysicsRepulsionLimit = 820;

const levelColorPalette = {
  root: "#2f6f5e",
  peer: "#168aa3",
  leaf: "#6f7a6a",
  keyword: "#9a4638",
  facet: "#8f6b2f",
  "lineage:-1": "#2f6f5e",
  "lineage:0": "#5b527d",
  "lineage:1": "#2f7fcb",
  "lineage:2": "#14906f",
  "lineage:3": "#c98419",
  "lineage:4": "#b36a2f",
  "lineage:5": "#c94f3d",
};

const phaseStages = [
  { label: "受旨定性", score: 1, terms: ["太子定性", "启动", "归档加载"] },
  { label: "拟旨考据", score: 2, terms: ["中书", "拟旨", "考据", "请太子转问", "澄清"] },
  { label: "三省会审", score: 3, terms: ["三省", "上奏", "会审", "太子回奏", "门下封驳"] },
  { label: "尚书分派", score: 4, terms: ["尚书", "分派", "调度"] },
  { label: "六部营造", score: 5, terms: ["六部", "工部", "兵部", "户部", "吏部", "刑部", "礼部", "执行", "营造", "办差"] },
  { label: "门下复核", score: 6, terms: ["门下复核", "复核", "验收"] },
  { label: "史馆实录", score: 7, terms: ["史馆", "实录", "记忆裁定", "奏报归档"] },
];

const statusLabels = {
  DONE: "已完成",
  DONE_WITH_CONCERNS: "已完成有余险",
  DONE_WITH_CAVEATS: "已完成有余险",
  APPROVED: "已准",
  APPROVED_WITH_CAVEATS: "有条件批准",
  REVIEW_READY: "待审",
  NEEDS_CONTEXT: "待问",
  BLOCKED: "受阻",
  REJECTED: "驳回",
  PROPOSE: "候选",
  WRITE: "写入",
  SKIP: "跳过",
  DEFERRED: "暂缓",
  DRAFT: "草稿",
};

const statusColors = {
  DONE: "#14906f",
  DONE_WITH_CONCERNS: "#c98419",
  DONE_WITH_CAVEATS: "#c98419",
  APPROVED: "#14906f",
  APPROVED_WITH_CAVEATS: "#c98419",
  REVIEW_READY: "#2f7fcb",
  NEEDS_CONTEXT: "#2f7fcb",
  BLOCKED: "#c94f3d",
  REJECTED: "#c94f3d",
  PROPOSE: "#7b62b5",
  WRITE: "#14906f",
  SKIP: "#7b8580",
  DEFERRED: "#7b8580",
  DRAFT: "#7b8580",
};

const gradeScore = { S: 7, A: 6, B: 5, C: 4, D: 3, E: 2, F: 1 };
const memoryScore = { WRITE: 7, PROPOSE: 5, DEFERRED: 3, SKIP: 1 };

const englishTermZh = {
  menxia: "门下省",
  zhongshu: "中书省",
  shangshu: "尚书省",
  court: "朝廷",
  startup: "启动",
  super: "完全控制权限",
  approval: "只读权限",
  autonomous: "管理权限",
  review: "复核",
  "read-only": "只读",
  subagent: "子工匠",
  agent: "工匠代理",
  agents: "工匠代理",
  agente: "工匠代理",
  skill: "技能",
  skills: "技能",
  "find-skills": "技能查找器",
  "skill-creator": "技能创建器",
  catalog: "官籍目录",
  "catalog map": "官籍图谱",
  registry: "官籍",
  "registry refresh": "官籍刷新",
  capability: "能力",
  "capability registry": "能力官籍",
  "standing agents": "常驻工匠代理",
  scripts: "脚本",
  script: "脚本",
  shiguan: "史馆",
  web: "网页",
  "web entry": "网页入口",
  state: "状态",
  directory: "目录",
  "court directory": "朝廷目录",
  "startup prerequisites": "启动前置条件",
  prerequisites: "前置条件",
  readable: "可读取",
  confirmed: "已确认",
  caveat: "余限",
  caveats: "余限",
  fresh: "新的",
  performed: "已执行",
  "not performed": "未执行",
  "no fresh registry refresh": "未执行新的官籍刷新",
  sandbox: "沙盒",
  yolo: "无沙盒直行",
  package: "安装包",
  index: "索引",
  graph: "图谱",
  "knowledge graph": "知识图谱",
};

const controlledFieldConfigs = {
  phase: {
    maxLength: 24,
    options: [
      ["太子定性", "起旨定调"],
      ["中书拟旨", "拟定方案"],
      ["中书勘验", "查证细节"],
      ["三省会审", "合议复核"],
      ["太子回奏", "上奏回覆"],
      ["尚书分派", "分派执行"],
      ["六部并行办差", "分工执行"],
      ["门下复核", "审查封驳"],
      ["史馆实录", "记录归档"],
      ["记忆裁定", "判定入库"],
      ["启动能力分类", "能力盘点"],
      ["手动修订", "人工编辑"],
    ],
  },
  status: {
    inputId: "statusField",
    maxLength: 28,
    transform: "upper",
    allowed: /[^A-Z_]/g,
    options: [
      ["DONE", "已完成"],
      ["DONE_WITH_CONCERNS", "完成有余险"],
      ["DONE_WITH_CAVEATS", "完成有附注"],
      ["APPROVED", "已批准"],
      ["APPROVED_WITH_CAVEATS", "附条件批准"],
      ["REVIEW_READY", "待复核"],
      ["NEEDS_CONTEXT", "待澄清"],
      ["BLOCKED", "受阻"],
      ["REJECTED", "驳回"],
      ["PROPOSE", "候选"],
      ["WRITE", "写入"],
      ["SKIP", "跳过"],
      ["DEFERRED", "暂缓"],
      ["DRAFT", "草稿"],
    ],
  },
  memory_decision: {
    maxLength: 12,
    transform: "upper",
    allowed: /[^A-Z_]/g,
    options: [
      ["WRITE", "写入长期记忆"],
      ["PROPOSE", "只列候选"],
      ["SKIP", "不入记忆"],
      ["DEFERRED", "暂缓裁定"],
    ],
  },
  record_type: {
    maxLength: 32,
    transform: "lower",
    allowed: /[^a-z0-9_-]/g,
    options: [
      ["checkpoint", "工作实录"],
      ["memory_decision", "记忆裁定"],
      ["manual_note", "人工补记"],
    ],
  },
  risk_level: {
    maxLength: 1,
    transform: "upper",
    allowed: /[^A-Z]/g,
    options: [["S", "极高"], ["A", "很高"], ["B", "较高"], ["C", "中等"], ["D", "较低"], ["E", "很低"], ["F", "最低"]],
  },
  knowledge_value: {
    maxLength: 1,
    transform: "upper",
    allowed: /[^A-Z]/g,
    options: [["S", "极有用"], ["A", "很有用"], ["B", "有用"], ["C", "一般"], ["D", "较少"], ["E", "很少"], ["F", "无用"]],
  },
  priority_level: {
    maxLength: 1,
    transform: "upper",
    allowed: /[^A-Z]/g,
    options: [["S", "即办"], ["A", "很高"], ["B", "较高"], ["C", "常规"], ["D", "较低"], ["E", "很低"], ["F", "搁置"]],
  },
};

const controlledDynamicOptions = new Map(Object.keys(controlledFieldConfigs).map((name) => [name, new Map()]));

const reduceMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches || false;
const finePointerQuery = window.matchMedia?.("(hover: hover) and (pointer: fine)");
const coarsePointerQuery = window.matchMedia?.("(hover: none), (pointer: coarse)");

function hasFineHover() {
  return finePointerQuery?.matches ?? true;
}

function compactViewport() {
  return window.innerWidth <= 760;
}

function touchOptimizedMode() {
  return coarsePointerQuery?.matches === true || !hasFineHover();
}

function isTextEntryElement(element) {
  return (
    element instanceof HTMLInputElement ||
    element instanceof HTMLTextAreaElement ||
    element instanceof HTMLSelectElement ||
    element?.isContentEditable === true
  );
}

function blurTextEntryForGraphInteraction() {
  const active = document.activeElement;
  if (!active || !isTextEntryElement(active)) return;
  active.blur();
}

function lowMotionMode() {
  return reduceMotion;
}

function heavyGraphMotionDisabled() {
  return reduceMotion || touchOptimizedMode() || state.entries.length > 90;
}

function defaultGraphLimit() {
  if (compactViewport()) return 70;
  if (touchOptimizedMode()) return 100;
  return 120;
}

const motion = {
  feedback: lowMotionMode() ? 0 : 120,
  state: lowMotionMode() ? 0 : 220,
  cluster: reduceMotion ? 0 : (touchOptimizedMode() ? 180 : 320),
  focus: reduceMotion ? 0 : (touchOptimizedMode() ? 240 : 420),
  reset: reduceMotion ? 0 : (touchOptimizedMode() ? 200 : 360),
};

function requestedTheme() {
  try {
    const theme = new URLSearchParams(window.location.search).get("theme");
    return theme === "dark" || theme === "light" ? theme : "";
  } catch (_) {
    return "";
  }
}

function storedTheme() {
  const requested = requestedTheme();
  if (requested) {
    return requested;
  }
  try {
    return localStorage.getItem("shiguan-tree-theme") || "";
  } catch (_) {
    return "";
  }
}

const state = {
  entries: [],
  peers: [],
  agentPresence: [],
  activePeerId: "",
  currentEntry: null,
  knowledgeGraph: null,
  selectedId: "",
  selectedNode: "",
  focusNode: "",
  pendingFocusNode: "",
  query: "",
  totalCount: 0,
  graphLimit: defaultGraphLimit(),
  graphMode: "star",
  graphBounds: { ...defaultGraphBounds },
  graphView: { ...defaultGraphBounds },
  showFacets: true,
  facetStateBeforeFocus: null,
  showList: true,
  showEditor: true,
  classColorMode: "chain",
  theme: storedTheme() === "dark" ? "dark" : "light",
  graphNodesById: new Map(),
  dragging: false,
  dragStart: null,
  activePointers: new Map(),
  graphGesture: null,
  blankClickCandidate: false,
  suppressNextNodeClick: false,
  suppressClickTimer: 0,
  hoveredNode: "",
  previousPositions: new Map(),
  viewAnimation: 0,
  tooltipFrame: 0,
  previousRadarPoints: [],
  graphSnapshot: null,
  graphViewportFrame: 0,
  graphViewFitPending: false,
  orbitNodeElements: new Map(),
  orbitEdgeElements: [],
  orbitGuideElements: [],
  orbitFrame: 0,
  orbitAngle: 0,
  orbitLastFrame: 0,
  orbitPaused: false,
  orbitEnabled: true,
  orbitCenter: { x: 0, y: 0 },
  orbitPhysics: new Map(),
  orbitVisibleIds: new Set(),
  graphFollowNode: "",
  graphFollowViewSize: null,
  graphFollowPausedUntil: 0,
  graphFollowLastRender: 0,
  focusReturnView: null,
  drawingGraph: false,
  entryRenderFrame: 0,
  showRawSummary: false,
  graphLimitTouched: false,
  editorEditing: false,
  importQueue: null,
  defaultShareHost: "",
  defaultSharePort: "",
  obsidianSync: null,
};

const el = {
  meta: document.querySelector("#meta"),
  status: document.querySelector("#status"),
  entries: document.querySelector("#entries"),
  searchInput: document.querySelector("#searchInput"),
  searchBtn: document.querySelector("#searchBtn"),
  layout: document.querySelector(".layout"),
  rebuildBtn: document.querySelector("#rebuildBtn"),
  growBtn: document.querySelector("#growBtn"),
  syncObsidianBtn: document.querySelector("#syncObsidianBtn"),
  obsidianRestPushBtn: document.querySelector("#obsidianRestPushBtn"),
  importTextBtn: document.querySelector("#importTextBtn"),
  generateKeyBtn: document.querySelector("#generateKeyBtn"),
  exportKeyBtn: document.querySelector("#exportKeyBtn"),
  manageKeyBtn: document.querySelector("#manageKeyBtn"),
  importKeyBtn: document.querySelector("#importKeyBtn"),
  peerStatusBar: document.querySelector("#peerStatusBar"),
  newBtn: document.querySelector("#newBtn"),
  form: document.querySelector("#entryForm"),
  graph: document.querySelector("#graph"),
  graphMeta: document.querySelector("#graphMeta"),
  graphDetail: document.querySelector("#graphDetail"),
  graphModeStar: document.querySelector("#graphModeStar"),
  graphModeTree: document.querySelector("#graphModeTree"),
  facetToggle: document.querySelector("#facetToggle"),
  orbitToggle: document.querySelector("#orbitToggle"),
  graphWrap: document.querySelector(".graph-wrap"),
  graphTooltip: document.querySelector("#graphTooltip"),
  graphLimitInput: document.querySelector("#graphLimitInput"),
  toggleListBtn: document.querySelector("#toggleListBtn"),
  toggleEditorBtn: document.querySelector("#toggleEditorBtn"),
  collapseListBtn: document.querySelector("#collapseListBtn"),
  collapseEditorBtn: document.querySelector("#collapseEditorBtn"),
  editEntryBtn: document.querySelector("#editEntryBtn"),
  saveEntryBtn: document.querySelector("#saveEntryBtn"),
  zoomOutBtn: document.querySelector("#zoomOutBtn"),
  zoomInBtn: document.querySelector("#zoomInBtn"),
  zoomResetBtn: document.querySelector("#zoomResetBtn"),
  zoomLevel: document.querySelector("#zoomLevel"),
  classColorToggle: document.querySelector("#classColorToggle"),
  themeToggle: document.querySelector("#themeToggle"),
  profile: document.querySelector("#entryProfile"),
  profileStage: document.querySelector("#profileStage"),
  profileStatus: document.querySelector("#profileStatus"),
  profileClass: document.querySelector("#profileClass"),
  profileRadar: document.querySelector("#profileRadar"),
  displaySummary: document.querySelector("#display_summary"),
  rawSummaryToggle: document.querySelector("#rawSummaryToggle"),
  rawSummaryState: document.querySelector("#rawSummaryState"),
  keyGenerateDialog: document.querySelector("#keyGenerateDialog"),
  keyGenerateForm: document.querySelector("#keyGenerateForm"),
  keyGenerateTitle: document.querySelector("#keyGenerateTitle"),
  keyGenerateHelp: document.querySelector("#keyGenerateHelp"),
  keyRole: document.querySelector("#keyRole"),
  keyExpiryPreset: document.querySelector("#keyExpiryPreset"),
  keyShareHost: document.querySelector("#keyShareHost"),
  keySharePort: document.querySelector("#keySharePort"),
  keyManageDialog: document.querySelector("#keyManageDialog"),
  keyManageForm: document.querySelector("#keyManageForm"),
  keyManageList: document.querySelector("#keyManageList"),
  keyManageSelect: document.querySelector("#keyManageSelect"),
  keyManageExpiryPreset: document.querySelector("#keyManageExpiryPreset"),
  obsidianSyncDialog: document.querySelector("#obsidianSyncDialog"),
  obsidianSyncForm: document.querySelector("#obsidianSyncForm"),
  obsidianManualMode: document.querySelector("#obsidianManualMode"),
  obsidianAutoMode: document.querySelector("#obsidianAutoMode"),
  obsidianEndpoint: document.querySelector("#obsidianEndpoint"),
  obsidianApiKey: document.querySelector("#obsidianApiKey"),
  obsidianImportQuery: document.querySelector("#obsidianImportQuery"),
  obsidianImportPaths: document.querySelector("#obsidianImportPaths"),
  obsidianOutputFolder: document.querySelector("#obsidianOutputFolder"),
  obsidianAutoEnabled: document.querySelector("#obsidianAutoEnabled"),
  obsidianVerifySsl: document.querySelector("#obsidianVerifySsl"),
  obsidianSyncResult: document.querySelector("#obsidianSyncResult"),
  keyFileInput: document.querySelector("#keyFileInput"),
  textFileInput: document.querySelector("#textFileInput"),
  obsidianFileInput: document.querySelector("#obsidianFileInput"),
};

if (!el.graphTooltip && el.graphWrap) {
  el.graphTooltip = document.createElement("div");
  el.graphTooltip.id = "graphTooltip";
  el.graphTooltip.className = "graph-tooltip";
  el.graphWrap.append(el.graphTooltip);
}

if (el.graphLimitInput) {
  el.graphLimitInput.value = String(state.graphLimit);
}

function field(name) {
  if (name === "status") {
    return document.querySelector("#statusField");
  }
  return document.querySelector(`#${name}`);
}

function syncRawSummaryFromDisplay() {
  if (!state.showRawSummary || !el.displaySummary) return;
  const rawField = field("summary");
  if (rawField) {
    rawField.value = el.displaySummary.value;
  }
}

function updateRawSummaryVisibility(entry = null) {
  if (!el.rawSummaryToggle || !el.displaySummary) return;
  const currentEntry = entry || formToEntry({ syncRaw: false });
  el.rawSummaryToggle.setAttribute("aria-expanded", String(state.showRawSummary));
  el.rawSummaryToggle.textContent = state.showRawSummary ? "隐藏原文" : "显示原文";
  el.displaySummary.classList.toggle("raw-summary-mode", state.showRawSummary);
  el.displaySummary.readOnly = !state.editorEditing || !state.showRawSummary;
  el.displaySummary.value = state.showRawSummary
    ? (field("summary")?.value || "")
    : displaySummaryZh(currentEntry);
  if (el.rawSummaryState) {
    el.rawSummaryState.textContent = state.showRawSummary ? "正在显示源摘要" : "正在显示中文摘要";
  }
}

function peerMachineName(peer = {}) {
  const node = peer.node && typeof peer.node === "object" ? peer.node : {};
  return String(node.node_name || node.node_id || peer.peer_id || "共享史馆");
}

function peerNodeId(peer = {}) {
  const raw = String(peer.peer_id || peer.key_id || peerMachineName(peer));
  return `peer:${raw}`;
}

function peerNodeIdForId(peerId) {
  return `peer:${String(peerId || "")}`;
}

function peerForId(peerId) {
  const id = String(peerId || "");
  return state.peers.find((peer) => String(peer.peer_id || "") === id) || null;
}

function peerRoleLabel(role) {
  return String(role || "read") === "edit" ? "可编辑密钥" : "只读密钥";
}

function peerStatusLabel(status) {
  return {
    collapsed: "未展开",
    online: "已连接",
    offline: "离线",
    disabled: "已停用",
    expired: "已过期",
  }[String(status || "collapsed")] || "未展开";
}

function peerStatusColor(peer = {}) {
  const status = String(peer.status || "collapsed");
  if (status === "online") return "#14906f";
  if (status === "offline" || status === "expired" || status === "disabled") return "#c94f3d";
  return "#2f7fcb";
}

function peerStatusClass(peer = {}) {
  const status = String(peer.status || "collapsed");
  if (status === "online") return "online";
  if (status === "offline") return "offline";
  if (status === "disabled" || status === "expired") return "disabled";
  return "unknown";
}

function agentStatusLabel(status) {
  return String(status || "offline") === "online" ? "在线" : "离线";
}

function renderPeerStatusBar() {
  if (!el.peerStatusBar) return;
  const peers = Array.isArray(state.peers) ? state.peers : [];
  const agents = Array.isArray(state.agentPresence) ? state.agentPresence : [];
  el.peerStatusBar.replaceChildren();
  const activeAgents = agents.filter((agent) => agent.status === "online");
  const agentSummary = document.createElement("span");
  agentSummary.className = "peer-status-chip summary";
  agentSummary.textContent = `AI 心跳 ${activeAgents.length}`;
  el.peerStatusBar.append(agentSummary);
  for (const agent of activeAgents.slice(0, 4)) {
    const chip = document.createElement("span");
    chip.className = "peer-status-chip online";
    chip.title = [
      agent.label || agent.agent_id || "AI",
      `状态：${agentStatusLabel(agent.status)}`,
      agent.last_seen ? `最后运行：${agent.last_seen}` : "",
      agent.event ? `事件：${agent.event}` : "",
    ].filter(Boolean).join("\n");
    const dot = document.createElement("span");
    dot.className = "peer-status-dot";
    dot.setAttribute("aria-hidden", "true");
    const name = document.createElement("span");
    name.className = "peer-status-name";
    name.textContent = truncate(agent.label || agent.agent_id || "AI", 12);
    chip.append(dot, name);
    el.peerStatusBar.append(chip);
  }
  const online = peers.filter((peer) => peer.status === "online").length;
  const offline = peers.filter((peer) => peer.status === "offline").length;
  const disabled = peers.filter((peer) => peer.status === "disabled" || peer.status === "expired").length;
  const summary = document.createElement("span");
  summary.className = "peer-status-chip summary";
  summary.textContent = peers.length
    ? `共享 ${peers.length} 台 · 在线 ${online} · 离线 ${offline}${disabled ? ` · 停用 ${disabled}` : ""}`
    : "共享 0 台";
  el.peerStatusBar.append(summary);
  for (const peer of peers.slice(0, 5)) {
    const chip = document.createElement("span");
    chip.className = `peer-status-chip ${peerStatusClass(peer)}`;
    chip.title = [
      peerMachineName(peer),
      `状态：${peerStatusLabel(peer.status)}`,
      peer.checked_at ? `校验：${peer.checked_at}` : "",
      peer.error ? `错误：${peer.error}` : "",
    ].filter(Boolean).join("\n");
    const dot = document.createElement("span");
    dot.className = "peer-status-dot";
    dot.setAttribute("aria-hidden", "true");
    const name = document.createElement("span");
    name.className = "peer-status-name";
    name.textContent = truncate(peerMachineName(peer), 14);
    chip.append(dot, name);
    el.peerStatusBar.append(chip);
  }
  if (peers.length > 5) {
    const more = document.createElement("span");
    more.className = "peer-status-chip summary";
    more.textContent = `+${peers.length - 5}`;
    el.peerStatusBar.append(more);
  }
}

function peerExpanded(peer = {}) {
  return Boolean(peer.peer_id && state.activePeerId === String(peer.peer_id));
}

function entryEditBlockReason(entry = {}) {
  if (!entry?.peer_id) return "";
  if (entry.read_only || String(entry.peer_role || "read") !== "edit") {
    return "这条树叶来自共享史馆，当前密钥为只读；需要导入该机器的编辑密钥后才能修改。";
  }
  return "";
}

function setEditorEditing(editing, { keepFocus = false } = {}) {
  if (state.showRawSummary) {
    syncRawSummaryFromDisplay();
  }
  const requestedEditing = Boolean(editing);
  const blockReason = requestedEditing ? entryEditBlockReason(state.currentEntry) : "";
  state.editorEditing = blockReason ? false : requestedEditing;
  if (blockReason) {
    setStatus(blockReason, true);
  }
  el.form?.classList.toggle("editor-locked", !state.editorEditing);
  el.form?.classList.toggle("peer-readonly", Boolean(entryEditBlockReason(state.currentEntry)));
  el.editEntryBtn?.setAttribute("aria-pressed", String(state.editorEditing));
  if (el.editEntryBtn) {
    el.editEntryBtn.textContent = "编辑";
    el.editEntryBtn.title = state.editorEditing ? "编辑模式已开启；再次点击回到只读查看。" : "只读查看；点击后开放树叶编辑。";
  }
  if (el.saveEntryBtn) {
    el.saveEntryBtn.disabled = !state.editorEditing;
    el.saveEntryBtn.setAttribute("aria-disabled", String(!state.editorEditing));
  }
  for (const control of el.form?.querySelectorAll("input, textarea, select") || []) {
    if (control.type === "hidden") continue;
    const fixedReadonly = ["court_code", "ancient_lineage"].includes(control.id);
    const displaySummaryReadonly = control.id === "display_summary" && !state.showRawSummary;
    if (control instanceof HTMLSelectElement) {
      control.disabled = !state.editorEditing;
    } else {
      control.readOnly = !state.editorEditing || fixedReadonly || displaySummaryReadonly;
    }
  }
  updateRawSummaryVisibility();
  if (!state.editorEditing && !keepFocus) {
    blurTextEntryForGraphInteraction();
  }
}

function setStatus(message, warn = false) {
  el.status.textContent = message;
  el.status.classList.toggle("warn", warn);
}

function downloadTextFile(filename, text, type = "application/x-shiguan-key") {
  const blob = new Blob([text], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename || "shiguan-peer-key.shiguan-key";
  link.rel = "noopener";
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function serviceAccessText(data) {
  const localUrl = data.local_url || "http://127.0.0.1:8765/";
  const lanUrls = Array.isArray(data.lan_urls) ? data.lan_urls.filter(Boolean) : [];
  if (!lanUrls.length) {
    return `本机 ${localUrl}`;
  }
  return `本机 ${localUrl}；局域网 ${lanUrls.join("、")}`;
}

function applyTheme() {
  const dark = state.theme === "dark";
  document.documentElement.dataset.theme = state.theme;
  el.themeToggle?.setAttribute("aria-pressed", String(dark));
  if (el.themeToggle) {
    el.themeToggle.textContent = dark ? "昼明" : "暗夜";
  }
  try {
    localStorage.setItem("shiguan-tree-theme", state.theme);
  } catch (_) {
    // Theme storage is best-effort; the page still works without it.
  }
}

function colorModeEnabled() {
  return state.classColorMode !== "off";
}

function colorModeLabel() {
  return colorModeLabels[state.classColorMode] || colorModeLabels.chain;
}

function updateColorModeControl() {
  if (!el.classColorToggle) return;
  const enabled = colorModeEnabled();
  el.classColorToggle.setAttribute("aria-pressed", String(enabled));
  el.classColorToggle.textContent = colorModeLabel();
  el.classColorToggle.title = "切换分类色：链路色 / 层级色 / 素色";
}

function listValue(value) {
  if (Array.isArray(value)) {
    return value.join(", ");
  }
  return value || "";
}

function controlledInputName(name) {
  return name === "status" ? "statusField" : name;
}

function controlledFieldInput(name) {
  const config = controlledFieldConfigs[name];
  if (!config) return null;
  return document.querySelector(`#${config.inputId || controlledInputName(name)}`);
}

function normalizeControlledInput(value, config = {}) {
  let text = String(value || "");
  if (config.transform === "upper") {
    text = text.toUpperCase();
  } else if (config.transform === "lower") {
    text = text.toLowerCase();
  }
  if (config.allowed) {
    text = text.replace(config.allowed, "");
  }
  if (config.maxLength) {
    text = text.slice(0, config.maxLength);
  }
  return text;
}

function controlledOptions(name) {
  const config = controlledFieldConfigs[name];
  const options = new Map();
  for (const [value, desc] of config?.options || []) {
    options.set(value, desc);
  }
  for (const [value, desc] of controlledDynamicOptions.get(name) || []) {
    if (!options.has(value)) {
      options.set(value, desc);
    }
  }
  return [...options.entries()].map(([value, desc]) => ({ value, desc }));
}

function controlledMatch(name, rawValue) {
  const config = controlledFieldConfigs[name];
  const value = normalizeControlledInput(rawValue, config);
  const lower = value.toLowerCase();
  const options = controlledOptions(name);
  const exact = options.find((item) => item.value.toLowerCase() === lower);
  if (exact) return { value, exact, options };
  const matches = options.filter((item) => item.value.toLowerCase().startsWith(lower));
  return { value, exact: null, matches, options };
}

function controlledHelpElement(input) {
  return input?.closest("label")?.querySelector(".field-help");
}

function setControlledHelp(name, value, explicitDesc = "") {
  const input = controlledFieldInput(name);
  const help = controlledHelpElement(input);
  if (!help) return;
  if (!help.dataset.baseHelp) {
    help.dataset.baseHelp = help.textContent;
  }
  const match = controlledMatch(name, value);
  const desc = explicitDesc || match.exact?.desc || match.matches?.[0]?.desc || "";
  const suffix = desc ? `｜${desc}` : "｜Tab 补全；只允许候选前缀";
  help.textContent = `${help.dataset.baseHelp}${suffix}`;
  help.classList.toggle("field-help-warn", Boolean(value && !match.exact && !match.matches?.length));
}

function updateControlledDatalists() {
  for (const name of Object.keys(controlledFieldConfigs)) {
    const input = controlledFieldInput(name);
    if (!input) continue;
    let datalist = document.querySelector(`#${name}Options`);
    if (!datalist) {
      datalist = document.createElement("datalist");
      datalist.id = `${name}Options`;
      document.body.append(datalist);
    }
    datalist.replaceChildren();
    for (const option of controlledOptions(name)) {
      const node = document.createElement("option");
      node.value = option.value;
      node.label = option.desc;
      datalist.append(node);
    }
    input.setAttribute("list", datalist.id);
    input.setAttribute("maxlength", String(controlledFieldConfigs[name].maxLength));
  }
}

function addDynamicControlledOption(name, value) {
  const config = controlledFieldConfigs[name];
  const normalized = normalizeControlledInput(value, config).trim();
  if (!normalized) return;
  const dynamic = controlledDynamicOptions.get(name);
  if (!dynamic?.has(normalized)) {
    dynamic?.set(normalized, "旧记录取值");
  }
}

function refreshControlledOptionsFromEntries(entries = []) {
  for (const entry of entries) {
    for (const name of Object.keys(controlledFieldConfigs)) {
      addDynamicControlledOption(name, entry[name]);
    }
  }
  updateControlledDatalists();
}

function handleControlledInput(name, event) {
  const input = event.currentTarget;
  const config = controlledFieldConfigs[name];
  const previous = input.dataset.lastValid || "";
  const normalized = normalizeControlledInput(input.value, config);
  const match = controlledMatch(name, normalized);
  const allowed = !normalized || Boolean(match.exact || match.matches?.length);
  input.value = allowed ? normalized : previous;
  input.dataset.lastValid = input.value;
  input.classList.toggle("controlled-invalid", !allowed);
  setControlledHelp(name, input.value);
}

function completeControlledInput(name, input) {
  const match = controlledMatch(name, input.value);
  const option = match.exact || match.matches?.[0];
  if (!option) return false;
  input.value = option.value;
  input.dataset.lastValid = option.value;
  input.classList.remove("controlled-invalid");
  setControlledHelp(name, option.value, option.desc);
  input.dispatchEvent(new Event("input", { bubbles: true }));
  return true;
}

function initializeControlledFields() {
  updateControlledDatalists();
  for (const name of Object.keys(controlledFieldConfigs)) {
    const input = controlledFieldInput(name);
    if (!input || input.dataset.controlledReady) continue;
    input.dataset.controlledReady = "true";
    input.dataset.lastValid = input.value || "";
    input.addEventListener("input", (event) => handleControlledInput(name, event));
    input.addEventListener("keydown", (event) => {
      if (event.key === "Tab" && input.value) {
        if (completeControlledInput(name, input)) {
          event.preventDefault();
        }
      }
    });
    input.addEventListener("change", () => {
      completeControlledInput(name, input);
      setControlledHelp(name, input.value);
    });
    setControlledHelp(name, input.value);
  }
}

function uniqueText(values, limit = 16) {
  const seen = new Set();
  const output = [];
  for (const value of values) {
    const text = String(value || "").trim();
    if (!text) continue;
    const key = text.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    output.push(text);
    if (output.length >= limit) break;
  }
  return output;
}

function truncate(value, max = 180) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  if (text.length <= max) {
    return text;
  }
  return `${text.slice(0, max - 1)}...`;
}

function hasChinese(value) {
  return /[\u4e00-\u9fff]/.test(String(value || ""));
}

function hasEnglish(value) {
  return /[A-Za-z]/.test(String(value || ""));
}

function chineseDisplayFragment(value, max = 180) {
  let text = String(value || "").replace(/\s+/g, " ").trim();
  if (!hasChinese(text)) return "";
  text = text
    .replace(/[A-Za-z][A-Za-z0-9_.\\/-]*/g, "")
    .replace(/[`'"<>()[\]{}]/g, "")
    .replace(/\s+/g, " ")
    .replace(/^[\s；;，,：:_|\-]+|[\s；;，,：:_|\-]+$/g, "");
  return hasChinese(text) ? truncate(text, max) : "";
}

function chineseOnlyList(values, limit = 12) {
  const source = Array.isArray(values) ? values : [values];
  return uniqueText(source.filter((value) => hasChinese(value) && !hasEnglish(value)), limit);
}

function translateEnglishSummary(value, max = 140) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  if (!hasEnglish(text)) return "";
  const lower = text.toLowerCase();
  if (lower.includes("menxia") && lower.includes("read-only") && lower.includes("startup prerequisites")) {
    return truncate("门下只读子工匠已核验启动前置条件：朝廷工作目录、技能查找器、技能创建器、能力目录地图、常驻工匠、脚本、史馆状态与网页入口均可读取；余限为本次只读复核未刷新能力官籍。", max);
  }
  const phrases = Object.keys(englishTermZh)
    .sort((a, b) => b.length - a.length)
    .filter((term) => lower.includes(term))
    .map((term) => englishTermZh[term]);
  const uniquePhrases = uniqueText(phrases, 12);
  let prefix = "";
  if (lower.includes("confirmed") && lower.includes("prerequisites")) {
    prefix = "已确认启动前置条件";
  } else if (lower.includes("no fresh registry refresh") || (lower.includes("registry refresh") && lower.includes("no "))) {
    prefix = "未执行新的官籍刷新";
  } else if (lower.includes("readable")) {
    prefix = "已确认相关目录与入口可读取";
  } else if (uniquePhrases.length) {
    prefix = "源摘要涉及";
  }
  let suffix = "";
  if (lower.includes("caveat") && (lower.includes("registry refresh") || lower.includes("refresh"))) {
    suffix = "；余限为尚未执行新的官籍刷新";
  } else if (lower.includes("caveat")) {
    suffix = "；仍有余限需复核";
  }
  const details = uniquePhrases.join("、");
  if (details && prefix) {
    return truncate(`${prefix}：${details}${suffix}。`, max);
  }
  if (prefix) {
    return truncate(`${prefix}${suffix}。`, max);
  }
  return "";
}

function escapeText(value) {
  return String(value || "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[char]));
}

function hashText(value) {
  let total = 0;
  const text = String(value || "");
  for (let index = 0; index < text.length; index += 1) {
    total = ((total * 31) + text.charCodeAt(index)) >>> 0;
  }
  return total;
}

function lineagePathPartsFromKey(key = "") {
  return String(key || "")
    .split(/[\/>·]/)
    .map((part) => part.trim())
    .filter(Boolean);
}

function entryLineageParts(entry = {}) {
  const parts = entry.lineage_parts || {};
  const fallback = lineagePathPartsFromKey(entry.lineage_key || entry.ancient_lineage || entry.lineage_display);
  return [
    parts.zhi || fallback[0],
    parts.men || fallback[1],
    parts.gang || fallback[2],
    parts.mu || fallback[3],
    parts.tiao || fallback[4],
    parts.zhao || fallback[5] || displayTitleZh(entry, 18),
  ].filter(Boolean);
}

function chainColorKeyForEntry(entry = {}) {
  return entryLineageParts(entry)[0] || entry.lineage_key || entryBranch(entry) || entry.topic || "unclassified";
}

function chainColorKeyForLineageNode(node = {}) {
  const path = String(node.id || "").replace(/^lineage:\d+:/, "");
  return lineagePathPartsFromKey(path)[0] || node.rawLabel || node.label || node.id || "unclassified";
}

function classColorForEntry(entry = {}) {
  if (state.classColorMode === "level") return levelColorPalette.leaf;
  const key = chainColorKeyForEntry(entry);
  return classPalette[hashText(key) % classPalette.length];
}

function dominantEntryClassKey(entries = []) {
  const counts = new Map();
  for (const entry of entries) {
    const key = chainColorKeyForEntry(entry);
    counts.set(key, (counts.get(key) || 0) + 1);
  }
  return [...counts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] || "";
}

function classColorForNode(node = {}) {
  if (node.type === "peer") return peerStatusColor(node.peer);
  if (state.classColorMode === "level") {
    if (node.type === "lineage") {
      return levelColorPalette[`lineage:${Number(node.lineageIndex || 0)}`] || nodeColor(node.type);
    }
    return levelColorPalette[node.type] || nodeColor(node.type);
  }
  if (node.entry) return classColorForEntry(node.entry);
  const key = node.type === "lineage"
    ? chainColorKeyForLineageNode(node)
    : (node.branch || node.classKey || dominantEntryClassKey(node.entries || []) || node.label || node.id || "unclassified");
  return classPalette[hashText(key) % classPalette.length];
}

function statusLabel(status) {
  const key = String(status || "UNKNOWN").trim().toUpperCase();
  return statusLabels[key] || status || "未定";
}

function memoryDecisionLabel(value) {
  const key = String(value || "").trim().toUpperCase();
  return {
    WRITE: "写入",
    PROPOSE: "候选",
    SKIP: "跳过",
    DEFERRED: "暂缓",
  }[key] || chineseDisplayFragment(value, 24) || "未裁定";
}

function statusColor(status) {
  const key = String(status || "UNKNOWN").trim().toUpperCase();
  return statusColors[key] || "#66706a";
}

function phaseStage(entry = {}) {
  const phase = String(entry.phase || "");
  const haystack = [
    phase,
    entry.summary,
    entry.memory_content,
    entry.key_actions,
  ].flat().join(" ");
  for (const stage of phaseStages) {
    if (stage.terms.some((term) => haystack.includes(term))) {
      return stage;
    }
  }
  return { label: phase || "未定", score: 1, terms: [] };
}

function gradeValue(value, fallback = "C") {
  const key = String(value || fallback).trim().toUpperCase()[0] || fallback;
  return gradeScore[key] || gradeScore[fallback] || 4;
}

function memoryValue(value) {
  const key = String(value || "DEFERRED").trim().toUpperCase();
  return memoryScore[key] || memoryScore.DEFERRED;
}

function entryRadarMetrics(entry = {}) {
  const stage = phaseStage(entry);
  return [
    { label: "朝程", value: stage.score, detail: stage.label },
    { label: "记忆", value: memoryValue(entry.memory_decision), detail: String(entry.memory_decision || "DEFERRED") },
    { label: "风险", value: gradeValue(entry.risk_level, entry.court_code_parts?.risk || "C"), detail: String(entry.risk_level || entry.court_code_parts?.risk || "C").toUpperCase() },
    { label: "价值", value: gradeValue(entry.knowledge_value, entry.court_code_parts?.knowledge_value || "C"), detail: String(entry.knowledge_value || entry.court_code_parts?.knowledge_value || "C").toUpperCase() },
    { label: "优先", value: gradeValue(entry.priority_level, entry.court_code_parts?.priority || "C"), detail: String(entry.priority_level || entry.court_code_parts?.priority || "C").toUpperCase() },
  ];
}

function formToEntry(options = {}) {
  if (options.syncRaw !== false) {
    syncRawSummaryFromDisplay();
  }
  const entry = {};
  for (const name of fields) {
    const input = field(name);
    if (input) {
      entry[name] = input.value.trim();
    }
  }
  return entry;
}

function fillForm(entry = {}, options = {}) {
  state.currentEntry = entry;
  for (const name of fields) {
    const input = field(name);
    if (input) {
      input.value = listValue(entry[name]);
      if (controlledFieldConfigs[name]) {
        input.dataset.lastValid = input.value;
        setControlledHelp(name, input.value);
      }
    }
  }
  if (el.displaySummary) {
    el.displaySummary.value = displaySummaryZh(entry);
  }
  state.showRawSummary = false;
  updateRawSummaryVisibility();
  state.selectedId = String(entry.id || "");
  const graphIdentityAvailable = Boolean(entry.id || entry.topic || entry.time);
  state.selectedNode = graphIdentityAvailable ? entryNodeId(entry) : "";
  if (!state.selectedNode && !options.preserveFocus) {
    state.focusNode = "";
    state.pendingFocusNode = "";
  }
  setEditorEditing(options.editing === true);
  renderEntryProfile(entry);
  renderEntries();
  renderGraph();
}

function entryNodeId(entry) {
  return `leaf:${entry.id || `${entry.topic || "未命名"}:${entry.time || ""}`}`;
}

function revealPanelsForEntry() {
  let changed = false;
  if (!state.showList) {
    state.showList = true;
    changed = true;
  }
  if (!state.showEditor) {
    state.showEditor = true;
    changed = true;
  }
  if (changed) {
    updatePanelVisibility();
  }
}

function revealEntryInList(entryId) {
  if (!entryId) return;
  const index = state.entries.findIndex((entry) => String(entry.id || "") === String(entryId));
  if (index >= 0) {
    const targetTop = Math.max(0, (index * entryVirtualRowHeight) - Math.round((el.entries.clientHeight || 520) / 2));
    el.entries.scrollTo({ top: targetTop, behavior: reduceMotion ? "auto" : "smooth" });
    scheduleRenderEntries();
  }
  const target = el.entries.querySelector(`[data-entry-id="${CSS.escape(entryId)}"]`);
  if (target) {
    target.scrollIntoView({ block: "center", behavior: reduceMotion ? "auto" : "smooth" });
  }
}

function revealEditor() {
  el.form.scrollTo({ top: 0, behavior: "smooth" });
}

function revealGraphDetail() {
  if (!touchOptimizedMode() || !el.graphDetail) return;
  el.graphDetail.scrollIntoView({ block: "nearest", behavior: reduceMotion ? "auto" : "smooth" });
}

function graphFocusActive() {
  return Boolean(state.focusNode || state.pendingFocusNode);
}

function graphFacetsVisible() {
  return state.showFacets || graphFocusActive();
}

function syncFacetToggle() {
  if (!el.facetToggle) return;
  const visible = graphFacetsVisible();
  const forced = visible && !state.showFacets;
  el.facetToggle.setAttribute("aria-pressed", visible ? "true" : "false");
  el.facetToggle.classList.toggle("forced", forced);
}

function syncOrbitToggle() {
  if (!el.orbitToggle) return;
  const active = orbitGraphActive();
  el.orbitToggle.setAttribute("aria-pressed", state.orbitEnabled ? "true" : "false");
  el.orbitToggle.classList.toggle("forced", state.orbitEnabled && !active);
  el.orbitToggle.textContent = state.orbitEnabled ? "旋转" : "静止";
  el.orbitToggle.title = active
    ? "星图谱系层级旋转已开启"
    : "旋转只作用于普通星图；树图、聚焦、拖拽和标签暂停时会暂停";
}

function resetOrbitState() {
  state.orbitNodeElements = new Map();
  state.orbitEdgeElements = [];
  state.orbitGuideElements = [];
  state.orbitVisibleIds = new Set();
}

function clearGraphFollow() {
  state.graphFollowNode = "";
  state.graphFollowViewSize = null;
  state.graphFollowPausedUntil = 0;
  state.graphFollowLastRender = 0;
}

function clearGraphSelection(options = {}) {
  if (!state.selectedNode && !state.focusNode && !state.pendingFocusNode) return;
  clearGraphFollow();
  state.selectedNode = "";
  if (options.clearEntry) {
    state.selectedId = "";
  }
  hideNodeTooltip();
  showGraphDetail(null);
  renderGraph();
}

function rememberFocusReturnView() {
  if (graphFocusActive() || state.focusReturnView) return;
  state.focusReturnView = {
    mode: state.graphMode,
    width: state.graphView.width,
    height: state.graphView.height,
  };
}

function graphViewCenteredOnPoint(point, size = state.graphView) {
  if (!point) return null;
  const width = Number(size?.width) || state.graphView.width;
  const height = Number(size?.height) || state.graphView.height;
  return clampGraphView({
    x: point.x - width / 2,
    y: point.y - height / 2,
    width,
    height,
  });
}

function graphPointForNodeId(nodeId, orbitPoints = null) {
  if (!nodeId) return null;
  const node = state.graphSnapshot?.positions?.get(nodeId);
  if (!node) return null;
  return orbitPoints?.get(nodeId) || orbitPointForNode(node);
}

function applyGraphFollow(orbitPoints = null, elapsedMs = 16, options = {}) {
  if (!state.graphFollowNode) return;
  if (state.dragging || state.graphGesture) return;
  if (state.viewAnimation && !options.force) return;
  const now = performance.now();
  if (!options.force && now < state.graphFollowPausedUntil) return;
  const point = graphPointForNodeId(state.graphFollowNode, orbitPoints);
  if (!point) {
    clearGraphFollow();
    return;
  }
  const target = graphViewCenteredOnPoint(point, state.graphFollowViewSize || state.focusReturnView || state.graphView);
  if (!target) return;
  if (options.immediate) {
    state.graphView = target;
  } else {
    const strength = clamp(elapsedMs / 130, 0.08, 0.3);
    state.graphView = {
      x: state.graphView.x + (target.x - state.graphView.x) * strength,
      y: state.graphView.y + (target.y - state.graphView.y) * strength,
      width: target.width,
      height: target.height,
    };
  }
  applyGraphView({ scheduleRender: false });
  if (options.force || now - state.graphFollowLastRender > 180) {
    state.graphFollowLastRender = now;
    scheduleGraphViewportRender();
  }
}

function startGraphFollow(nodeId, size = state.focusReturnView || state.graphView, options = {}) {
  if (!nodeId) return;
  state.graphFollowNode = nodeId;
  state.graphFollowViewSize = {
    width: Number(size?.width) || state.graphView.width,
    height: Number(size?.height) || state.graphView.height,
  };
  const point = graphPointForNodeId(nodeId);
  const target = graphViewCenteredOnPoint(point, state.graphFollowViewSize);
  if (!target) return;
  if (options.animate) {
    state.graphFollowPausedUntil = performance.now() + motion.reset + 40;
    animateGraphView(target, motion.reset, {
      onComplete: () => {
        state.graphFollowPausedUntil = 0;
        applyGraphFollow(null, 16, { force: true, immediate: true });
      },
    });
  } else {
    state.graphFollowPausedUntil = 0;
    applyGraphFollow(null, 16, { force: true, immediate: true });
  }
}

function rememberFacetStateForFocus() {
  if (!graphFocusActive() && state.facetStateBeforeFocus === null) {
    state.facetStateBeforeFocus = state.showFacets;
  }
}

function restoreFacetStateAfterFocus() {
  if (state.facetStateBeforeFocus !== null) {
    state.showFacets = state.facetStateBeforeFocus;
    state.facetStateBeforeFocus = null;
  }
  syncFacetToggle();
}

function syncGraphModeButtons() {
  el.graphModeStar?.classList.toggle("active", state.graphMode === "star");
  el.graphModeTree?.classList.toggle("active", state.graphMode === "tree");
}

function setGraphMode(mode, options = {}) {
  if (!options.preserveFollow) {
    clearGraphFollow();
    state.focusReturnView = null;
  }
  const nextMode = mode === "tree" ? "tree" : "star";
  const changed = state.graphMode !== nextMode;
  state.graphMode = nextMode;
  if (changed && !options.preserveView) {
    state.graphViewFitPending = true;
  }
  if (state.focusNode || state.pendingFocusNode) {
    state.focusNode = "";
    state.pendingFocusNode = "";
    restoreFacetStateAfterFocus();
  }
  syncGraphModeButtons();
  if (options.render && (changed || options.forceRender)) {
    renderGraph();
  }
  return changed;
}

function preferTreeForFocus() {
  // Focus rendering uses a compact subgraph tree while preserving the user's free-browse mode.
  syncGraphModeButtons();
}

function selectEntry(entry, options = {}) {
  const entryId = String(entry.id || "");
  const nodeId = entryNodeId(entry);
  clearGraphFollow();
  state.selectedId = entryId;
  state.selectedNode = nodeId;
  if (options.focusNode) {
    rememberFocusReturnView();
    rememberFacetStateForFocus();
    preferTreeForFocus();
    state.focusNode = nodeId;
    state.pendingFocusNode = nodeId;
    syncFacetToggle();
  }
  if (options.reveal && !options.preservePanels) {
    revealPanelsForEntry();
  }
  fillForm(entry, { editing: options.editing === true });
  if (options.reveal) {
    window.requestAnimationFrame(() => {
      if (state.showList) {
        revealEntryInList(entryId);
      }
      if (state.showEditor && !options.preservePanels) {
        revealEditor();
      }
      revealGraphDetail();
    });
  }
}

function newEntry(options = {}) {
  const editing = options.editing !== false;
  const focus = options.focus !== false && editing;
  state.showList = true;
  state.showEditor = true;
  state.currentEntry = null;
  state.activePeerId = "";
  updatePanelVisibility();
  fillForm({
    record_type: "manual_note",
    topic: "",
    phase: "手动修订",
    status: "DRAFT",
    time: "",
    memory_decision: "DEFERRED",
    evidence: "local shiguan web",
  }, { editing });
  if (!focus) return;
  window.requestAnimationFrame(() => {
    revealEditor();
    field("topic")?.focus({ preventScroll: true });
  });
}

function entryBranch(entry) {
  return entry.lineage_key || "unclassified";
}

function lineageLabel(entry) {
  if (entry.lineage_display || entry.ancient_lineage) {
    return entry.lineage_display || entry.ancient_lineage;
  }
  const parts = entry.lineage_parts || {};
  return [parts.zhi, parts.men, parts.gang, parts.mu, parts.tiao].filter(Boolean).join(" · ") || "未分类";
}

function branchLabel(entry) {
  const parts = entry.lineage_parts || {};
  return [parts.zhi, parts.men, parts.gang].filter(Boolean).join(" · ") || lineageLabel(entry);
}

function displayReason(entry) {
  return chineseDisplayFragment(entry.display_reason_zh || entry.memory_reason || entry.next, 120) || "未记录理由";
}

function primaryKeywords(entry) {
  const displayZh = Array.isArray(entry.display_keywords_zh) ? entry.display_keywords_zh : [];
  const zh = Array.isArray(entry.keywords_zh) ? entry.keywords_zh : [];
  const parts = entry.lineage_parts || {};
  const lineage = [parts.zhi, parts.men, parts.gang, parts.mu, parts.tiao, parts.zhao];
  return chineseOnlyList([...displayZh, ...lineage, ...zh].filter(Boolean), 8);
}

function displaySummaryZh(entry) {
  const cleanDisplay = !hasEnglish(entry.display_summary_zh) ? chineseDisplayFragment(entry.display_summary_zh, 180) : "";
  const cleanKeyword = !hasEnglish(entry.keyword_summary_zh) ? chineseDisplayFragment(entry.keyword_summary_zh, 180) : "";
  const rawSource = entry.summary || entry.memory_content || entry.evidence;
  const translated = translateEnglishSummary(rawSource, 140);
  const direct = cleanDisplay
    || cleanKeyword
    || translated
    || chineseDisplayFragment(entry.summary, 140);
  if (direct) return direct;
  const parts = entry.lineage_parts || {};
  const lineage = chineseOnlyList([parts.zhi, parts.men, parts.gang, parts.mu, parts.tiao], 5);
  const clauses = [
    hasEnglish(rawSource) ? "源摘要为英文，原文保留在源字段，可点“显示原文”查看" : "",
    `阶段${chineseDisplayFragment(entry.phase, 24) || "未分期"}，状态${statusLabel(entry.status)}`,
    `内容归类为${lineage.join("、") || "未分类"}`,
    `记忆裁定为${memoryDecisionLabel(entry.memory_decision)}`,
  ].filter(Boolean);
  return truncate(`${clauses.join("；")}。`, 180);
}

function graphRecordId(entry) {
  return `record:${entry.record_uid || entry.kb_uid || entry.id || entry.court_code || entry.topic || entry.time || "unknown"}`;
}

function actionLabel(entry) {
  const summary = displaySummaryZh(entry);
  const compact = summary
    .replace(/^.*?[：:]/, "")
    .replace(/[。；;].*$/, "")
    .trim();
  return truncate(compact || chineseDisplayFragment(entry.phase, 18) || "树叶", 18);
}

function displayTitleZh(entry, max = 24) {
  const direct = chineseDisplayFragment(entry.display_title_zh || entry.topic, max);
  if (direct) return direct;
  const parts = entry.lineage_parts || {};
  const lineage = chineseOnlyList([parts.zhao, parts.tiao, parts.mu, parts.gang, parts.men, parts.zhi], 1)[0];
  if (lineage) return truncate(lineage, max);
  const keyword = primaryKeywords(entry)[0];
  if (keyword) return truncate(keyword, max);
  return truncate(actionLabel(entry) || "史馆树叶", max);
}

function graphTypeLabel(type) {
  return {
    root: "总根",
    peer: "共享机器",
    leaf: "树叶",
    keyword: "关键词",
    lineage: "谱系",
    facet: "分面",
  }[type] || "节点";
}

function graphEntryLimit() {
  const raw = Number(el.graphLimitInput?.value || state.graphLimit || defaultGraphLimit());
  const limit = Math.min(500, Math.max(10, Math.round(raw || defaultGraphLimit())));
  state.graphLimit = limit;
  if (el.graphLimitInput) {
    el.graphLimitInput.value = String(limit);
  }
  return limit;
}

function syncDefaultGraphLimitForViewport() {
  if (state.graphLimitTouched) return false;
  const next = defaultGraphLimit();
  if (next === state.graphLimit) return false;
  state.graphLimit = next;
  if (el.graphLimitInput) {
    el.graphLimitInput.value = String(next);
  }
  return true;
}

function updatePanelVisibility() {
  el.layout.classList.toggle("hide-list", !state.showList);
  el.layout.classList.toggle("hide-editor", !state.showEditor);
  el.toggleListBtn.setAttribute("aria-pressed", String(state.showList));
  el.toggleEditorBtn.setAttribute("aria-pressed", String(state.showEditor));
  updateColorModeControl();
  window.requestAnimationFrame(() => applyGraphView());
}

function scheduleRenderEntries() {
  if (!shouldVirtualizeEntries()) return;
  if (state.entryRenderFrame) {
    cancelAnimationFrame(state.entryRenderFrame);
  }
  state.entryRenderFrame = requestAnimationFrame(() => {
    state.entryRenderFrame = 0;
    renderEntries();
  });
}

function shouldVirtualizeEntries() {
  return state.entries.length > entryFullRenderLimit;
}

function createEntryItem(entry) {
  const item = document.createElement("article");
  item.className = "entry";
  item.classList.toggle("peer-entry", Boolean(entry.peer_id));
  item.tabIndex = 0;
  item.setAttribute("role", "button");
  item.style.setProperty("--class-color", colorModeEnabled() ? classColorForEntry(entry) : "var(--line)");
  item.style.setProperty("--status-color", statusColor(entry.status));
  if (String(entry.id || "") === state.selectedId) {
    item.classList.add("active");
  }

  const title = document.createElement("div");
  title.className = "entry-title";
  title.textContent = `${displayTitleZh(entry)} / ${chineseDisplayFragment(entry.phase, 24) || "未分期"}`;

  const meta = document.createElement("div");
  meta.className = "entry-meta";
  const statusDot = document.createElement("span");
  statusDot.className = "entry-status-dot";
  statusDot.setAttribute("aria-hidden", "true");
  const statusText = document.createElement("span");
  statusText.className = "entry-status-text";
  statusText.textContent = statusLabel(entry.status);
  const metaTail = document.createElement("span");
  metaTail.textContent = [
    entry.peer_machine_name ? `共享：${entry.peer_machine_name}` : "",
    entry.time || "",
    entry.memory_decision ? `记忆：${memoryDecisionLabel(entry.memory_decision)}` : "",
  ]
    .filter(Boolean)
    .join(" · ");
  meta.append(statusDot, statusText, metaTail);

  const code = document.createElement("div");
  code.className = "entry-code";
  code.textContent = entry.court_code || "";

  const summary = document.createElement("div");
  summary.className = "entry-summary";
  summary.textContent = `摘要：${truncate(displaySummaryZh(entry), 140)}`;

  const reason = document.createElement("div");
  reason.className = "entry-summary";
  reason.textContent = `理由：${truncate(displayReason(entry), 120)}`;

  const keywordLine = document.createElement("div");
  keywordLine.className = "entry-summary";
  keywordLine.textContent = `关键词：${primaryKeywords(entry).slice(0, 6).join("，") || "无"}`;

  const tags = document.createElement("div");
  tags.className = "entry-tags";
  for (const keyword of primaryKeywords(entry).slice(0, 4)) {
    const tag = document.createElement("span");
    tag.className = "tag";
    tag.textContent = keyword;
    tags.append(tag);
  }

  item.append(title, meta, code, keywordLine, summary, reason, tags);
  item.dataset.entryId = String(entry.id || "");
  item.setAttribute("aria-label", title.textContent || "史馆记录");
  item.addEventListener("click", () => selectEntry(entry, { focusNode: true, reveal: true }));
  item.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      selectEntry(entry, { focusNode: true, reveal: true });
    }
  });
  return item;
}

function restoreEntryScroll(previousScrollTop) {
  const maxScrollTop = Math.max(0, el.entries.scrollHeight - el.entries.clientHeight);
  el.entries.scrollTop = Math.min(previousScrollTop, maxScrollTop);
}

function renderEntries() {
  const previousScrollTop = el.entries.scrollTop;
  const fragment = document.createDocumentFragment();
  el.entries.replaceChildren();
  if (!state.entries.length) {
    const empty = document.createElement("div");
    empty.className = "entry-summary";
    empty.textContent = "暂无匹配记录";
    el.entries.append(empty);
    return;
  }

  if (!shouldVirtualizeEntries()) {
    for (const entry of state.entries) {
      fragment.append(createEntryItem(entry));
    }
    el.entries.append(fragment);
    restoreEntryScroll(previousScrollTop);
    return;
  }

  const viewportHeight = el.entries.clientHeight || 520;
  const startIndex = Math.max(0, Math.floor(previousScrollTop / entryVirtualRowHeight) - entryVirtualOverscan);
  const visibleCount = Math.ceil(viewportHeight / entryVirtualRowHeight) + entryVirtualOverscan * 2;
  const endIndex = Math.min(state.entries.length, startIndex + visibleCount);
  const topSpacer = document.createElement("div");
  topSpacer.className = "entry-spacer";
  topSpacer.style.height = `${startIndex * entryVirtualRowHeight}px`;
  fragment.append(topSpacer);

  for (const entry of state.entries.slice(startIndex, endIndex)) {
    fragment.append(createEntryItem(entry));
  }

  const bottomSpacer = document.createElement("div");
  bottomSpacer.className = "entry-spacer";
  bottomSpacer.style.height = `${Math.max(0, state.entries.length - endIndex) * entryVirtualRowHeight}px`;
  fragment.append(bottomSpacer);
  el.entries.append(fragment);
  restoreEntryScroll(previousScrollTop);
}

el.entries?.addEventListener("scroll", () => {
  if (shouldVirtualizeEntries()) {
    scheduleRenderEntries();
  }
}, { passive: true });

function buildGraph() {
  const nodes = [{ id: "root", label: "史馆总纪", type: "root", count: state.entries.length, lineageIndex: -1 }];
  const edges = [];
  const edgeSet = new Set();
  const includeFacets = graphFacetsVisible();
  const lineageMap = new Map();
  const keywordCounts = new Map();
  const facetCounts = new Map();
  const leafEntryMap = new Map();
  const addGraphEdge = (from, to, type) => {
    if (!from || !to) return;
    const key = `${from}->${to}:${type}`;
    if (edgeSet.has(key)) return;
    edgeSet.add(key);
    edges.push({ from, to, type });
  };

  for (const peer of state.peers) {
    const nodeId = peerNodeId(peer);
    nodes.push({
      id: nodeId,
      label: peerMachineName(peer),
      type: "peer",
      peer,
      count: Number(peer.count || peer.shown || 0),
      expanded: peerExpanded(peer),
      status: peer.status || "collapsed",
    });
    addGraphEdge("root", nodeId, "peer");
  }

  for (const entry of state.entries) {
    const peerId = String(entry.peer_id || "");
    let parentId = "root";
    for (const item of lineageItemsForEntry(entry)) {
      const current = lineageMap.get(item.id);
      if (current) {
        current.count += 1;
        current.entries.push(entry);
      } else {
        lineageMap.set(item.id, { ...item, count: 1, entries: [entry] });
        nodes.push(lineageMap.get(item.id));
        addGraphEdge(parentId, item.id, "lineage");
      }
      parentId = item.id;
    }

    const leafId = entryNodeId(entry);
    leafEntryMap.set(leafId, entry);
    nodes.push({
      id: leafId,
      label: actionLabel(entry),
      type: "leaf",
      branch: entryBranch(entry),
      parentLineageId: parentId,
      entry,
      count: 1,
    });
    addGraphEdge(parentId, leafId, "leaf");
    if (peerId) {
      addGraphEdge(peerNodeIdForId(peerId), leafId, "peer");
    }

    for (const keyword of primaryKeywords(entry).slice(0, 3)) {
      const key = keyword.toLowerCase();
      const current = keywordCounts.get(key) || { label: keyword, count: 0, entries: [] };
      current.count += 1;
      current.entries.push(entry);
      keywordCounts.set(key, current);
    }

    if (includeFacets) {
      for (const facet of facetItemsForEntry(entry)) {
        const current = facetCounts.get(facet.id) || { ...facet, count: 0, entries: [] };
        current.count += 1;
        current.entries.push(entry);
        facetCounts.set(facet.id, current);
      }
    }
  }

  const topKeywords = [...keywordCounts.entries()]
    .sort((a, b) => b[1].count - a[1].count)
    .slice(0, 16);
  for (const [key, item] of topKeywords) {
    const nodeId = `keyword:${key}`;
    nodes.push({
      id: nodeId,
      label: item.label,
      type: "keyword",
      count: item.count,
      entries: item.entries,
      classKey: dominantEntryClassKey(item.entries),
    });
    for (const entry of item.entries.slice(0, 8)) {
      addGraphEdge(entryNodeId(entry), nodeId, "keyword");
    }
  }

  if (includeFacets) {
    const topFacets = [...facetCounts.values()]
      .sort((a, b) => b.count - a.count)
      .slice(0, 18);
    for (const item of topFacets) {
      nodes.push({
        id: item.id,
        label: item.label,
        type: "facet",
        facetDimension: item.dimension,
        count: item.count,
        entries: item.entries,
        classKey: dominantEntryClassKey(item.entries),
      });
      for (const entry of item.entries.slice(0, 8)) {
        addGraphEdge(entryNodeId(entry), item.id, "facet");
      }
    }
  }

  return { nodes, edges };
}

function graphIdPart(value) {
  return String(value || "")
    .trim()
    .replace(/[^\w\u4e00-\u9fff-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 72) || "unclassified";
}

function lineageItemsForEntry(entry = {}) {
  const parts = entry.lineage_parts || {};
  const fallback = String(entry.lineage_key || "").split(/[\/>·]/).map((item) => item.trim()).filter(Boolean);
  const labels = [
    ["志", parts.zhi || fallback[0]],
    ["门", parts.men || fallback[1]],
    ["纲", parts.gang || fallback[2]],
    ["目", parts.mu || fallback[3]],
    ["条", parts.tiao || fallback[4]],
    ["诏", parts.zhao || displayTitleZh(entry, 18)],
  ].filter(([, label]) => label);
  const path = [];
  return labels.map(([level, label], index) => ({
    id: `lineage:${index}:${path.push(graphIdPart(label)) && path.join("/")}`,
    level,
    label: `${level}:${label}`,
    rawLabel: label,
    type: "lineage",
    lineageIndex: index,
    classKey: entryBranch(entry),
    entries: [entry],
  }));
}

function facetItemsForEntry(entry = {}) {
  const facets = entry.facet_dimensions || {};
  const output = [];
  for (const [dimension, rawValues] of Object.entries(facets)) {
    if (dimension === "内容谱系") continue;
    const values = Array.isArray(rawValues) ? rawValues : [rawValues];
    for (const value of values.filter(Boolean).slice(0, 4)) {
      const label = `${String(dimension).replace(/分面$/, "")}:${value}`;
      output.push({
        id: `facet:${graphIdPart(dimension)}:${graphIdPart(value)}`,
        label,
        dimension,
        type: "facet",
        classKey: entryBranch(entry),
        entries: [entry],
      });
    }
  }
  return output;
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function graphLabelWidth(node) {
  return Math.min(String(node.label || node.id || "").length, 14) * 7 + 18;
}

function nodeFootprint(node) {
  const radius = nodeRadius(node);
  const shapeWidth = isRectGraphNode(node) ? radius * 3.6 : radius * 2;
  return Math.max(shapeWidth, graphLabelWidth(node), node.type === "root" ? 92 : 46);
}

function isRectGraphNode(node = {}) {
  return node.type === "facet";
}

function nodeConnectedToSelection(nodeId, edges) {
  if (!state.selectedNode) return false;
  return edges.some((edge) => (
    (edge.from === state.selectedNode && edge.to === nodeId) ||
    (edge.to === state.selectedNode && edge.from === nodeId)
  ));
}

function graphContextNodeId() {
  return state.focusNode || state.selectedNode || "";
}

function relatedNodeIds(edges, nodeId = graphContextNodeId()) {
  const related = new Set();
  if (!nodeId) return related;
  const selected = state.graphNodesById?.get(nodeId);
  if (selected?.type === "lineage") {
    return lineageFocusNodeIds(nodeId, edges);
  }
  for (const edge of edges) {
    if (edge.from === nodeId) {
      related.add(edge.to);
    }
    if (edge.to === nodeId) {
      related.add(edge.from);
    }
  }
  return related;
}

function selectedGraphNode() {
  return state.selectedNode ? state.graphNodesById?.get(state.selectedNode) : null;
}

function lineageFocusNodeIds(selectedId, edges) {
  const related = new Set();
  const positions = state.graphNodesById || new Map();
  const lineageIds = new Set([selectedId]);

  const addLineage = (id) => {
    if (!id || lineageIds.has(id)) return false;
    const node = positions.get(id);
    if (node?.type !== "lineage" && node?.type !== "root") return false;
    lineageIds.add(id);
    return true;
  };

  const upQueue = [selectedId];
  while (upQueue.length) {
    const current = upQueue.shift();
    for (const edge of edges) {
      if (edge.type !== "lineage" || edge.to !== current) continue;
      if (addLineage(edge.from)) upQueue.push(edge.from);
    }
  }

  const downQueue = [selectedId];
  while (downQueue.length) {
    const current = downQueue.shift();
    for (const edge of edges) {
      if (edge.type !== "lineage" || edge.from !== current) continue;
      if (addLineage(edge.to)) downQueue.push(edge.to);
    }
  }

  for (const id of lineageIds) {
    if (id !== selectedId) related.add(id);
  }
  for (const edge of edges) {
    if (edge.type === "leaf" && lineageIds.has(edge.from)) {
      related.add(edge.to);
    }
  }
  return related;
}

function addLineageAncestors(focusIds, lineageId, edges, positions) {
  const queue = [lineageId];
  while (queue.length) {
    const current = queue.shift();
    if (!positions.has(current)) continue;
    focusIds.add(current);
    for (const edge of edges) {
      if (edge.type !== "lineage" || edge.to !== current) continue;
      const parent = positions.get(edge.from);
      if (!parent || (parent.type !== "lineage" && parent.type !== "root")) continue;
      if (!focusIds.has(edge.from)) {
        focusIds.add(edge.from);
        queue.push(edge.from);
      }
    }
  }
}

function focusedSubgraphNodeIds(positions, edges, related) {
  if (!state.focusNode || !positions.has(state.focusNode)) return null;
  const focusIds = new Set([state.focusNode]);
  for (const id of related) {
    if (positions.has(id)) {
      focusIds.add(id);
    }
  }

  for (const id of [...focusIds]) {
    const node = positions.get(id);
    if (node?.type === "leaf" && node.parentLineageId) {
      addLineageAncestors(focusIds, node.parentLineageId, edges, positions);
    }
    if (node?.type === "lineage") {
      addLineageAncestors(focusIds, id, edges, positions);
    }
  }

  return focusIds;
}

function focusSortValue(node) {
  const rank = {
    root: 0,
    lineage: 1,
    leaf: 2,
    keyword: 3,
    facet: 4,
    peer: 5,
  }[node?.type] ?? 9;
  const lineage = Number.isFinite(Number(node?.lineageIndex)) ? Number(node.lineageIndex) : 99;
  return `${rank}:${String(lineage).padStart(2, "0")}:${String(node?.parentLineageId || "")}:${String(node?.label || node?.id || "")}`;
}

function focusColumnRank(node, maxLineageIndex) {
  if (node.type === "root") return 0;
  if (node.type === "lineage") return Number(node.lineageIndex || 0) + 1;
  const leafRank = Math.max(1, maxLineageIndex + 2);
  if (node.type === "leaf") return leafRank;
  if (node.type === "keyword") return leafRank + 1;
  if (node.type === "facet") return leafRank + 2;
  if (node.type === "peer") return leafRank + 3;
  return leafRank + 4;
}

function separateFocusColumn(items, minGap, top, height) {
  items.sort((a, b) => a.y - b.y || focusSortValue(a).localeCompare(focusSortValue(b), "zh-Hans-CN"));
  for (let index = 1; index < items.length; index += 1) {
    if (items[index].y < items[index - 1].y + minGap) {
      items[index].y = items[index - 1].y + minGap;
    }
  }
  const bottom = top + height;
  const overflow = items.length ? items[items.length - 1].y - bottom : 0;
  if (overflow > 0) {
    for (const item of items) {
      item.y -= overflow / 2;
    }
  }
  if (items.length && items[0].y < top) {
    const lift = top - items[0].y;
    for (const item of items) {
      item.y += lift;
    }
  }
}

function applyFocusedTreeLayout(positions, edges, focusIds) {
  if (!focusIds || focusIds.size <= 1) return null;
  const focusNodes = [...focusIds].map((id) => positions.get(id)).filter(Boolean);
  const maxLineageIndex = Math.max(
    -1,
    ...focusNodes
      .filter((node) => node.type === "lineage")
      .map((node) => Number(node.lineageIndex || 0)),
  );
  const columnSpacing = 164;
  const rowSpacing = 82;
  const top = 92;
  const left = 96;
  const columns = new Map();

  for (const node of focusNodes) {
    const rank = focusColumnRank(node, maxLineageIndex);
    const items = columns.get(rank) || [];
    items.push(node);
    columns.set(rank, items);
  }

  const maxColumnCount = Math.max(...[...columns.values()].map((items) => items.length), 1);
  const maxRank = Math.max(...columns.keys(), 0);
  const height = Math.max(420, top * 2 + Math.max(1, maxColumnCount - 1) * rowSpacing);
  const width = Math.max(760, left * 2 + maxRank * columnSpacing + 140);

  for (const [rank, items] of columns.entries()) {
    items.sort((a, b) => focusSortValue(a).localeCompare(focusSortValue(b), "zh-Hans-CN"));
    const yOffset = (height - top * 2 - Math.max(0, items.length - 1) * rowSpacing) / 2;
    items.forEach((node, index) => {
      node.x = left + rank * columnSpacing;
      node.y = top + Math.max(0, yOffset) + index * rowSpacing;
    });
  }

  for (let round = 0; round < 3; round += 1) {
    const ranked = [...focusNodes]
      .filter((node) => node.type === "root" || node.type === "lineage")
      .sort((a, b) => focusColumnRank(b, maxLineageIndex) - focusColumnRank(a, maxLineageIndex));
    for (const node of ranked) {
      const childNodes = edges
        .filter((edge) => focusIds.has(edge.from) && focusIds.has(edge.to) && edge.from === node.id)
        .map((edge) => positions.get(edge.to))
        .filter(Boolean);
      if (!childNodes.length) continue;
      node.y = childNodes.reduce((sum, child) => sum + child.y, 0) / childNodes.length;
    }
    for (const items of columns.values()) {
      separateFocusColumn(items, rowSpacing * 0.82, top * 0.65, height - top * 1.3);
    }
  }

  return { x: 0, y: 0, width, height };
}

function edgeActiveForSelection(edge, related = null) {
  const activeIds = [state.selectedNode, state.focusNode].filter(Boolean);
  if (!activeIds.length) return false;
  if (activeIds.some((id) => edge.from === id || edge.to === id)) return true;
  return Boolean(related?.has(edge.from) && related?.has(edge.to));
}

function focusGraphNode(node, zoom = 0.42) {
  if (!node) return;
  const width = Math.max(220, state.graphBounds.width * zoom);
  const height = Math.max(160, state.graphBounds.height * zoom);
  animateGraphView({
    x: node.x - width / 2,
    y: node.y - height / 2,
    width,
    height,
  }, motion.focus);
}

function focusGraphCluster(nodeId, positions, edges) {
  const node = positions.get(nodeId);
  if (!node) return;
  const related = relatedNodeIds(edges, nodeId);
  const focusIds = state.graphSnapshot?.focusIds;
  const items = focusIds?.size
    ? [...focusIds].map((id) => positions.get(id)).filter(Boolean)
    : [node, ...[...related].map((id) => positions.get(id)).filter(Boolean)];
  if (!items.length) return;
  const minX = Math.min(...items.map((item) => item.x));
  const maxX = Math.max(...items.map((item) => item.x));
  const minY = Math.min(...items.map((item) => item.y));
  const maxY = Math.max(...items.map((item) => item.y));
  const rect = el.graph?.getBoundingClientRect?.();
  const aspect = rect?.width && rect?.height ? rect.width / rect.height : state.graphBounds.width / state.graphBounds.height;
  const padding = touchOptimizedMode() ? 96 : 128;
  let width = Math.max(360, maxX - minX + padding * 2);
  let height = Math.max(240, maxY - minY + padding * 2);
  if (width / height > aspect) {
    height = width / aspect;
  } else {
    width = height * aspect;
  }
  width = Math.min(state.graphBounds.width, width);
  height = Math.min(state.graphBounds.height, height);
  animateGraphView({
    x: (minX + maxX) / 2 - width / 2,
    y: (minY + maxY) / 2 - height / 2,
    width,
    height,
  }, motion.focus);
}

function clampGraphView(view) {
  const maxWidth = state.graphBounds.width * 1.8;
  const maxHeight = state.graphBounds.height * 1.8;
  const width = clamp(view.width, 220, maxWidth);
  const height = clamp(view.height, 140, maxHeight);
  return {
    x: clamp(view.x, state.graphBounds.x - state.graphBounds.width * 0.4, state.graphBounds.x + state.graphBounds.width * 0.4),
    y: clamp(view.y, state.graphBounds.y - state.graphBounds.height * 0.4, state.graphBounds.y + state.graphBounds.height * 0.4),
    width,
    height,
  };
}

function localUnfocusView(view = state.graphView) {
  const width = Math.min(state.graphBounds.width * 0.82, Math.max(320, view.width * 1.18));
  const height = Math.min(state.graphBounds.height * 0.82, Math.max(240, view.height * 1.18));
  return clampGraphView({
    x: view.x + view.width / 2 - width / 2,
    y: view.y + view.height / 2 - height / 2,
    width,
    height,
  });
}

function clearGraphFocus() {
  if (!state.focusNode && !state.pendingFocusNode) return;
  const followNode = state.focusNode || state.pendingFocusNode || state.selectedNode;
  const followSize = state.focusReturnView || {
    width: state.graphView.width,
    height: state.graphView.height,
  };
  state.focusNode = "";
  state.pendingFocusNode = "";
  restoreFacetStateAfterFocus();
  hideNodeTooltip();
  renderEntries();
  renderGraph();
  startGraphFollow(followNode, followSize, { animate: true });
  state.focusReturnView = null;
}

function setGraphBounds(bounds) {
  const oldBounds = state.graphBounds;
  if (state.graphViewFitPending) {
    state.graphBounds = bounds;
    state.graphView = { ...bounds };
    state.graphViewFitPending = false;
    return;
  }
  const viewWasAtBounds = (
    Math.abs(state.graphView.x - oldBounds.x) < 1 &&
    Math.abs(state.graphView.y - oldBounds.y) < 1 &&
    Math.abs(state.graphView.width - oldBounds.width) < 1 &&
    Math.abs(state.graphView.height - oldBounds.height) < 1
  );
  state.graphBounds = bounds;
  if (viewWasAtBounds) {
    state.graphView = { ...bounds };
    return;
  }
  const maxWidth = bounds.width * 1.8;
  const maxHeight = bounds.height * 1.8;
  state.graphView = {
    x: clamp(state.graphView.x, bounds.x - bounds.width * 0.4, bounds.x + bounds.width * 0.4),
    y: clamp(state.graphView.y, bounds.y - bounds.height * 0.4, bounds.y + bounds.height * 0.4),
    width: clamp(state.graphView.width, 220, maxWidth),
    height: clamp(state.graphView.height, 140, maxHeight),
  };
}

function relaxCollisions(positioned, bounds, iterations = 30) {
  const items = [...positioned.values()];
  for (let round = 0; round < iterations; round += 1) {
    let moved = false;
    for (let i = 0; i < items.length; i += 1) {
      const a = items[i];
      for (let j = i + 1; j < items.length; j += 1) {
        const b = items[j];
        const minGap = (nodeFootprint(a) + nodeFootprint(b)) / 2 + 14;
        let dx = b.x - a.x;
        let dy = b.y - a.y;
        let distance = Math.hypot(dx, dy);
        if (distance >= minGap) {
          continue;
        }
        if (distance < 0.01) {
          const angle = ((i + 1) * 37 + (j + 1) * 19) * Math.PI / 180;
          dx = Math.cos(angle);
          dy = Math.sin(angle);
          distance = 1;
        }
        const push = (minGap - distance) / 2;
        const ux = dx / distance;
        const uy = dy / distance;
        if (a.type !== "root") {
          a.x -= ux * push;
          a.y -= uy * push;
        }
        if (b.type !== "root") {
          b.x += ux * push;
          b.y += uy * push;
        }
        moved = true;
      }
    }
    for (const item of items) {
      if (item.type === "root") {
        continue;
      }
      const margin = nodeFootprint(item) / 2 + 26;
      item.x = clamp(item.x, bounds.x + margin, bounds.x + bounds.width - margin);
      item.y = clamp(item.y, bounds.y + margin, bounds.y + bounds.height - margin);
    }
    if (!moved) {
      break;
    }
  }
  return positioned;
}

function topLineageKeyFromId(id = "") {
  const path = String(id).replace(/^lineage:\d+:/, "");
  return lineagePathPartsFromKey(path)[0] || path.split("/")[0] || "未分谱系";
}

function starArmKey(node = {}) {
  if (node.type === "peer") return `peer:${peerMachineName(node.peer) || node.id}`;
  if (node.type === "lineage") return topLineageKeyFromId(node.id);
  if (node.type === "leaf") return chainColorKeyForEntry(node.entry || {});
  if (node.type === "keyword" || node.type === "facet") {
    return node.classKey || dominantEntryClassKey(node.entries || []) || node.label || node.id;
  }
  return node.branch || node.classKey || node.id || "未分谱系";
}

function starNodeSortValue(node = {}) {
  const rank = {
    peer: 0,
    lineage: 1,
    leaf: 8,
    keyword: 10,
    facet: 11,
  }[node.type] ?? 9;
  const lineage = Number.isFinite(Number(node.lineageIndex)) ? Number(node.lineageIndex) : 99;
  return `${rank}:${String(lineage).padStart(2, "0")}:${String(node.parentLineageId || "")}:${String(node.label || node.id || "")}`;
}

function starLayout(nodes) {
  const side = Math.ceil(Math.sqrt(Math.max(nodes.length, 1))) * 205;
  const width = Math.max(defaultGraphBounds.width, side);
  const height = Math.max(defaultGraphBounds.height, Math.round(side * 0.74));
  const bounds = { x: 0, y: 0, width, height };
  const center = { x: width / 2, y: height / 2 };
  const peers = nodes.filter((node) => node.type === "peer");
  const leaves = nodes.filter((node) => node.type === "leaf");
  const keywords = nodes.filter((node) => node.type === "keyword");
  const facets = nodes.filter((node) => node.type === "facet");
  const lineages = nodes.filter((node) => node.type === "lineage");
  const leavesByLineage = new Map();
  const lineagesByArm = new Map();
  const leavesByArm = new Map();
  const keywordsByArm = new Map();
  const facetsByArm = new Map();
  const peersByArm = new Map();

  const positioned = new Map();
  positioned.set("root", { ...nodes.find((node) => node.id === "root"), ...center });

  const pushArm = (map, node) => {
    const key = starArmKey(node);
    const items = map.get(key) || [];
    items.push(node);
    map.set(key, items);
    return key;
  };

  for (const node of lineages) {
    pushArm(lineagesByArm, node);
  }

  for (const leaf of leaves) {
    const list = leavesByLineage.get(leaf.parentLineageId) || [];
    list.push(leaf);
    leavesByLineage.set(leaf.parentLineageId, list);
    pushArm(leavesByArm, leaf);
  }

  for (const node of keywords) pushArm(keywordsByArm, node);
  for (const node of facets) pushArm(facetsByArm, node);
  for (const node of peers) pushArm(peersByArm, node);

  const armKeys = [...new Set([
    ...lineagesByArm.keys(),
    ...leavesByArm.keys(),
    ...keywordsByArm.keys(),
    ...facetsByArm.keys(),
    ...peersByArm.keys(),
  ])].sort((a, b) => String(a).localeCompare(String(b), "zh-Hans-CN"));
  const armCount = Math.max(armKeys.length, 1);
  const armAngles = new Map();
  armKeys.forEach((key, index) => {
    const stagger = (index % 2 ? 0.08 : -0.04);
    armAngles.set(key, -Math.PI / 2 + (Math.PI * 2 * index) / armCount + stagger);
  });
  const ellipse = 0.78;

  for (const [key, items] of lineagesByArm.entries()) {
    const baseAngle = armAngles.get(key) ?? 0;
    const sorted = items.sort((a, b) => starNodeSortValue(a).localeCompare(starNodeSortValue(b), "zh-Hans-CN"));
    const levelCounts = new Map();
    for (const node of sorted) {
      const level = Number(node.lineageIndex || 0);
      const sameLevelIndex = levelCounts.get(level) || 0;
      levelCounts.set(level, sameLevelIndex + 1);
      const radius = 118 + (level + 1) * 82 + sameLevelIndex * 24;
      const angle = baseAngle + (level + 1) * 0.38 + sameLevelIndex * 0.07;
      positioned.set(node.id, {
        ...node,
        x: center.x + Math.cos(angle) * radius,
        y: center.y + Math.sin(angle) * radius * ellipse,
        radiusFromCenter: radius,
        angle,
      });
    }
  }

  for (const [key, items] of peersByArm.entries()) {
    const baseAngle = armAngles.get(key) ?? Math.PI;
    items.sort((a, b) => starNodeSortValue(a).localeCompare(starNodeSortValue(b), "zh-Hans-CN"))
      .forEach((node, index) => {
        const radius = 140 + index * 74;
        const angle = baseAngle - 0.22 + index * 0.16;
        positioned.set(node.id, {
          ...node,
          x: center.x + Math.cos(angle) * radius,
          y: center.y + Math.sin(angle) * radius * ellipse,
          radiusFromCenter: radius,
          angle,
        });
      });
  }

  leaves.forEach((leaf, index) => {
    const parent = positioned.get(leaf.parentLineageId);
    const siblingCount = leavesByLineage.get(leaf.parentLineageId)?.length || leaves.length || 1;
    const siblingIndex = (leavesByLineage.get(leaf.parentLineageId) || []).findIndex((item) => item.id === leaf.id);
    const armAngle = armAngles.get(starArmKey(leaf)) ?? (-Math.PI / 2 + (Math.PI * 2 * index) / Math.max(leaves.length, 1));
    const baseAngle = parent?.angle ?? armAngle + 2.35;
    const spread = Math.min(0.72, Math.max(0.18, siblingCount * 0.065));
    const localIndex = siblingIndex < 0 ? index : siblingIndex;
    const leafAngle = baseAngle + 0.28 + (localIndex - (siblingCount - 1) / 2) * (spread / Math.max(siblingCount, 1));
    const leafRadius = parent
      ? 94 + Math.floor(Math.max(localIndex, 0) / 7) * 54 + (localIndex % 7) * 4
      : Math.min(width, height) * 0.45;
    positioned.set(leaf.id, {
      ...leaf,
      x: (parent?.x ?? center.x) + Math.cos(leafAngle) * leafRadius,
      y: (parent?.y ?? center.y) + Math.sin(leafAngle) * leafRadius * ellipse,
      angle: leafAngle,
    });
  });

  const placeOuterNodes = (map, baseLayer, nodeType) => {
    for (const [key, items] of map.entries()) {
      const baseAngle = armAngles.get(key) ?? 0;
      items.sort((a, b) => starNodeSortValue(a).localeCompare(starNodeSortValue(b), "zh-Hans-CN"))
        .forEach((node, index) => {
          const radius = Math.min(width, height) * baseLayer + Math.floor(index / 4) * 46 + (index % 4) * 12;
          const angle = baseAngle + 2.55 + index * 0.09 + (nodeType === "facet" ? 0.18 : 0);
          positioned.set(node.id, {
            ...node,
            x: center.x + Math.cos(angle) * radius,
            y: center.y + Math.sin(angle) * radius * ellipse,
            radiusFromCenter: radius,
            angle,
          });
        });
    }
  };

  placeOuterNodes(keywordsByArm, 0.42, "keyword");
  placeOuterNodes(facetsByArm, 0.52, "facet");

  return { positions: relaxCollisions(positioned, bounds, touchOptimizedMode() ? 16 : 24), bounds, center };
}

function treeLayout(nodes) {
  const positioned = new Map();
  const byType = {
    root: nodes.filter((node) => node.type === "root"),
    peer: nodes.filter((node) => node.type === "peer"),
    leaf: nodes.filter((node) => node.type === "leaf"),
    keyword: nodes.filter((node) => node.type === "keyword"),
    lineage: nodes.filter((node) => node.type === "lineage"),
    facet: nodes.filter((node) => node.type === "facet"),
  };
  const columns = [
    ["root", 126],
    ["lineage:0", 276],
    ["lineage:1", 426],
    ["lineage:2", 576],
    ["lineage:3", 726],
    ["lineage:4", 876],
    ["lineage:5", 1026],
    ["leaf", 1206],
    ["keyword", 1416],
    ["facet", 1616],
    ["peer", 1796],
  ];
  const lineageColumns = new Map();
  for (const node of byType.lineage) {
    const key = `lineage:${Number(node.lineageIndex || 0)}`;
    const items = lineageColumns.get(key) || [];
    items.push(node);
    lineageColumns.set(key, items);
  }
  const columnItems = new Map([
    ["root", byType.root],
    ["leaf", byType.leaf],
    ["keyword", byType.keyword],
    ["facet", byType.facet],
    ["peer", byType.peer],
  ]);
  for (const [key, items] of lineageColumns.entries()) {
    columnItems.set(key, items.sort((a, b) => String(a.label).localeCompare(String(b.label), "zh-Hans-CN")));
  }
  const maxColumnCount = Math.max(...[...columnItems.values()].map((items) => items.length), 1);
  const height = Math.max(defaultGraphBounds.height, 120 + maxColumnCount * graphSpacing.treeY);
  const bounds = { x: 0, y: 0, width: Math.max(defaultGraphBounds.width, 1940), height };
  for (const [type, x] of columns) {
    const items = columnItems.get(type) || [];
    items.forEach((node, index) => {
      const y = 70 + index * graphSpacing.treeY;
      positioned.set(node.id, { ...node, x, y });
    });
  }
  return { positions: positioned, bounds };
}

function nodeColor(type) {
  return {
    root: "#2f6f5e",
    peer: "#168aa3",
    leaf: "#6f7a6a",
    keyword: "#9a4638",
    lineage: "#5b527d",
    facet: "#8f6b2f",
  }[type] || "#66706a";
}

function nodeFillColor(node = {}) {
  if (!colorModeEnabled() || node.type === "root") {
    return nodeColor(node.type);
  }
  return classColorForNode(node);
}

function nodeRadius(node) {
  const countBoost = Math.min(Math.sqrt(Math.max(0, Number(node.count || 0))) * 0.75, 4);
  if (node.type === "root") return 34;
  if (node.type === "peer") return 24 + (peerExpanded(node.peer) ? 3 : 0);
  if (node.type === "lineage") {
    const lineageLevel = clamp(Number(node.lineageIndex ?? 4), 0, 6);
    return Math.max(16, 28 - lineageLevel * 2.2 + Math.min(countBoost, 2.5));
  }
  if (node.type === "leaf") {
    const parent = state.graphSnapshot?.positions?.get(node.parentLineageId);
    const parentLevel = parent?.type === "lineage" ? clamp(Number(parent.lineageIndex || 0), 0, 6) : 5;
    return Math.max(11.5, 16 - parentLevel * 0.55 + Math.min(countBoost, 1.4));
  }
  if (node.type === "keyword") return 13.5 + Math.min(countBoost, 2.2);
  if (node.type === "facet") return 12 + Math.min(countBoost, 3.5);
  return 12;
}

function svgEl(name, attrs = {}) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", name);
  for (const [key, value] of Object.entries(attrs)) {
    node.setAttribute(key, value);
  }
  return node;
}

function renderEntryProfile(entry = {}) {
  if (!el.profileRadar) return;
  const classColor = colorModeEnabled() ? classColorForEntry(entry) : "#d8d1c4";
  const stage = phaseStage(entry);
  const status = String(entry.status || "UNKNOWN").trim().toUpperCase();
  document.documentElement.style.setProperty("--class-color", classColor);
  if (el.profile) {
    el.profile.style.setProperty("--class-color", classColor);
    el.profile.style.setProperty("--status-color", statusColor(status));
  }
  if (el.profileStage) {
    el.profileStage.textContent = `朝程阶段：${stage.label}`;
  }
  if (el.profileStatus) {
    el.profileStatus.textContent = `状态：${statusLabel(status)}`;
    el.profileStatus.style.setProperty("--status-color", statusColor(status));
  }
  if (el.profileClass) {
    el.profileClass.textContent = `分类：${lineageLabel(entry)}`;
  }

  const metrics = entryRadarMetrics(entry);
  const center = { x: 130, y: 92 };
  const radius = 58;
  const nextPoints = [];
  el.profileRadar.replaceChildren();
  const contentGroup = svgEl("g", { class: "radar-content" });
  el.profileRadar.append(contentGroup);
  for (const scale of [0.33, 0.66, 1]) {
    const points = metrics.map((_, index) => {
      const angle = -Math.PI / 2 + (Math.PI * 2 * index) / metrics.length;
      return `${(center.x + Math.cos(angle) * radius * scale).toFixed(1)},${(center.y + Math.sin(angle) * radius * scale).toFixed(1)}`;
    }).join(" ");
    contentGroup.append(svgEl("polygon", { points, class: "radar-grid" }));
  }
  const valuePoints = metrics.map((metric, index) => {
    const angle = -Math.PI / 2 + (Math.PI * 2 * index) / metrics.length;
    const valueRadius = radius * clamp(metric.value, 1, 7) / 7;
    const endX = center.x + Math.cos(angle) * radius;
    const endY = center.y + Math.sin(angle) * radius;
    const pointX = center.x + Math.cos(angle) * valueRadius;
    const pointY = center.y + Math.sin(angle) * valueRadius;
    nextPoints.push({ x: pointX, y: pointY });
    contentGroup.append(svgEl("line", { x1: center.x, y1: center.y, x2: endX, y2: endY, class: "radar-axis" }));
    const label = svgEl("text", {
      x: center.x + Math.cos(angle) * (radius + 28),
      y: center.y + Math.sin(angle) * (radius + 22) + 3,
      "text-anchor": Math.abs(Math.cos(angle)) < 0.2 ? "middle" : (Math.cos(angle) > 0 ? "start" : "end"),
      class: "radar-label",
    });
    label.textContent = `${metric.label}:${metric.detail}`;
    contentGroup.append(label);
    return `${pointX.toFixed(1)},${pointY.toFixed(1)}`;
  }).join(" ");
  const previousPoints = state.previousRadarPoints.length === nextPoints.length
    ? state.previousRadarPoints
    : nextPoints.map(() => ({ ...center }));
  const previousValuePoints = previousPoints.map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(" ");
  const shape = svgEl("polygon", { points: valuePoints, class: "radar-shape" });
  if (!lowMotionMode() && previousValuePoints !== valuePoints) {
    shape.append(svgEl("animate", {
      attributeName: "points",
      from: previousValuePoints,
      to: valuePoints,
      dur: `${motion.focus}ms`,
      fill: "freeze",
      calcMode: "spline",
      keyTimes: "0;1",
      keySplines: "0.2 0 0 1",
    }));
  }
  contentGroup.append(shape);
  nextPoints.forEach((point, index) => {
    const previous = previousPoints[index] || center;
    const circle = svgEl("circle", { cx: point.x.toFixed(1), cy: point.y.toFixed(1), r: 3.5, class: "radar-point" });
    if (!lowMotionMode()) {
      circle.append(svgEl("animate", {
        attributeName: "cx",
        from: previous.x.toFixed(1),
        to: point.x.toFixed(1),
        dur: `${motion.focus}ms`,
        fill: "freeze",
        calcMode: "spline",
        keyTimes: "0;1",
        keySplines: "0.2 0 0 1",
      }));
      circle.append(svgEl("animate", {
        attributeName: "cy",
        from: previous.y.toFixed(1),
        to: point.y.toFixed(1),
        dur: `${motion.focus}ms`,
        fill: "freeze",
        calcMode: "spline",
        keyTimes: "0;1",
        keySplines: "0.2 0 0 1",
      }));
    }
    contentGroup.append(circle);
  });
  if (!lowMotionMode()) {
    contentGroup.append(svgEl("animate", {
      attributeName: "opacity",
      from: "0.72",
      to: "1",
      dur: `${motion.state}ms`,
      fill: "freeze",
      calcMode: "spline",
      keyTimes: "0;1",
      keySplines: "0.2 0 0 1",
    }));
  }
  state.previousRadarPoints = nextPoints;
}

function driftForNode(node) {
  if (lowMotionMode()) {
    return { dx: 0, dy: 0, duration: 0 };
  }
  const seed = String(node.id || node.label || "");
  let total = 0;
  for (let index = 0; index < seed.length; index += 1) {
    total += seed.charCodeAt(index) * (index + 1);
  }
  const angle = (total % 360) * Math.PI / 180;
  const distance = node.type === "root" ? 0 : 12 + (total % 11);
  return {
    dx: Math.cos(angle) * distance,
    dy: Math.sin(angle) * distance,
    duration: 8 + (total % 7),
  };
}

function shouldDrift() {
  return false;
}

function addMoveTransition(group, node) {
  if (orbitGraphActive()) return;
  if (heavyGraphMotionDisabled()) return;
  const previous = state.previousPositions.get(node.id);
  if (!previous) return;
  const dx = previous.x - node.x;
  const dy = previous.y - node.y;
  if (Math.hypot(dx, dy) < 1.5) return;
  group.append(svgEl("animateTransform", {
    attributeName: "transform",
    type: "translate",
    values: `${dx.toFixed(2)} ${dy.toFixed(2)}; 0 0`,
    dur: `${motion.cluster}ms`,
    begin: "0s",
    fill: "freeze",
    additive: "sum",
    calcMode: "spline",
    keyTimes: "0;1",
    keySplines: "0.2 0 0 1",
  }));
}

function addLineTransition(line, edge, from, to) {
  if (orbitGraphActive()) return;
  if (heavyGraphMotionDisabled()) return;
  const oldFrom = state.previousPositions.get(edge.from);
  const oldTo = state.previousPositions.get(edge.to);
  if (!oldFrom || !oldTo) return;
  const attrs = [
    ["x1", oldFrom.x, from.x],
    ["y1", oldFrom.y, from.y],
    ["x2", oldTo.x, to.x],
    ["y2", oldTo.y, to.y],
  ];
  for (const [attributeName, start, end] of attrs) {
    if (Math.abs(start - end) < 1) continue;
    line.append(svgEl("animate", {
      attributeName,
      from: start.toFixed(2),
      to: end.toFixed(2),
      dur: `${motion.cluster}ms`,
      begin: "0s",
      fill: "freeze",
      calcMode: "spline",
      keyTimes: "0;1",
      keySplines: "0.2 0 0 1",
    }));
  }
}

function setGraphAnimationsPaused(paused) {
  state.orbitPaused = Boolean(paused);
  if (paused) {
    stopOrbitRotation(false);
    applyOrbitTransform();
  } else {
    scheduleOrbitRotation();
  }
  if (reduceMotion || !el.graph) return;
  try {
    if (paused && typeof el.graph.pauseAnimations === "function") {
      el.graph.pauseAnimations();
    }
    if (!paused && typeof el.graph.unpauseAnimations === "function") {
      el.graph.unpauseAnimations();
    }
  } catch (_) {
    // If a browser lacks SVG timeline controls, hover still shows the tooltip.
  }
}

function supportsHoverTooltip(event) {
  if (event?.pointerType && event.pointerType !== "mouse") {
    return false;
  }
  return hasFineHover() && !compactViewport();
}

function applyGraphView(options = {}) {
  const scheduleRender = options.scheduleRender !== false;
  const view = state.graphView;
  el.graph.setAttribute("viewBox", `${view.x} ${view.y} ${view.width} ${view.height}`);
  el.zoomLevel.textContent = `${Math.round((state.graphBounds.width / view.width) * 100)}%`;
  if (scheduleRender && !state.drawingGraph) {
    scheduleGraphViewportRender();
  }
}

function scheduleGraphViewportRender() {
  if (!state.graphSnapshot || state.graphViewportFrame) return;
  state.graphViewportFrame = requestAnimationFrame(() => {
    state.graphViewportFrame = 0;
    drawGraphSnapshot();
  });
}

function motionEase(progress) {
  return 1 - ((1 - progress) ** 3);
}

function animateGraphView(target, duration = motion.focus, options = {}) {
  if (reduceMotion) {
    duration = 0;
  }
  if (duration <= 0) {
    state.graphView = { ...target };
    applyGraphView();
    options.onComplete?.();
    return;
  }
  const start = { ...state.graphView };
  const startedAt = performance.now();
  if (state.viewAnimation) {
    cancelAnimationFrame(state.viewAnimation);
  }
  const tick = (now) => {
    const progress = Math.min(1, (now - startedAt) / duration);
    const eased = motionEase(progress);
    state.graphView = {
      x: start.x + (target.x - start.x) * eased,
      y: start.y + (target.y - start.y) * eased,
      width: start.width + (target.width - start.width) * eased,
      height: start.height + (target.height - start.height) * eased,
    };
    applyGraphView();
    if (progress < 1) {
      state.viewAnimation = requestAnimationFrame(tick);
    } else {
      state.viewAnimation = 0;
      options.onComplete?.();
    }
  };
  state.viewAnimation = requestAnimationFrame(tick);
}

function graphPointFromEvent(event) {
  return graphPointFromClient(event.clientX, event.clientY);
}

function graphPointFromClient(clientX, clientY, view = state.graphView) {
  const rect = el.graph.getBoundingClientRect();
  const x = view.x + ((clientX - rect.left) / rect.width) * view.width;
  const y = view.y + ((clientY - rect.top) / rect.height) * view.height;
  return { x, y };
}

function zoomGraph(factor, anchor = { x: state.graphView.x + state.graphView.width / 2, y: state.graphView.y + state.graphView.height / 2 }, options = {}) {
  if (!options.preserveFollow) {
    clearGraphFollow();
  }
  const oldView = state.graphView;
  const width = Math.min(state.graphBounds.width * 1.8, Math.max(220, oldView.width * factor));
  const height = Math.min(state.graphBounds.height * 1.8, Math.max(140, oldView.height * factor));
  const ax = (anchor.x - oldView.x) / oldView.width;
  const ay = (anchor.y - oldView.y) / oldView.height;
  state.graphView = {
    x: anchor.x - ax * width,
    y: anchor.y - ay * height,
    width,
    height,
  };
  applyGraphView();
}

function graphGestureThreshold() {
  return touchOptimizedMode() ? 12 : 5;
}

function graphPointers() {
  return [...state.activePointers.values()];
}

function graphPointerCenter(pointers = graphPointers()) {
  if (!pointers.length) return { clientX: 0, clientY: 0 };
  const total = pointers.reduce((sum, pointer) => ({
    clientX: sum.clientX + pointer.clientX,
    clientY: sum.clientY + pointer.clientY,
  }), { clientX: 0, clientY: 0 });
  return {
    clientX: total.clientX / pointers.length,
    clientY: total.clientY / pointers.length,
  };
}

function graphPointerDistance(pointers = graphPointers()) {
  if (pointers.length < 2) return 0;
  return Math.hypot(
    pointers[0].clientX - pointers[1].clientX,
    pointers[0].clientY - pointers[1].clientY,
  );
}

function suppressNextNodeClick() {
  state.suppressNextNodeClick = true;
  if (state.suppressClickTimer) {
    window.clearTimeout(state.suppressClickTimer);
  }
  state.suppressClickTimer = window.setTimeout(() => {
    state.suppressNextNodeClick = false;
    state.suppressClickTimer = 0;
  }, 360);
}

function clearSuppressedNodeClick() {
  state.suppressNextNodeClick = false;
  if (state.suppressClickTimer) {
    window.clearTimeout(state.suppressClickTimer);
    state.suppressClickTimer = 0;
  }
}

function startGraphPanGesture(pointer, blankClickCandidate, moved = false, tapNodeId = "") {
  state.dragging = true;
  state.blankClickCandidate = blankClickCandidate;
  state.dragStart = {
    clientX: pointer.clientX,
    clientY: pointer.clientY,
    view: { ...state.graphView },
  };
  state.graphGesture = {
    mode: "pan",
    pointerId: pointer.pointerId,
    startClientX: pointer.clientX,
    startClientY: pointer.clientY,
    startView: { ...state.graphView },
    moved,
    hadPinch: false,
    tapNodeId,
  };
  el.graphWrap.classList.add("dragging");
}

function startGraphPinchGesture() {
  const pointers = graphPointers().slice(0, 2);
  if (pointers.length < 2) return;
  clearGraphFollow();
  const center = graphPointerCenter(pointers);
  const distance = Math.max(1, graphPointerDistance(pointers));
  state.dragging = true;
  state.blankClickCandidate = false;
  state.dragStart = null;
  state.graphGesture = {
    mode: "pinch",
    startCenter: center,
    startDistance: distance,
    startView: { ...state.graphView },
    anchor: graphPointFromClient(center.clientX, center.clientY),
    moved: true,
    hadPinch: true,
  };
  el.graphWrap.classList.add("dragging");
  suppressNextNodeClick();
}

function updateGraphPanGesture(pointer) {
  const gesture = state.graphGesture;
  if (!gesture || gesture.mode !== "pan") return;
  const rect = el.graph.getBoundingClientRect();
  const dx = ((pointer.clientX - gesture.startClientX) / rect.width) * gesture.startView.width;
  const dy = ((pointer.clientY - gesture.startClientY) / rect.height) * gesture.startView.height;
  const moved = Math.hypot(pointer.clientX - gesture.startClientX, pointer.clientY - gesture.startClientY);
  if (moved >= graphGestureThreshold()) {
    gesture.moved = true;
    state.blankClickCandidate = false;
    clearGraphFollow();
    suppressNextNodeClick();
  }
  if (!gesture.moved) {
    return;
  }
  state.graphView = clampGraphView({
    ...gesture.startView,
    x: gesture.startView.x - dx,
    y: gesture.startView.y - dy,
  });
  applyGraphView();
}

function updateGraphPinchGesture() {
  const gesture = state.graphGesture;
  const pointers = graphPointers().slice(0, 2);
  if (!gesture || gesture.mode !== "pinch" || pointers.length < 2) return;
  const rect = el.graph.getBoundingClientRect();
  const center = graphPointerCenter(pointers);
  const distance = Math.max(1, graphPointerDistance(pointers));
  const factor = gesture.startDistance / distance;
  const width = Math.min(state.graphBounds.width * 1.8, Math.max(220, gesture.startView.width * factor));
  const height = Math.min(state.graphBounds.height * 1.8, Math.max(140, gesture.startView.height * factor));
  const sx = (center.clientX - rect.left) / rect.width;
  const sy = (center.clientY - rect.top) / rect.height;
  state.graphView = clampGraphView({
    x: gesture.anchor.x - sx * width,
    y: gesture.anchor.y - sy * height,
    width,
    height,
  });
  gesture.moved = true;
  applyGraphView();
}

function finishGraphGesture(event) {
  const gesture = state.graphGesture;
  const shouldClearFocus = Boolean(
    gesture &&
    gesture.mode === "pan" &&
    state.blankClickCandidate &&
    !gesture.moved &&
    !gesture.hadPinch &&
    (state.focusNode || state.pendingFocusNode)
  );
  const shouldClearSelection = Boolean(
    gesture &&
    gesture.mode === "pan" &&
    state.blankClickCandidate &&
    !gesture.moved &&
    !gesture.hadPinch &&
    !state.focusNode &&
    !state.pendingFocusNode &&
    state.selectedNode
  );
  if (gesture?.moved || gesture?.hadPinch) {
    suppressNextNodeClick();
  }
  const tapNode = (
    gesture &&
    gesture.mode === "pan" &&
    !gesture.moved &&
    !gesture.hadPinch &&
    gesture.tapNodeId
  ) ? state.graphNodesById.get(gesture.tapNodeId) : null;
  state.dragging = false;
  state.dragStart = null;
  state.graphGesture = null;
  state.blankClickCandidate = false;
  el.graphWrap.classList.remove("dragging");
  if (shouldClearFocus) {
    clearGraphFocus();
  } else if (shouldClearSelection) {
    clearGraphSelection();
  }
  if (tapNode) {
    selectGraphNode(tapNode);
    suppressNextNodeClick();
  }
  if (event?.pointerId !== undefined && el.graph.hasPointerCapture(event.pointerId)) {
    el.graph.releasePointerCapture(event.pointerId);
  }
  scheduleOrbitRotation();
}

function continueGraphPanAfterPinch() {
  const pointer = graphPointers()[0];
  if (!pointer) return;
  startGraphPanGesture(pointer, false, true);
  if (state.graphGesture) {
    state.graphGesture.hadPinch = true;
  }
}

function resetGraphView() {
  if (state.focusNode || state.pendingFocusNode) {
    clearGraphFocus();
    return;
  }
  clearGraphFollow();
  state.focusReturnView = null;
  animateGraphView({ ...state.graphBounds }, motion.reset);
}

function showGraphDetail(node) {
  if (!node) {
    el.graphDetail.innerHTML = "<strong>关系详情</strong><br>点按节点查看完整信息；桌面端也可悬停预览。";
    return;
  }
  if (node.type === "peer") {
    const peer = node.peer || {};
    const expanded = peerExpanded(peer);
    const endpoint = peer.endpoint || "未记录";
    const action = expanded ? "再次点按将收起这个共享史馆。" : "点按后只展开这台机器的共享树叶。";
    el.graphDetail.innerHTML = `<strong>${escapeText(peerMachineName(peer))}</strong><br>类型：共享机器；状态：${escapeText(peerStatusLabel(peer.status))}；权限：${escapeText(peerRoleLabel(peer.role))}<br>端点：${escapeText(endpoint)}<br>记录：${escapeText(peer.count || peer.shown || 0)} 条；${escapeText(action)}`;
    return;
  }
  if (node.type === "leaf") {
    const entry = node.entry || {};
    const parts = entry.court_code_parts || {};
    const codeLine = entry.court_code
      ? `<br>诏令编号：<span class="entry-code">${escapeText(entry.court_code)}</span>`
      : "";
    const lineage = lineageLabel(entry);
    const lineageLine = lineage
      ? `<br>${escapeText(lineage)}`
      : "";
    const fourCodeLine = entry.court_code
      ? `<br>四字码：状态 ${escapeText(parts.status || "?")} / 风险 ${escapeText(parts.risk || "?")} / 知识库价值 ${escapeText(parts.knowledge_value || "?")} / 优先级 ${escapeText(parts.priority || "?")}`
      : "";
    const statusLine = `<br>状态：<span style="color:${statusColor(entry.status)}">${escapeText(statusLabel(entry.status))}</span>`;
    const keywords = primaryKeywords(entry).join("，") || "无";
    el.graphDetail.innerHTML = `<strong>${escapeText(displayTitleZh(entry))} / ${escapeText(actionLabel(entry))}</strong>${codeLine}${lineageLine}${fourCodeLine}${statusLine}<br>关键词：${escapeText(keywords)}<br>摘要：${escapeText(displaySummaryZh(entry))}<br>理由：${escapeText(displayReason(entry))}`;
    return;
  }
  const label = node.label || node.id;
  const lineageLevel = node.type === "lineage" && node.level ? `<br>谱系层级：${escapeText(node.level)}` : "";
  el.graphDetail.innerHTML = `<strong>${escapeText(label)}</strong><br>类型：${escapeText(graphTypeLabel(node.type))}；关联记录：${node.count || 0}${lineageLevel}`;
}

function selectGraphNode(node) {
  blurTextEntryForGraphInteraction();
  clearGraphFollow();
  preferTreeForFocus();
  if (node.type !== "leaf") {
    rememberFocusReturnView();
    rememberFacetStateForFocus();
  }
  if (node.type === "lineage") {
    state.selectedNode = node.id;
    state.focusNode = node.id;
    state.pendingFocusNode = node.id;
    state.selectedId = "";
    showGraphDetail(node);
    renderGraph();
    revealGraphDetail();
    return;
  }
  if (node.type === "leaf" && node.entry) {
    selectEntry(node.entry, { focusNode: true, reveal: true, preservePanels: true });
    return;
  }
  state.selectedNode = node.id;
  state.focusNode = node.id;
  state.pendingFocusNode = node.id;
  if (node.type === "peer") {
    const peerId = String(node.peer?.peer_id || "");
    state.activePeerId = state.activePeerId === peerId ? "" : peerId;
    state.selectedId = "";
    setEditorEditing(false);
    loadState().then(() => {
      preferTreeForFocus();
      state.selectedNode = node.id;
      state.focusNode = node.id;
      state.pendingFocusNode = node.id;
      renderGraph();
      revealGraphDetail();
    }).catch((error) => setStatus(`共享史馆载入失败：${error.message}`, true));
    showGraphDetail(node);
    revealGraphDetail();
    return;
  }
  if (node.type === "keyword") {
    el.searchInput.value = node.label;
    state.query = node.label;
    loadState().catch((error) => setStatus(`检索失败：${error.message}`, true));
    revealGraphDetail();
    return;
  }
  showGraphDetail(node);
  renderGraph();
  revealGraphDetail();
}

function tooltipHtml(node) {
  if (node.type === "leaf") {
    const entry = node.entry || {};
    return `
      <strong>${escapeText(displayTitleZh(entry))}</strong>
      <span>诏令编号：${escapeText(entry.court_code || "未生成")}</span>
      <span>状态：${escapeText(statusLabel(entry.status))}</span>
      <span>中文关键词：${escapeText(primaryKeywords(entry).join("，") || "无")}</span>
      <span>中文摘要：${escapeText(displaySummaryZh(entry) || "未记录中文摘要")}</span>
    `;
  }
  if (node.type === "peer") {
    const peer = node.peer || {};
    return `
      <strong>${escapeText(peerMachineName(peer))}</strong>
      <span>节点：共享机器</span>
      <span>状态：${escapeText(peerStatusLabel(peer.status))}</span>
      <span>权限：${escapeText(peerRoleLabel(peer.role))}</span>
      <span>说明：${escapeText(peerExpanded(peer) ? "已展开，点按可收起。" : "未展开，点按后载入这台机器。")}</span>
    `;
  }
  const scope = node.type === "keyword" ? "关键词" : (node.type === "lineage" ? `谱系层级：${node.level || "内容"}` : node.type);
  return `
    <strong>${escapeText(node.label || node.id)}</strong>
    <span>节点：${escapeText(graphTypeLabel(node.type))}</span>
    <span>范围：${escapeText(node.type === "keyword" || node.type === "lineage" ? scope : graphTypeLabel(node.type))}</span>
    <span>中文关键词：${escapeText(node.label || "无")}</span>
    <span>中文摘要：关联记录 ${escapeText(node.count || 0)} 条。</span>
  `;
}

function positionTooltip(event) {
  if (!el.graphTooltip || !el.graphWrap) return;
  const rect = el.graphWrap.getBoundingClientRect();
  const left = Math.min(rect.width - 280, Math.max(12, event.clientX - rect.left + 16));
  const top = Math.min(rect.height - 156, Math.max(12, event.clientY - rect.top + 16));
  if (state.tooltipFrame) {
    cancelAnimationFrame(state.tooltipFrame);
  }
  state.tooltipFrame = requestAnimationFrame(() => {
    el.graphTooltip.style.left = `${left}px`;
    el.graphTooltip.style.top = `${top}px`;
    state.tooltipFrame = 0;
  });
}

function showNodeTooltip(event, node) {
  if (!el.graphTooltip || !supportsHoverTooltip(event)) return;
  state.hoveredNode = node.id;
  el.graphTooltip.innerHTML = tooltipHtml(node);
  positionTooltip(event);
  el.graphTooltip.classList.add("show");
}

function hideNodeTooltip() {
  state.hoveredNode = "";
  if (el.graphTooltip) {
    el.graphTooltip.classList.remove("show");
  }
}

function graphNodeFromEvent(event) {
  const target = event.target;
  if (!(target instanceof Element)) return null;
  const nodeTarget = target.closest(".graph-node");
  if (!nodeTarget || !el.graph.contains(nodeTarget)) return null;
  const nodeId = nodeTarget.getAttribute("data-node-id") || "";
  return state.graphNodesById.get(nodeId) || null;
}

function pointInGraphViewport(point, padding = graphViewportPadding) {
  const view = state.graphView;
  return (
    point.x >= view.x - padding &&
    point.x <= view.x + view.width + padding &&
    point.y >= view.y - padding &&
    point.y <= view.y + view.height + padding
  );
}

function nodeInGraphViewport(node) {
  const nodePadding = Math.max(graphViewportPadding, nodeFootprint(node) * 1.65 + 36);
  if (pointInGraphViewport(node, nodePadding)) return true;
  return orbitGraphActive() && pointInGraphViewport(orbitNodePoint(node), nodePadding);
}

function visibleGraphNodeIds(positions, edges, related, focusIds = null) {
  const visible = new Set();
  if (focusIds?.size) {
    for (const id of focusIds) {
      if (positions.has(id)) {
        visible.add(id);
      }
    }
    return visible;
  }
  for (const [id, node] of positions.entries()) {
    if (nodeInGraphViewport(node)) {
      visible.add(id);
    }
  }
  if (state.selectedNode) {
    visible.add(state.selectedNode);
    for (const id of related) {
      visible.add(id);
    }
  }
  if (!visible.size) {
    visible.add("root");
  }
  for (const edge of edges) {
    if (visible.has(edge.from) || visible.has(edge.to)) {
      visible.add(edge.from);
      visible.add(edge.to);
    }
  }
  return visible;
}

function orbitGraphActive(snapshot = state.graphSnapshot) {
  return Boolean(
    snapshot &&
    state.orbitEnabled &&
    state.graphMode === "star" &&
    !snapshot.focusIds?.size &&
    !document.hidden
  );
}

function orbitRotationAllowed(snapshot = state.graphSnapshot) {
  return Boolean(
    orbitGraphActive(snapshot) &&
    !state.orbitPaused &&
    !state.dragging &&
    !state.graphGesture &&
    snapshot.nodes.length <= (touchOptimizedMode() ? 700 : 1400)
  );
}

function orbitLayerIndex(node = {}) {
  if (node.type === "root") return 0;
  if (node.type === "peer") return 1;
  if (node.type === "lineage") return Number(node.lineageIndex || 0) + 1;
  if (node.type === "leaf") {
    const parent = state.graphSnapshot?.positions?.get(node.parentLineageId);
    return parent?.type === "lineage" ? Number(parent.lineageIndex || 0) + 2 : 7;
  }
  if (node.type === "keyword") return 8;
  if (node.type === "facet") return 9;
  return 6;
}

function orbitLayerSpeed(node = {}) {
  if (node.type === "root") return 0;
  const layer = orbitLayerIndex(node);
  return clamp(1.3 - layer * 0.085, 0.42, 1.18);
}

function orbitLayerPull(node = {}) {
  if (node.type === "root") return 1.4;
  const layer = orbitLayerIndex(node);
  return clamp(1.34 - layer * 0.08, 0.54, 1.26);
}

function orbitGroupKey(node = {}) {
  return `${orbitLayerIndex(node)}:${starArmKey(node)}`;
}

function orbitGroupPhase(node = {}) {
  const layer = orbitLayerIndex(node);
  const group = orbitGroupKey(node);
  const phase = ((hashText(group) % 41) - 20) * Math.PI / 900;
  return phase + layer * 0.018;
}

function orbitTargetPoint(node = {}, angleDegrees = state.orbitAngle) {
  const center = state.orbitCenter || { x: 0, y: 0 };
  if (node.type === "root") {
    return { x: node.x, y: node.y };
  }
  const dx = node.x - center.x;
  const dy = (node.y - center.y) / orbitEllipseRatio;
  const theta = -(angleDegrees * orbitLayerSpeed(node)) * Math.PI / 180 + orbitGroupPhase(node);
  const cos = Math.cos(theta);
  const sin = Math.sin(theta);
  return {
    x: center.x + dx * cos - dy * sin,
    y: center.y + (dx * sin + dy * cos) * orbitEllipseRatio,
  };
}

function orbitNodePoint(node = {}, angleDegrees = state.orbitAngle) {
  if (!orbitGraphActive() || node.type === "root") {
    return { x: node.x, y: node.y };
  }
  const body = state.orbitPhysics.get(node.id);
  if (body) {
    return { x: body.x, y: body.y };
  }
  return orbitTargetPoint(node, angleDegrees);
}

function orbitPointForNode(node = {}) {
  return orbitGraphActive() ? orbitNodePoint(node) : { x: node.x, y: node.y };
}

function orbitRepulsionRadius(node = {}) {
  return Math.max(28, nodeRadius(node) + graphLabelWidth(node) * 0.16 + (touchOptimizedMode() ? 18 : 24));
}

function orbitBodyForNode(node = {}, target = orbitTargetPoint(node)) {
  let body = state.orbitPhysics.get(node.id);
  if (!body) {
    body = {
      id: node.id,
      x: target.x,
      y: target.y,
      vx: 0,
      vy: 0,
      layer: orbitLayerIndex(node),
      group: orbitGroupKey(node),
    };
    state.orbitPhysics.set(node.id, body);
  }
  body.node = node;
  body.target = target;
  body.layer = orbitLayerIndex(node);
  body.group = orbitGroupKey(node);
  body.radius = orbitRepulsionRadius(node);
  if (Math.hypot(body.x - target.x, body.y - target.y) > 180) {
    body.x = target.x;
    body.y = target.y;
    body.vx = 0;
    body.vy = 0;
  }
  return body;
}

function pruneOrbitPhysics(visibleIds) {
  for (const id of state.orbitPhysics.keys()) {
    if (!visibleIds.has(id)) {
      state.orbitPhysics.delete(id);
    }
  }
}

function orbitApplyPairRepulsion(a, b, dt) {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  let distance = Math.hypot(dx, dy);
  if (!distance) {
    distance = 0.01;
  }
  const sameLayer = a.layer === b.layer;
  const sameGroup = a.group === b.group;
  const desired = a.radius + b.radius + (sameGroup ? 16 : 6) + (sameLayer ? 10 : 0);
  if (distance >= desired) return;
  const nx = dx / distance;
  const ny = dy / distance;
  const overlap = (desired - distance) / desired;
  const strength = overlap * (sameLayer ? 1.7 : 1.05) * dt;
  a.vx -= nx * strength;
  a.vy -= ny * strength;
  b.vx += nx * strength;
  b.vy += ny * strength;
}

function orbitApplyRepulsion(bodies, dt) {
  const limit = touchOptimizedMode() ? Math.min(orbitPhysicsRepulsionLimit, 420) : orbitPhysicsRepulsionLimit;
  if (bodies.length > limit) return;
  const cells = new Map();
  const cellFor = (body) => `${Math.floor(body.x / orbitPhysicsCellSize)}:${Math.floor(body.y / orbitPhysicsCellSize)}`;
  for (const body of bodies) {
    const key = cellFor(body);
    const items = cells.get(key) || [];
    items.push(body);
    cells.set(key, items);
  }
  for (const body of bodies) {
    const cx = Math.floor(body.x / orbitPhysicsCellSize);
    const cy = Math.floor(body.y / orbitPhysicsCellSize);
    for (let ox = -1; ox <= 1; ox += 1) {
      for (let oy = -1; oy <= 1; oy += 1) {
        const items = cells.get(`${cx + ox}:${cy + oy}`) || [];
        for (const other of items) {
          if (String(body.id) >= String(other.id)) continue;
          orbitApplyPairRepulsion(body, other, dt);
        }
      }
    }
  }
}

function orbitApplyEdgeAttraction(bodyById, positions, dt) {
  for (const { edge } of state.orbitEdgeElements) {
    const a = bodyById.get(edge.from);
    const b = bodyById.get(edge.to);
    if (!a && !b) continue;
    const from = a || positions.get(edge.from);
    const to = b || positions.get(edge.to);
    if (!from || !to) continue;
    const dx = to.x - from.x;
    const dy = to.y - from.y;
    const distance = Math.hypot(dx, dy) || 0.01;
    const desired = edge.type === "lineage" ? 126 : 158;
    if (distance <= desired) continue;
    const fromNode = a?.node || positions.get(edge.from) || {};
    const toNode = b?.node || positions.get(edge.to) || {};
    const attractionWeight = (orbitLayerPull(fromNode) + orbitLayerPull(toNode)) / 2;
    const pull = Math.min(0.58, (distance - desired) * 0.0028) * attractionWeight * dt;
    const nx = dx / distance;
    const ny = dy / distance;
    if (a) {
      a.vx += nx * pull;
      a.vy += ny * pull;
    }
    if (b) {
      b.vx -= nx * pull;
      b.vy -= ny * pull;
    }
  }
}

function orbitCounterClockwiseTangent(point = {}) {
  const center = state.orbitCenter || { x: 0, y: 0 };
  const dx = Number(point.x || 0) - center.x;
  const dy = (Number(point.y || 0) - center.y) / orbitEllipseRatio;
  const length = Math.hypot(dx, dy);
  if (length < 8) return null;
  const tx = dy / length;
  const ty = (-dx * orbitEllipseRatio) / length;
  const tangentLength = Math.hypot(tx, ty) || 1;
  return { x: tx / tangentLength, y: ty / tangentLength };
}

function orbitScreenAngle(point = {}) {
  const center = state.orbitCenter || { x: 0, y: 0 };
  const dx = Number(point.x || 0) - center.x;
  const dy = (Number(point.y || 0) - center.y) / orbitEllipseRatio;
  return Math.atan2(dy, dx);
}

function orbitAngleDelta(fromPoint = {}, toPoint = {}) {
  let delta = orbitScreenAngle(toPoint) - orbitScreenAngle(fromPoint);
  while (delta > Math.PI) delta -= Math.PI * 2;
  while (delta < -Math.PI) delta += Math.PI * 2;
  return delta;
}

function biasOrbitCounterClockwiseMotion(body, dt) {
  if (!body?.node || body.node.type === "root") return;
  const tangent = orbitCounterClockwiseTangent(body);
  if (!tangent) return;
  const current = body.vx * tangent.x + body.vy * tangent.y;
  const layerDrive = orbitLayerSpeed(body.node) * orbitLayerPull(body.node);
  const bias = (touchOptimizedMode() ? 0.042 : 0.056) * layerDrive * clamp(dt, 0.55, 1.7);
  if (current < -bias) {
    const correction = Math.min((-current - bias) * 0.62, bias * 2.2);
    body.vx += tangent.x * correction;
    body.vy += tangent.y * correction;
  }
  body.vx += tangent.x * bias;
  body.vy += tangent.y * bias;
}

function softenClockwiseOrbitDrift(body, previous, dt) {
  if (!body?.node || body.node.type === "root") return;
  const tangent = orbitCounterClockwiseTangent(body);
  if (!tangent) return;
  const delta = orbitAngleDelta(previous, body);
  const allowedClockwise = 0.00025 * clamp(dt, 0.6, 1.7);
  if (delta <= allowedClockwise) return;
  const center = state.orbitCenter || { x: 0, y: 0 };
  const previousAngle = orbitScreenAngle(previous);
  const radius = Math.max(40, Math.hypot(body.x - center.x, (body.y - center.y) / orbitEllipseRatio));
  const nextAngle = previousAngle + allowedClockwise;
  body.x = center.x + Math.cos(nextAngle) * radius;
  body.y = center.y + Math.sin(nextAngle) * radius * orbitEllipseRatio;
  const tangentVelocity = body.vx * tangent.x + body.vy * tangent.y;
  if (tangentVelocity < 0) {
    body.vx -= tangent.x * tangentVelocity * 0.74;
    body.vy -= tangent.y * tangentVelocity * 0.74;
  }
}

function advanceOrbitPhysics(elapsedMs = 16) {
  const snapshot = state.graphSnapshot;
  const positions = snapshot?.positions || new Map();
  const points = new Map();
  const active = orbitGraphActive(snapshot);
  if (!active) {
    state.orbitPhysics.clear();
    for (const [id, node] of positions.entries()) {
      points.set(id, { x: node.x, y: node.y });
    }
    return points;
  }
  const visibleIds = new Set(state.orbitNodeElements.keys());
  state.orbitVisibleIds = visibleIds;
  pruneOrbitPhysics(visibleIds);
  const dt = clamp(elapsedMs / 16.67, 0.25, 2.2);
  const bodyById = new Map();
  const bodies = [];
  for (const id of visibleIds) {
    const node = positions.get(id);
    if (!node) continue;
    if (node.type === "root") {
      points.set(id, { x: node.x, y: node.y });
      continue;
    }
    const target = orbitTargetPoint(node);
    const body = orbitBodyForNode(node, target);
    bodyById.set(id, body);
    bodies.push(body);
    const spring = (touchOptimizedMode() ? 0.04 : 0.052) * orbitLayerPull(node);
    body.vx += (target.x - body.x) * spring * dt;
    body.vy += (target.y - body.y) * spring * dt;
  }
  orbitApplyEdgeAttraction(bodyById, positions, dt);
  orbitApplyRepulsion(bodies, dt);
  const damping = Math.pow(touchOptimizedMode() ? 0.78 : 0.82, dt);
  for (const body of bodies) {
    const previous = { x: body.x, y: body.y };
    body.vx *= damping;
    body.vy *= damping;
    biasOrbitCounterClockwiseMotion(body, dt);
    body.x += body.vx * dt;
    body.y += body.vy * dt;
    const maxOffset = touchOptimizedMode() ? 74 : 96;
    const dx = body.x - body.target.x;
    const dy = body.y - body.target.y;
    const offset = Math.hypot(dx, dy);
    if (offset > maxOffset) {
      const pullback = (offset - maxOffset) / offset;
      body.x -= dx * pullback * 0.62;
      body.y -= dy * pullback * 0.62;
      body.vx *= 0.62;
      body.vy *= 0.62;
    }
    softenClockwiseOrbitDrift(body, previous, dt);
    points.set(body.id, { x: body.x, y: body.y });
  }
  return points;
}

function orbitLayerGuideRadii(positions, visibleIds) {
  if (!orbitGraphActive()) return [];
  const center = state.orbitCenter || { x: 0, y: 0 };
  const layers = new Map();
  for (const id of visibleIds) {
    const node = positions.get(id);
    if (!node || node.type === "root") continue;
    const layer = orbitLayerIndex(node);
    const items = layers.get(layer) || [];
    const dx = node.x - center.x;
    const dy = (node.y - center.y) / orbitEllipseRatio;
    items.push(Math.hypot(dx, dy));
    layers.set(layer, items);
  }
  return [...layers.entries()]
    .map(([layer, values]) => ({
      layer,
      radius: values.reduce((sum, value) => sum + value, 0) / Math.max(values.length, 1),
    }))
    .filter((item) => item.radius > 42)
    .sort((a, b) => a.layer - b.layer)
    .slice(0, touchOptimizedMode() ? 7 : 10);
}

function applyOrbitTransform(elapsedMs = 16) {
  const snapshot = state.graphSnapshot;
  const positions = snapshot?.positions || new Map();
  const active = orbitGraphActive(snapshot);
  const orbitPoints = advanceOrbitPhysics(active ? elapsedMs : 0);
  el.graphWrap?.classList.toggle("orbit-active", active);
  syncOrbitToggle();
  for (const [id, element] of state.orbitNodeElements.entries()) {
    const node = positions.get(id);
    if (!node) continue;
    const point = orbitPoints.get(id) || node;
    element.setAttribute("transform", `translate(${point.x},${point.y})`);
  }
  for (const { line, edge } of state.orbitEdgeElements) {
    const from = positions.get(edge.from);
    const to = positions.get(edge.to);
    if (!from || !to) continue;
    const fromPoint = orbitPoints.get(edge.from) || from;
    const toPoint = orbitPoints.get(edge.to) || to;
    line.setAttribute("x1", fromPoint.x);
    line.setAttribute("y1", fromPoint.y);
    line.setAttribute("x2", toPoint.x);
    line.setAttribute("y2", toPoint.y);
  }
  for (const guide of state.orbitGuideElements) {
    guide.setAttribute("opacity", active ? "1" : "0");
  }
  applyGraphFollow(orbitPoints, elapsedMs);
}

function stopOrbitRotation(reset = false) {
  if (state.orbitFrame) {
    cancelAnimationFrame(state.orbitFrame);
    state.orbitFrame = 0;
  }
  state.orbitLastFrame = 0;
  if (reset) {
    state.orbitAngle = 0;
    applyOrbitTransform();
  }
}

function scheduleOrbitRotation() {
  stopOrbitRotation(false);
  if (!orbitRotationAllowed()) {
    applyOrbitTransform();
    return;
  }
  const speed = orbitRotationSpeed * (touchOptimizedMode() ? 0.66 : 1);
  const tick = (now) => {
    if (!orbitRotationAllowed()) {
      state.orbitFrame = 0;
      state.orbitLastFrame = 0;
      applyOrbitTransform();
      return;
    }
    if (!state.orbitLastFrame) {
      state.orbitLastFrame = now;
    }
    const elapsed = Math.min(80, now - state.orbitLastFrame);
    state.orbitLastFrame = now;
    state.orbitAngle = (state.orbitAngle + (elapsed / 1000) * speed) % 360;
    applyOrbitTransform(elapsed);
    state.orbitFrame = requestAnimationFrame(tick);
  };
  state.orbitFrame = requestAnimationFrame(tick);
}

function drawGraphSnapshot(options = {}) {
  const snapshot = state.graphSnapshot;
  if (!el.graph || !snapshot) return;
  const { nodes, edges, positions, related, focusIds, center } = snapshot;
  stopOrbitRotation(false);
  state.orbitCenter = center || {
    x: state.graphBounds.x + state.graphBounds.width / 2,
    y: state.graphBounds.y + state.graphBounds.height / 2,
  };
  resetOrbitState();
  const visibleIds = visibleGraphNodeIds(positions, edges, related, focusIds);
  const dimmingActive = Boolean(state.selectedNode || state.focusNode);
  el.graphWrap?.classList.toggle("orbit-active", orbitGraphActive(snapshot));
  syncOrbitToggle();
  state.drawingGraph = true;
  el.graph.replaceChildren();
  applyGraphView();
  state.drawingGraph = false;
  const modeLabel = focusIds?.size
    ? `聚焦子图-树状排版（${focusIds.size} 节点）`
    : (state.graphMode === "tree" ? "树图" : "星图");
  el.graphMeta.textContent = `节点 ${nodes.length}，可见 ${visibleIds.size}，关系 ${edges.length}，总数 ${state.totalCount} 条，显示 ${state.entries.length} 条，模式 ${modeLabel}`;

  const orbitGroup = svgEl("g", { class: "graph-orbit" });
  const guideGroup = svgEl("g", { class: "graph-orbit-guide-layer" });
  for (const { layer, radius } of orbitLayerGuideRadii(positions, visibleIds)) {
    const guide = svgEl("ellipse", {
      cx: state.orbitCenter.x,
      cy: state.orbitCenter.y,
      rx: radius.toFixed(2),
      ry: (radius * 0.78).toFixed(2),
      class: `graph-orbit-guide graph-orbit-guide-${layer}`,
    });
    state.orbitGuideElements.push(guide);
    guideGroup.append(guide);
  }
  orbitGroup.append(guideGroup);

  const edgeGroup = svgEl("g", { class: "graph-edge-layer" });
  for (const edge of edges) {
    if (!visibleIds.has(edge.from) || !visibleIds.has(edge.to)) continue;
    const from = positions.get(edge.from);
    const to = positions.get(edge.to);
    if (!from || !to) continue;
    const fromPoint = orbitPointForNode(from);
    const toPoint = orbitPointForNode(to);
    const active = edgeActiveForSelection(edge, related);
    const line = svgEl("line", {
      x1: fromPoint.x,
      y1: fromPoint.y,
      x2: toPoint.x,
      y2: toPoint.y,
      class: `graph-edge ${edge.type} ${active ? "active" : ""} ${dimmingActive && !active ? "dimmed" : ""}`,
    });
    addLineTransition(line, edge, from, to);
    state.orbitEdgeElements.push({ line, edge });
    edgeGroup.append(line);
  }
  orbitGroup.append(edgeGroup);

  const nodeGroup = svgEl("g", { class: "graph-node-layer" });
  state.graphNodesById = new Map(positions);
  for (const node of positions.values()) {
    if (!visibleIds.has(node.id)) continue;
    const active = node.id === state.selectedNode || node.id === state.focusNode;
    const isRelated = related.has(node.id);
    const dimmed = Boolean(dimmingActive && !active && !isRelated);
    const group = svgEl("g", {
      class: `graph-node graph-node-${node.type} ${active ? "active" : ""} ${isRelated ? "related" : ""} ${dimmed ? "dimmed" : ""}`,
      "data-node-id": node.id,
      tabindex: "-1",
      focusable: "false",
      transform: `translate(${node.x},${node.y})`,
      style: `--node-delay:${Math.abs(Math.round((node.x + node.y) % 900))}ms;--class-color:${colorModeEnabled() ? classColorForNode(node) : "#ffffff"}`,
    });
    addMoveTransition(group, node);
    const drift = driftForNode(node);
    if (drift.duration && drift.dx && shouldDrift(node, related)) {
      group.append(svgEl("animateTransform", {
        attributeName: "transform",
        type: "translate",
        values: `0 0; ${drift.dx.toFixed(2)} ${drift.dy.toFixed(2)}; 0 0`,
        dur: `${drift.duration}s`,
        repeatCount: "indefinite",
        additive: "sum",
        class: "drift-animation",
      }));
    }
    const radius = nodeRadius(node);
    const hitRadius = Math.max(radius + 12, touchOptimizedMode() ? 28 : 20);
    const classColor = colorModeEnabled() ? classColorForNode(node) : nodeColor(node.type);
    if (isRectGraphNode(node)) {
      group.append(svgEl("rect", {
        x: -radius * 1.95,
        y: -radius * 1.12,
        width: radius * 3.9,
        height: radius * 2.24,
        rx: 11,
        fill: "none",
        class: "graph-halo",
      }));
    } else {
      group.append(svgEl("circle", { r: radius + 6, fill: "none", class: "graph-halo" }));
    }
    if (isRectGraphNode(node)) {
      group.append(svgEl("rect", {
        x: -hitRadius * 1.8,
        y: -hitRadius,
        width: hitRadius * 3.6,
        height: hitRadius * 2,
        rx: 10,
        fill: "transparent",
        class: "graph-hit-area",
      }));
    } else {
      group.append(svgEl("circle", { r: hitRadius, fill: "transparent", class: "graph-hit-area" }));
    }
    if (isRectGraphNode(node)) {
      group.append(svgEl("rect", {
        x: -radius * 1.98,
        y: -radius * 1.12,
        width: radius * 3.96,
        height: radius * 2.24,
        rx: 8,
        fill: "none",
        class: "graph-node-ring",
      }));
      group.append(svgEl("rect", {
        x: -radius * 1.8,
        y: -radius,
        width: radius * 3.6,
        height: radius * 2,
        rx: 7,
        fill: nodeFillColor(node),
        class: "graph-node-core",
      }));
      group.append(svgEl("circle", {
        r: Math.max(2.4, radius * 0.22),
        cx: -radius * 1.1,
        cy: -radius * 0.48,
        fill: classColor,
        class: "graph-node-spark",
      }));
    } else {
      group.append(svgEl("circle", { r: radius + 3, fill: "none", class: "graph-node-ring" }));
      group.append(svgEl("circle", { r: radius, fill: nodeFillColor(node), class: "graph-node-core" }));
      if (node.type !== "root") {
        group.append(svgEl("circle", {
          r: Math.max(2.2, radius * 0.34),
          cx: -radius * 0.25,
          cy: -radius * 0.27,
          fill: classColor,
          class: "graph-node-spark",
        }));
      }
    }
    const labelText = truncate(node.label, 14);
    const labelWidth = Math.min(136, Math.max(42, labelText.length * 7.2 + 16));
    group.append(svgEl("rect", {
      x: -labelWidth / 2,
      y: radius + 5,
      width: labelWidth,
      height: 18,
      rx: 9,
      class: "graph-node-label-bg",
    }));
    const label = svgEl("text", {
      y: radius + 18,
      "text-anchor": "middle",
    });
    label.textContent = labelText;
      group.append(label);
    nodeGroup.append(group);
    state.orbitNodeElements.set(node.id, group);
  }
  orbitGroup.append(nodeGroup);
  el.graph.append(orbitGroup);

  showGraphDetail(positions.get(state.selectedNode) || positions.get(state.focusNode));
  if (state.pendingFocusNode) {
    if (options.allowFocus) {
      focusGraphCluster(state.pendingFocusNode, positions, edges);
    }
    state.pendingFocusNode = "";
  }
  state.previousPositions = new Map([...positions.entries()].map(([id, node]) => [id, { x: node.x, y: node.y }]));
  applyOrbitTransform();
  scheduleOrbitRotation();
}

function renderGraph() {
  if (!el.graph) return;
  el.graph.classList.toggle("class-color-on", colorModeEnabled());
  syncFacetToggle();
  syncOrbitToggle();
  const { nodes, edges } = buildGraph();
  const layout = state.graphMode === "tree" ? treeLayout(nodes) : starLayout(nodes);
  const { positions, bounds, center } = layout;
  state.graphNodesById = new Map(positions);
  if (state.focusNode && !positions.has(state.focusNode)) {
    state.focusNode = "";
    state.pendingFocusNode = "";
    restoreFacetStateAfterFocus();
  }
  if (state.pendingFocusNode && !positions.has(state.pendingFocusNode)) {
    state.pendingFocusNode = "";
    restoreFacetStateAfterFocus();
  }
  if (state.selectedNode && !positions.has(state.selectedNode)) {
    state.selectedNode = "";
    state.selectedId = "";
  }
  const related = relatedNodeIds(edges);
  const focusIds = focusedSubgraphNodeIds(positions, edges, related);
  const focusedBounds = applyFocusedTreeLayout(positions, edges, focusIds);
  const graphBounds = focusedBounds || bounds;
  setGraphBounds(graphBounds);
  state.graphSnapshot = { nodes, edges, positions, bounds: graphBounds, center: center || null, related, focusIds };
  drawGraphSnapshot({ allowFocus: true });
}

async function api(path, options = {}) {
  return shiguanApi(path, options);
}

async function loadState() {
  if (location.protocol === "file:") {
    setStatus("静态文件已打开；修改、重建、导出需用 serve_shiguan_tree.py 启动本机/局域网服务。", true);
    return;
  }
  const params = new URLSearchParams();
  if (state.query) {
    params.set("q", state.query);
  }
  params.set("limit", String(graphEntryLimit()));
  params.set("ui_collapsed", "1");
  if (state.activePeerId) {
    params.set("peer_id", state.activePeerId);
  }
  const data = await api(`/api/state?${params.toString()}`);
  state.entries = data.entries || [];
  state.peers = data.peers || [];
  state.agentPresence = data.agent_presence || [];
  state.totalCount = Number(data.count || data.local_count || state.entries.length || 0);
  if (state.activePeerId && !peerForId(state.activePeerId)) {
    state.activePeerId = "";
  }
  state.knowledgeGraph = data.knowledge_graph || null;
  state.importQueue = data.import_queue || null;
  state.defaultShareHost = String(data.default_share_host || "");
  state.defaultSharePort = String(data.default_share_port || data.port || "");
  state.obsidianSync = data.obsidian_sync || null;
  refreshControlledOptionsFromEntries(state.entries);
  renderPeerStatusBar();
  const peerShown = Number(data.peer_count || 0);
  const localShown = Number(data.shown || 0);
  const queue = state.importQueue || {};
  const queueText = queue.pending_count
    ? `；待处理导入 ${queue.pending_count} 份，新增 ${queue.new_count || 0} 份，约 ${queue.estimated_tokens || 0} tokens，新增约 ${queue.new_estimated_tokens || 0} tokens`
    : "";
  const rootText = data.shared_shiguan_root ? `；权威库 ${truncate(String(data.shared_shiguan_root), 72)}` : "";
  const graphText = state.activePeerId
    ? `已展开 ${peerMachineName(peerForId(state.activePeerId) || {})}：${peerShown} 条`
    : "图谱默认折叠";
  const metaText = `本机 ${data.local_count || data.count || 0} 条，当前显示 ${localShown} 条；${graphText}${queueText}${rootText}；${serviceAccessText(data)}`;
  el.meta.textContent = metaText;
  el.meta.title = metaText;
  renderEntries();
  renderGraph();
  setStatus(`已载入：${data.index_path}`);
}

async function runAction(label, path, payload = {}) {
  setStatus(`${label}中...`);
  const data = await api(path, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  await loadState();
  return data;
}

el.searchBtn.addEventListener("click", async () => {
  state.query = el.searchInput.value.trim();
  try {
    await loadState();
  } catch (error) {
    setStatus(`检索失败：${error.message}`, true);
  }
});

el.searchInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    el.searchBtn.click();
  }
});

el.graphLimitInput.addEventListener("change", async () => {
  state.graphLimitTouched = true;
  graphEntryLimit();
  try {
    await loadState();
  } catch (error) {
    setStatus(`载入失败：${error.message}`, true);
  }
});

el.graphLimitInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    el.graphLimitInput.blur();
  }
});

el.toggleListBtn.addEventListener("click", () => {
  state.showList = !state.showList;
  updatePanelVisibility();
});

el.toggleEditorBtn.addEventListener("click", () => {
  state.showEditor = !state.showEditor;
  updatePanelVisibility();
});

el.collapseListBtn.addEventListener("click", () => {
  state.showList = false;
  updatePanelVisibility();
});

el.collapseEditorBtn.addEventListener("click", () => {
  state.showEditor = false;
  updatePanelVisibility();
});

el.graphModeStar.addEventListener("click", () => {
  setGraphMode("star", { render: true });
});

el.graphModeTree.addEventListener("click", () => {
  setGraphMode("tree", { render: true });
});

el.classColorToggle?.addEventListener("click", () => {
  const current = colorModeOrder.indexOf(state.classColorMode);
  state.classColorMode = colorModeOrder[(current + 1) % colorModeOrder.length] || "chain";
  updateColorModeControl();
  renderEntries();
  renderGraph();
  renderEntryProfile(formToEntry());
});

el.facetToggle?.addEventListener("click", () => {
  if (graphFocusActive() && !state.showFacets) {
    state.showFacets = true;
  } else {
    state.showFacets = !state.showFacets;
  }
  if (state.facetStateBeforeFocus !== null) {
    state.facetStateBeforeFocus = state.showFacets;
  }
  syncFacetToggle();
  renderGraph();
});

el.orbitToggle?.addEventListener("click", () => {
  state.orbitEnabled = !state.orbitEnabled;
  syncOrbitToggle();
  if (state.orbitEnabled) {
    scheduleOrbitRotation();
  } else {
    stopOrbitRotation(true);
  }
});

el.themeToggle?.addEventListener("click", () => {
  state.theme = state.theme === "dark" ? "light" : "dark";
  applyTheme();
});

document.addEventListener("visibilitychange", () => {
  if (document.hidden) {
    stopOrbitRotation(false);
  } else {
    scheduleOrbitRotation();
  }
});

el.zoomOutBtn.addEventListener("click", () => zoomGraph(1.2));
el.zoomInBtn.addEventListener("click", () => zoomGraph(0.82));
el.zoomResetBtn.addEventListener("click", resetGraphView);

el.graph.addEventListener("wheel", (event) => {
  event.preventDefault();
  const factor = event.deltaY > 0 ? 1.12 : 0.88;
  zoomGraph(factor, graphPointFromEvent(event));
}, { passive: false });

el.graph.addEventListener("pointerdown", (event) => {
  if (event.button !== undefined && event.button !== 0) return;
  blurTextEntryForGraphInteraction();
  if (!supportsHoverTooltip(event)) {
    hideNodeTooltip();
  }
  if (state.viewAnimation) {
    cancelAnimationFrame(state.viewAnimation);
    state.viewAnimation = 0;
  }
  const pointer = {
    pointerId: event.pointerId,
    clientX: event.clientX,
    clientY: event.clientY,
    pointerType: event.pointerType || "mouse",
  };
  const target = event.target;
  const nodeTarget = target instanceof Element ? target.closest(".graph-node") : null;
  const tapNodeId = nodeTarget?.getAttribute("data-node-id") || "";
  const blankClickCandidate = !nodeTarget;
  state.activePointers.set(event.pointerId, pointer);
  if (state.activePointers.size >= 2) {
    startGraphPinchGesture();
  } else {
    startGraphPanGesture(pointer, blankClickCandidate, false, tapNodeId);
  }
  stopOrbitRotation(false);
  el.graph.setPointerCapture(event.pointerId);
  event.preventDefault();
});

el.graph.addEventListener("pointerover", (event) => {
  const node = graphNodeFromEvent(event);
  if (!node || !supportsHoverTooltip(event)) return;
  setGraphAnimationsPaused(true);
  showNodeTooltip(event, node);
});

el.graph.addEventListener("pointermove", (event) => {
  const hoverNode = graphNodeFromEvent(event);
  if (hoverNode && supportsHoverTooltip(event)) {
    positionTooltip(event);
  }
  if (!state.activePointers.has(event.pointerId)) return;
  state.activePointers.set(event.pointerId, {
    pointerId: event.pointerId,
    clientX: event.clientX,
    clientY: event.clientY,
    pointerType: event.pointerType || "mouse",
  });
  if (state.activePointers.size >= 2) {
    if (state.graphGesture?.mode !== "pinch") {
      startGraphPinchGesture();
    }
    updateGraphPinchGesture();
  } else {
    const pointer = state.activePointers.get(event.pointerId);
    if (state.graphGesture?.mode !== "pan") {
      startGraphPanGesture(pointer, false, true);
    }
    updateGraphPanGesture(pointer);
  }
  event.preventDefault();
});

el.graph.addEventListener("pointerout", (event) => {
  if (!supportsHoverTooltip(event)) return;
  const fromNode = graphNodeFromEvent(event);
  const relatedTarget = event.relatedTarget;
  const toNode = relatedTarget instanceof Element ? relatedTarget.closest(".graph-node") : null;
  if (!fromNode || toNode) return;
  hideNodeTooltip();
  setGraphAnimationsPaused(false);
});

el.graph.addEventListener("click", (event) => {
  const node = graphNodeFromEvent(event);
  if (!node) return;
  if (state.suppressNextNodeClick) {
    event.preventDefault();
    event.stopPropagation();
    clearSuppressedNodeClick();
    return;
  }
  selectGraphNode(node);
});

function endGraphDrag(event) {
  if (event.pointerId !== undefined) {
    state.activePointers.delete(event.pointerId);
  }
  if (event.pointerId !== undefined && el.graph.hasPointerCapture(event.pointerId)) {
    el.graph.releasePointerCapture(event.pointerId);
  }
  if (state.activePointers.size >= 2) {
    startGraphPinchGesture();
    return;
  }
  if (state.activePointers.size === 1 && state.graphGesture?.mode === "pinch") {
    continueGraphPanAfterPinch();
    return;
  }
  finishGraphGesture(event);
}

el.graph.addEventListener("pointerup", endGraphDrag);
el.graph.addEventListener("pointercancel", endGraphDrag);

el.rebuildBtn.addEventListener("click", async () => {
  try {
    const data = await runAction("重建索引", "/api/rebuild");
    setStatus(`索引已重建：${data.entries} 条`);
  } catch (error) {
    setStatus(`重建失败：${error.message}`, true);
  }
});

el.growBtn.addEventListener("click", async () => {
  try {
    const data = await runAction("刷新生长树", "/api/grow");
    setStatus(`生长树已刷新：${data.tree_root}`);
  } catch (error) {
    setStatus(`刷新失败：${error.message}`, true);
  }
});

function setObsidianMode(mode) {
  const auto = mode === "auto";
  el.obsidianManualMode?.classList.toggle("active", !auto);
  el.obsidianAutoMode?.classList.toggle("active", auto);
  el.obsidianManualMode?.setAttribute("aria-pressed", String(!auto));
  el.obsidianAutoMode?.setAttribute("aria-pressed", String(auto));
  if (el.obsidianAutoEnabled) {
    el.obsidianAutoEnabled.checked = auto;
  }
}

function obsidianConfigPayload() {
  const paths = String(el.obsidianImportPaths?.value || "")
    .split(/\n|,|，/)
    .map((item) => item.trim())
    .filter(Boolean);
  const syncMode = el.obsidianAutoEnabled?.checked ? "auto" : "manual";
  return {
    endpoint: el.obsidianEndpoint?.value.trim() || "https://127.0.0.1:27124",
    api_key: el.obsidianApiKey?.value.trim() || "",
    import_query: el.obsidianImportQuery?.value.trim() || "",
    import_paths: paths,
    output_folder: el.obsidianOutputFolder?.value.trim() || "Court Shiguan",
    auto_enabled: Boolean(el.obsidianAutoEnabled?.checked),
    sync_mode: syncMode,
    verify_ssl: Boolean(el.obsidianVerifySsl?.checked),
    save_config: false,
  };
}

function renderObsidianSyncStatus(status = {}) {
  const config = status.config || {};
  const autosync = status.autosync || state.obsidianSync?.autosync || {};
  if (el.obsidianEndpoint) {
    el.obsidianEndpoint.value = config.endpoint || "https://127.0.0.1:27124";
  }
  if (el.obsidianApiKey) {
    el.obsidianApiKey.value = "";
    el.obsidianApiKey.placeholder = config.has_api_key ? "已保存；留空保留原密钥" : "Obsidian REST API key";
  }
  if (el.obsidianImportQuery) {
    el.obsidianImportQuery.value = config.import_query || "";
  }
  if (el.obsidianImportPaths) {
    el.obsidianImportPaths.value = Array.isArray(config.import_paths) ? config.import_paths.join("\n") : "";
  }
  if (el.obsidianOutputFolder) {
    el.obsidianOutputFolder.value = config.output_folder || "Court Shiguan";
  }
  if (el.obsidianVerifySsl) {
    el.obsidianVerifySsl.checked = Boolean(config.verify_ssl);
  }
  setObsidianMode(config.sync_mode === "auto" || config.auto_enabled ? "auto" : "manual");
  const prefix = status.ok ? "同步正常" : "同步异常";
  const message = status.message
    || (status.rest?.configured === false ? "REST 通道未配置（可选）" : "等待同步状态");
  const daemonState = autosync.status || autosync.mode || (autosync.ok ? "running" : "not running");
  const detail = [
    `权威库 ${truncate(config.source_vault_path || config.shared_shiguan_root || "", 68)}`,
    `缓存 ${truncate(config.cache_vault_path || config.vault_path || "", 68)}`,
    `autosync ${daemonState}${autosync.pid ? ` pid ${autosync.pid}` : ""}`,
  ].filter((item) => !item.endsWith(" "));
  if (el.obsidianSyncResult) {
    el.obsidianSyncResult.textContent = `${prefix}：${message}${detail.length ? `\n${detail.join("；")}` : ""}`;
    el.obsidianSyncResult.classList.toggle("warn", !status.ok);
  }
}

async function loadObsidianSyncStatus() {
  const status = await api("/api/obsidian-sync/status");
  renderObsidianSyncStatus(status);
  return status;
}

function chooseFiles(input) {
  if (!input || !("files" in input)) return false;
  input.value = "";
  if (typeof input.showPicker === "function") {
    input.showPicker();
  } else {
    input.click();
  }
  return true;
}

function setObsidianActionResult(message, warn = false) {
  if (!el.obsidianSyncResult) return;
  el.obsidianSyncResult.textContent = message;
  el.obsidianSyncResult.classList.toggle("warn", warn);
}

function setObsidianActionBusy(busy, action = "") {
  const labels = {
    save: "保存连接",
    test: "测试连接",
    preview: "预览导入",
    import: "同步导入",
    export: "REST 导出",
    filesystem: "文件同步",
  };
  for (const button of el.obsidianSyncForm?.querySelectorAll("button[value]") || []) {
    button.disabled = Boolean(busy);
  }
  if (busy) {
    setObsidianActionResult(`执行中：${labels[action] || action || "同步操作"}...`);
  }
}

async function importObsidianFiles(files) {
  const candidates = [...(files || [])].filter((file) => /\.(md|txt|zip)$/i.test(file.name || ""));
  if (!candidates.length) {
    setObsidianActionResult("请选择 .md、.txt 或 .zip 文件", true);
    setStatus("请选择 .md、.txt 或 .zip 文件", true);
    return;
  }
  try {
    const payloadFiles = [];
    for (const file of candidates) {
      if (/\.zip$/i.test(file.name || "")) {
        setObsidianActionResult("zip 文件仍需使用 Obsidian 同步 API 或本机路径导入；本轮未直接解包浏览器 zip。", true);
        setStatus("zip 文件仍需使用 Obsidian 同步 API 或本机路径导入；本轮未直接解包浏览器 zip。", true);
        continue;
      }
      payloadFiles.push({
        filename: file.name,
        text: await readLocalTextFile(file),
        source: `obsidian-file:${file.name}`,
      });
    }
    if (!payloadFiles.length) return;
    const data = await api("/api/import-text", {
      method: "POST",
      body: JSON.stringify({ files: payloadFiles, source_prefix: "obsidian-file" }),
    });
    await loadState();
    const queue = data.queue || {};
    setObsidianActionResult(`文件已进入待处理队列：新增 ${data.new || 0} 份；队列共 ${queue.pending_count || 0} 份。`);
    setStatus(`Obsidian 文件已进入待处理队列：新增 ${data.new || 0} 份；队列共 ${queue.pending_count || 0} 份，约 ${queue.estimated_tokens || 0} tokens。`);
  } catch (error) {
    setObsidianActionResult(`文件导入失败：${error.message}`, true);
    setStatus(`Obsidian 文件导入失败：${error.message}`, true);
  }
}

async function openObsidianSyncDialog() {
  try {
    await loadObsidianSyncStatus();
  } catch (error) {
    renderObsidianSyncStatus({ ok: false, message: error.message, config: state.obsidianSync?.config || {} });
  }
  if (!el.obsidianSyncDialog?.showModal || !el.obsidianSyncForm) {
    const endpoint = window.prompt("Obsidian REST API 地址", "https://127.0.0.1:27124");
    if (endpoint === null) return;
    const apiKey = window.prompt("Obsidian REST API key；留空保留原密钥", "");
    if (apiKey === null) return;
    await api("/api/obsidian-sync/config", {
      method: "POST",
      body: JSON.stringify({ endpoint, api_key: apiKey, sync_mode: "manual", save_config: true }),
    });
    setStatus("Obsidian 同步连接已保存");
    return;
  }
  return new Promise((resolve) => {
    let submittedAction = "";
    let actionBusy = false;
    const cleanup = () => {
      setObsidianActionBusy(false);
      el.obsidianSyncForm.removeEventListener("click", handleButtonClick, true);
      el.obsidianSyncForm.removeEventListener("submit", handleSubmit);
      el.obsidianSyncDialog.removeEventListener("cancel", handleCancel);
      el.obsidianSyncDialog.removeEventListener("close", handleClose);
    };
    const handleButtonClick = (event) => {
      if (actionBusy) {
        event.preventDefault();
        return;
      }
      const modeButton = event.target?.closest?.("#obsidianManualMode, #obsidianAutoMode");
      if (modeButton === el.obsidianManualMode) {
        event.preventDefault();
        setObsidianMode("manual");
        return;
      }
      if (modeButton === el.obsidianAutoMode) {
        event.preventDefault();
        setObsidianMode("auto");
        return;
      }
      const button = event.target?.closest?.("button[value]");
      if (button instanceof HTMLButtonElement && button.form === el.obsidianSyncForm) {
        submittedAction = button.value;
      }
    };
    const handleSubmit = async (event) => {
      event.preventDefault();
      const submitter = event.submitter;
      const action = submitter instanceof HTMLButtonElement ? submitter.value : submittedAction;
      submittedAction = "";
      if (actionBusy) return;
      if (!action || action === "close") {
        cleanup();
        el.obsidianSyncDialog.close("close");
        resolve(null);
        return;
      }
      if (action === "choose") {
        chooseFiles(el.obsidianFileInput);
        return;
      }
      const payload = obsidianConfigPayload();
      const persistedPayload = { ...payload, save_config: true };
      actionBusy = true;
      setObsidianActionBusy(true, action);
      try {
        if (action === "save") {
          await api("/api/obsidian-sync/config", { method: "POST", body: JSON.stringify(persistedPayload) });
          await loadObsidianSyncStatus();
          setStatus("Obsidian 同步配置已保存");
        } else if (action === "test") {
          await api("/api/obsidian-sync/config", { method: "POST", body: JSON.stringify(persistedPayload) });
          const status = await loadObsidianSyncStatus();
          const restOk = Boolean(status.rest?.ok);
          setStatus(restOk ? "Obsidian REST API 连接成功" : `Obsidian REST API 未连接：${status.rest?.message || status.message}`);
        } else if (action === "preview") {
          const preview = await api("/api/obsidian-sync/preview", { method: "POST", body: JSON.stringify(payload) });
          if (el.obsidianSyncResult) {
            const errorText = preview.errors?.length ? `；错误 ${preview.errors.length} 项` : "";
            el.obsidianSyncResult.textContent = `预览：${preview.found || 0} 份，约 ${preview.estimated_tokens || 0} tokens${errorText}`;
            el.obsidianSyncResult.classList.toggle("warn", Boolean(preview.errors?.length));
          }
          setStatus(`Obsidian 导入预览：${preview.found || 0} 份，约 ${preview.estimated_tokens || 0} tokens`);
        } else if (action === "import") {
          const data = await api("/api/obsidian-sync/import", { method: "POST", body: JSON.stringify(payload) });
          await loadState();
          const queue = data.queue?.queue || {};
          setObsidianActionResult(`同步导入完成：新增 ${data.queue?.new || 0} 份；队列共 ${queue.pending_count || 0} 份。`);
          setStatus(`Obsidian 同步导入已预处理入队：新增 ${data.queue?.new || 0} 份；队列共 ${queue.pending_count || 0} 份。`);
        } else if (action === "export") {
          const data = await api("/api/obsidian-sync/export", { method: "POST", body: JSON.stringify(payload) });
          setObsidianActionResult(`REST 导出完成：写入 ${data.written || 0} 个文件到 ${data.target_folder || "Court Shiguan"}。`);
          setStatus(`Obsidian REST 导出完成：写入 ${data.written || 0} 个文件到 ${data.target_folder || "Court Shiguan"}。`);
        } else if (action === "filesystem") {
          const data = await api("/api/obsidian-sync/filesystem", { method: "POST", body: JSON.stringify(payload) });
          await loadState();
          const result = data.filesystem_sync || {};
          const autosync = data.autosync || {};
          if (result.refresh_requested) {
            setObsidianActionResult("文件同步请求已提交；现有 autosync daemon 将在下一轮执行 preserve-only 同步。");
            setStatus("Obsidian 文件同步请求已提交；后台 daemon 将异步完成。", false);
            return;
          }
          const removed = result.removed || 0;
          const preserveText = result.preserve_only ? "preserve-only" : "非 preserve-only";
          setObsidianActionResult(`文件同步完成：${preserveText}，新增 ${result.copied || 0}，更新 ${result.updated || 0}，保留 ${result.preserved || 0}，删除 ${removed}。`, Boolean(removed));
          setStatus(`Obsidian autosync 单次循环完成：${preserveText}，新增 ${result.copied || 0}，更新 ${result.updated || 0}，保留 ${result.preserved || 0}，删除 ${removed}，回传入队 ${autosync.queued_count || 0}。`, Boolean(removed));
        }
      } catch (error) {
        if (el.obsidianSyncResult) {
          el.obsidianSyncResult.textContent = `执行失败：${error.message}`;
          el.obsidianSyncResult.classList.add("warn");
        }
        setStatus(`Obsidian 同步失败：${error.message}`, true);
      } finally {
        actionBusy = false;
        setObsidianActionBusy(false);
      }
    };
    const handleCancel = (event) => {
      if (actionBusy) {
        event.preventDefault();
        return;
      }
      cleanup();
      resolve(null);
    };
    const handleClose = () => {
      cleanup();
      resolve(null);
    };
    el.obsidianSyncForm.addEventListener("click", handleButtonClick, true);
    el.obsidianSyncForm.addEventListener("submit", handleSubmit);
    el.obsidianSyncDialog.addEventListener("cancel", handleCancel, { once: true });
    el.obsidianSyncDialog.addEventListener("close", handleClose, { once: true });
    try {
      el.obsidianSyncDialog.showModal();
    } catch (error) {
      cleanup();
      setStatus(`同步窗口打开失败：${error.message}`, true);
      resolve(null);
    }
  });
}

el.syncObsidianBtn?.addEventListener("click", openObsidianSyncDialog);

async function pushCurrentShiguanToObsidianRest() {
  try {
    el.obsidianRestPushBtn?.setAttribute("disabled", "disabled");
    setStatus("正在通过 Obsidian Local REST API 推送当前史馆导出；密钥只在服务端使用，不会显示在页面中...");
    const config = state.obsidianSync?.config || {};
    const data = await api("/api/obsidian-sync/export", {
      method: "POST",
      body: JSON.stringify({
        output_folder: config.output_folder || "Court Shiguan",
      }),
    });
    const errorText = data.errors?.length ? `；错误 ${data.errors.length} 项` : "";
    const truncatedText = data.truncated ? "；结果已截断" : "";
    setStatus(`REST 推送完成：写入 ${data.written || 0} 个文件到当前 Obsidian vault 的 ${data.target_folder || "Court Shiguan"}${errorText}${truncatedText}。`, Boolean(data.errors?.length || data.truncated));
    await loadState();
  } catch (error) {
    setStatus(`REST 推送失败：${error.message}`, true);
  } finally {
    el.obsidianRestPushBtn?.removeAttribute("disabled");
  }
}

el.obsidianRestPushBtn?.addEventListener("click", pushCurrentShiguanToObsidianRest);

async function importTextFiles(files) {
  const candidates = [...(files || [])].filter((file) => /\.(md|txt)$/i.test(file.name || ""));
  if (!candidates.length) {
    setStatus("请选择 .md 或 .txt 文件", true);
    return;
  }
  try {
    setStatus("读取 md/txt 文件...");
    const payloadFiles = [];
    for (const file of candidates) {
      payloadFiles.push({
        filename: file.name,
        text: await readLocalTextFile(file),
      });
    }
    const data = await api("/api/import-text", {
      method: "POST",
      body: JSON.stringify({ files: payloadFiles }),
    });
    await loadState();
    const queue = data.queue || {};
    const duplicateText = data.duplicate_count ? `，重复 ${data.duplicate_count} 份` : "";
    const skippedText = data.skipped_count ? `，跳过 ${data.skipped_count} 份` : "";
    setStatus(`已导入待处理材料 ${data.new || 0} 份${duplicateText}${skippedText}；队列共 ${queue.pending_count || 0} 份，约 ${queue.estimated_tokens || 0} tokens。`);
  } catch (error) {
    setStatus(`导入 md/txt 失败：${error.message}`, true);
  }
}

el.importTextBtn?.addEventListener("click", () => {
  if (el.textFileInput && "files" in el.textFileInput) {
    chooseFiles(el.textFileInput);
    return;
  }
  setStatus("此浏览器不支持文件选择；请用本机服务打开页面。", true);
});

function keyExpiryPayload(value) {
  if (value === "permanent") {
    return { days: 3650, permanent: true };
  }
  return { days: Math.max(1, Math.min(Number(value || 7), 3650)), permanent: false };
}

function keyShortRoleLabel(role) {
  return String(role || "read") === "edit" ? "编辑" : "只读";
}

function keyExpiryText(value) {
  const text = String(value || "");
  if (!text) return "永久";
  return text.replace("T", " ");
}

function pendingDownloadText(record = {}) {
  if (record.download_state === "consumed") return "已导出；再次获取需重新生成";
  if (record.download_state === "regenerate_required") return "临时导出材料不可用；需删除旧密钥后重新生成";
  if (!record.download_ready) return "未待导出";
  const expiresAt = record.download_expires_at ? `，下载保留至 ${keyExpiryText(record.download_expires_at)}` : "";
  return `待导出${expiresAt}`;
}

function promptKeyGenerateOptions() {
  const roleValue = window.prompt("生成密钥权限：输入“只读”或“编辑”", "只读");
  if (roleValue === null) return null;
  const role = /edit|编辑/i.test(roleValue) ? "edit" : "read";
  const preset = window.prompt(`${keyShortRoleLabel(role)}密钥有效期：1、7、30、90、365，或输入“永久”`, "7");
  if (preset === null) return null;
  const normalized = preset.trim().toLowerCase();
  const expiry = keyExpiryPayload(normalized === "永久" || normalized === "permanent" ? "permanent" : normalized);
  const host = window.prompt("分享主机地址；留空自动使用本机局域网地址", "");
  if (host === null) return null;
  const portText = window.prompt("分享端口；留空使用当前服务端口", "");
  if (portText === null) return null;
  return {
    ...expiry,
    role,
    host: host.trim(),
    port: portText.trim() ? Number(portText.trim()) : undefined,
  };
}

function keyGenerateOptions() {
  if (!el.keyGenerateDialog?.showModal || !el.keyGenerateForm) {
    return Promise.resolve(promptKeyGenerateOptions());
  }
  if (el.keyGenerateTitle) {
    el.keyGenerateTitle.textContent = "生成密钥";
  }
  if (el.keyGenerateHelp) {
    el.keyGenerateHelp.textContent = "生成后再点“导出密钥”下载 .shiguan-key 文件；服务端只保存校验摘要。";
  }
  if (el.keyRole) {
    el.keyRole.value = "read";
  }
  if (el.keyExpiryPreset) {
    el.keyExpiryPreset.value = "7";
  }
  if (el.keyShareHost) {
    el.keyShareHost.value = state.defaultShareHost || "";
  }
  if (el.keySharePort) {
    el.keySharePort.value = state.defaultSharePort || "";
  }
  return new Promise((resolve) => {
    let submittedAction = "";
    const cleanup = () => {
      el.keyGenerateForm.removeEventListener("click", handleButtonClick, true);
      el.keyGenerateForm.removeEventListener("submit", handleSubmit);
      el.keyGenerateDialog.removeEventListener("cancel", handleCancel);
      el.keyGenerateDialog.removeEventListener("close", handleClose);
    };
    const readOptions = () => {
      const expiry = keyExpiryPayload(el.keyExpiryPreset?.value || "7");
      const portText = el.keySharePort?.value.trim() || "";
      return {
        ...expiry,
        role: el.keyRole?.value === "edit" ? "edit" : "read",
        host: el.keyShareHost?.value.trim() || "",
        port: portText ? Number(portText) : undefined,
      };
    };
    const handleButtonClick = (event) => {
      const button = event.target?.closest?.("button[value]");
      if (button instanceof HTMLButtonElement && button.form === el.keyGenerateForm) {
        submittedAction = button.value;
      }
    };
    const handleSubmit = (event) => {
      event.preventDefault();
      const submitter = event.submitter;
      const action = submitter instanceof HTMLButtonElement ? submitter.value : submittedAction;
      cleanup();
      el.keyGenerateDialog.close(action || "cancel");
      resolve(action === "generate" ? readOptions() : null);
    };
    const handleCancel = () => {
      cleanup();
      resolve(null);
    };
    const handleClose = () => {
      cleanup();
      resolve(null);
    };
    el.keyGenerateForm.addEventListener("click", handleButtonClick, true);
    el.keyGenerateForm.addEventListener("submit", handleSubmit);
    el.keyGenerateDialog.addEventListener("cancel", handleCancel, { once: true });
    el.keyGenerateDialog.addEventListener("close", handleClose, { once: true });
    try {
      el.keyGenerateDialog.showModal();
    } catch (error) {
      cleanup();
      setStatus(`生成密钥窗口打开失败，已切换到简易输入：${error.message}`, true);
      resolve(promptKeyGenerateOptions());
    }
  });
}

async function generatePeerKey() {
  const options = await keyGenerateOptions();
  if (!options) return;
  try {
    const payload = {
      role: options.role,
      days: options.days,
      permanent: options.permanent,
      share_host: options.host,
      share_port: options.port,
    };
    const data = await api("/api/key/generate", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    await loadState();
    const key = data.key || {};
    setStatus(`已生成${keyShortRoleLabel(key.role)}密钥：${truncate(key.key_id, 20)}；请点击“导出密钥”下载文件。`);
  } catch (error) {
    setStatus(`密钥生成失败：${error.message}`, true);
  }
}

function latestPendingDownload(downloads = []) {
  return downloads
    .filter((item) => item?.key_id && item?.download_nonce && !item.downloaded_at)
    .slice()
    .sort((a, b) => String(b.created_at || "").localeCompare(String(a.created_at || "")))[0] || null;
}

function triggerDownload(url, filename = "") {
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.rel = "noopener";
  if (filename) {
    anchor.download = filename;
  }
  anchor.style.display = "none";
  document.body.append(anchor);
  anchor.click();
  window.setTimeout(() => anchor.remove(), 1000);
}

async function exportPendingKey() {
  try {
    const data = await api("/api/keys");
    const pending = latestPendingDownload(Array.isArray(data.pending_downloads) ? data.pending_downloads : []);
    if (!pending?.key_id || !pending?.download_nonce) {
      setStatus("没有可导出的临时密钥文件；服务重启、超时或一次下载后材料会被销毁。请删除或吊销未使用的旧密钥，再重新生成。", true);
      return;
    }
    const params = new URLSearchParams({
      key_id: pending.key_id,
      download_nonce: pending.download_nonce,
    });
    triggerDownload(`/api/key/export-file?${params.toString()}`, pending.filename || "shiguan-peer.shiguan-key");
    setStatus(`正在下载${keyShortRoleLabel(pending.role)}密钥文件：${pending.filename || pending.key_id}`);
  } catch (error) {
    setStatus(`密钥导出失败：${error.message}`, true);
  }
}

function renderKeyManageList(data = {}) {
  const keys = Array.isArray(data.issued_keys) ? data.issued_keys : [];
  if (el.keyManageSelect) {
    el.keyManageSelect.replaceChildren();
  }
  if (el.keyManageList) {
    el.keyManageList.replaceChildren();
  }
  if (!keys.length) {
    const empty = document.createElement("div");
    empty.className = "key-record empty";
    empty.textContent = "尚未生成密钥";
    el.keyManageList?.append(empty);
    return;
  }
  for (const key of keys) {
    const option = document.createElement("option");
    option.value = String(key.key_id || "");
    option.textContent = `${keyShortRoleLabel(key.role)} · ${truncate(key.key_id, 16)} · ${key.expired ? "已过期" : key.revoked ? "已吊销" : "有效"}`;
    el.keyManageSelect?.append(option);

    const item = document.createElement("article");
    item.className = "key-record";
    item.dataset.keyId = String(key.key_id || "");
    item.addEventListener("click", () => {
      if (el.keyManageSelect) {
        el.keyManageSelect.value = String(key.key_id || "");
      }
    });
    const title = document.createElement("strong");
    title.textContent = `${keyShortRoleLabel(key.role)}密钥`;
    const meta = document.createElement("div");
    meta.className = "key-record-meta";
    meta.textContent = [
      `ID ${key.key_id || ""}`,
      `端点 ${key.endpoint || "未记录"}`,
      `有效期 ${keyExpiryText(key.expires_at)}`,
      key.revoked ? "已吊销" : key.expired ? "已过期" : "有效",
      pendingDownloadText(key),
    ].filter(Boolean).join(" · ");
    item.append(title, meta);
    el.keyManageList?.append(item);
  }
}

async function openKeyManageDialog() {
  try {
    const data = await api("/api/keys");
    renderKeyManageList(data);
    if (!el.keyManageDialog?.showModal || !el.keyManageForm) {
      const keyId = window.prompt("输入要管理的 key_id", data.issued_keys?.[0]?.key_id || "");
      if (!keyId) return;
      const preset = window.prompt("续期天数：1、7、30、90、365，或输入“永久”；输入 delete 删除", "7");
      if (preset === null) return;
      const normalized = preset.trim().toLowerCase();
      const expiry = keyExpiryPayload(normalized === "永久" || normalized === "permanent" ? "permanent" : normalized);
      const action = normalized === "delete" || normalized === "删除" ? "delete" : (expiry.permanent ? "permanent" : "renew");
      await api("/api/key/manage", {
        method: "POST",
        body: JSON.stringify({ key_id: keyId.trim(), action, ...expiry }),
      });
      await loadState();
      setStatus("密钥状态已更新");
      return;
    }
    return new Promise((resolve) => {
      let submittedAction = "";
      const cleanup = () => {
        el.keyManageForm.removeEventListener("click", handleButtonClick, true);
        el.keyManageForm.removeEventListener("submit", handleSubmit);
        el.keyManageDialog.removeEventListener("cancel", handleCancel);
        el.keyManageDialog.removeEventListener("close", handleClose);
      };
      const handleButtonClick = (event) => {
        const button = event.target?.closest?.("button[value]");
        if (button instanceof HTMLButtonElement && button.form === el.keyManageForm) {
          submittedAction = button.value;
        }
      };
      const handleSubmit = async (event) => {
        event.preventDefault();
        const submitter = event.submitter;
        const action = submitter instanceof HTMLButtonElement ? submitter.value : submittedAction;
        cleanup();
        el.keyManageDialog.close(action || "close");
        if (!action || action === "close") {
          resolve(null);
          return;
        }
        const keyId = el.keyManageSelect?.value || "";
        if (!keyId) {
          setStatus("请先选择一枚密钥", true);
          resolve(null);
          return;
        }
        const expiry = keyExpiryPayload(el.keyManageExpiryPreset?.value || "7");
        try {
          const payload = { key_id: keyId, action, ...expiry };
          if (action === "permanent") {
            payload.permanent = true;
          }
          const result = await api("/api/key/manage", {
            method: "POST",
            body: JSON.stringify(payload),
          });
          await loadState();
          setStatus(`密钥状态已更新：${result.changed || 0} 项`);
        } catch (error) {
          setStatus(`密钥管理失败：${error.message}`, true);
        }
        resolve(null);
      };
      const handleCancel = () => {
        cleanup();
        resolve(null);
      };
      const handleClose = () => {
        cleanup();
        resolve(null);
      };
      el.keyManageForm.addEventListener("click", handleButtonClick, true);
      el.keyManageForm.addEventListener("submit", handleSubmit);
      el.keyManageDialog.addEventListener("cancel", handleCancel, { once: true });
      el.keyManageDialog.addEventListener("close", handleClose, { once: true });
      try {
        el.keyManageDialog.showModal();
      } catch (error) {
        cleanup();
        setStatus(`管理密钥窗口打开失败：${error.message}`, true);
        resolve(null);
      }
    });
  } catch (error) {
    setStatus(`密钥管理失败：${error.message}`, true);
  }
}

el.generateKeyBtn?.addEventListener("click", generatePeerKey);
el.exportKeyBtn?.addEventListener("click", exportPendingKey);
el.manageKeyBtn?.addEventListener("click", openKeyManageDialog);

function readLocalTextFile(file) {
  if (file?.text) {
    return file.text();
  }
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.addEventListener("load", () => resolve(String(reader.result || "")));
    reader.addEventListener("error", () => reject(reader.error || new Error("密钥文件读取失败")));
    reader.readAsText(file, "utf-8");
  });
}

async function importPeerKeyText(text, filename = "") {
  const keyText = String(text || "").trim();
  if (!keyText) {
    setStatus("密钥文件为空", true);
    return;
  }
  try {
    const data = await runAction("导入共享密钥", "/api/key/import", { key_text: keyText });
    setStatus(`已导入共享机器：${peerMachineName(data.peer || {})}；权限 ${peerRoleLabel(data.peer?.role)}`);
  } catch (error) {
    const source = filename ? `（${filename}）` : "";
    setStatus(`密钥导入失败${source}：${error.message}`, true);
  }
}

el.importKeyBtn?.addEventListener("click", async () => {
  if (el.keyFileInput && "files" in el.keyFileInput) {
    el.keyFileInput.value = "";
    el.keyFileInput.click();
    return;
  }
  const value = window.prompt("粘贴完整 .shiguan-key 文件内容", "");
  if (value) {
    await importPeerKeyText(value);
  }
});

el.keyFileInput?.addEventListener("change", async () => {
  const file = el.keyFileInput.files?.[0];
  if (!file) return;
  try {
    await importPeerKeyText(await readLocalTextFile(file), file.name);
  } catch (error) {
    setStatus(`密钥文件读取失败：${error.message}`, true);
  }
});

el.textFileInput?.addEventListener("change", async () => {
  await importTextFiles(el.textFileInput.files);
});

el.obsidianFileInput?.addEventListener("change", async () => {
  await importObsidianFiles(el.obsidianFileInput.files);
});

el.newBtn.addEventListener("click", newEntry);

el.editEntryBtn?.addEventListener("click", () => {
  setEditorEditing(!state.editorEditing);
});

el.rawSummaryToggle?.addEventListener("click", () => {
  if (state.showRawSummary) {
    syncRawSummaryFromDisplay();
  }
  state.showRawSummary = !state.showRawSummary;
  updateRawSummaryVisibility();
});

el.form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.editorEditing) {
    setStatus("当前为只读查看；请先开启“编辑”再保存。", true);
    return;
  }
  const peerBlockReason = entryEditBlockReason(state.currentEntry);
  if (peerBlockReason) {
    setEditorEditing(false);
    setStatus(peerBlockReason, true);
    return;
  }
  syncRawSummaryFromDisplay();
  try {
    setStatus("保存中...");
    const entry = formToEntry();
    let data;
    if (state.currentEntry?.peer_id) {
      data = await api("/api/peer/save", {
        method: "POST",
        body: JSON.stringify({
          peer_id: state.currentEntry.peer_id,
          entry: {
            ...entry,
            id: state.currentEntry.origin_id || state.currentEntry.id || entry.id,
            origin_id: state.currentEntry.origin_id || "",
          },
        }),
      });
    } else {
      data = await api("/api/entry", {
        method: "POST",
        body: JSON.stringify(entry),
      });
      state.selectedId = String(data.entry.id || "");
      state.selectedNode = `leaf:${state.selectedId}`;
    }
    await loadState();
    const savedEntry = data.entry || entry;
    if (!state.currentEntry?.peer_id) {
      fillForm(savedEntry);
    }
    setStatus(state.currentEntry?.peer_id ? "已保存到共享史馆并刷新" : "已保存并刷新生长树");
  } catch (error) {
    setStatus(`保存失败：${error.message}`, true);
  }
});

el.form.addEventListener("input", () => {
  if (!state.editorEditing) return;
  if (state.showRawSummary) {
    syncRawSummaryFromDisplay();
  }
  const entry = formToEntry();
  if (el.displaySummary && !state.showRawSummary) {
    el.displaySummary.value = displaySummaryZh(entry);
  }
  renderEntryProfile(entry);
});

let viewportFrame = 0;

function handleViewportChange() {
  if (viewportFrame) {
    cancelAnimationFrame(viewportFrame);
  }
  viewportFrame = requestAnimationFrame(() => {
    viewportFrame = 0;
    const limitChanged = syncDefaultGraphLimitForViewport();
    if (state.focusNode) {
      state.pendingFocusNode = state.focusNode;
    }
    if (limitChanged && location.protocol !== "file:") {
      loadState().catch((error) => setStatus(`载入失败：${error.message}`, true));
      return;
    }
    renderGraph();
  });
}

function watchMediaQuery(query) {
  if (!query) return;
  if (typeof query.addEventListener === "function") {
    query.addEventListener("change", handleViewportChange);
  } else if (typeof query.addListener === "function") {
    query.addListener(handleViewportChange);
  }
}

window.addEventListener("resize", handleViewportChange, { passive: true });
window.addEventListener("orientationchange", handleViewportChange);
watchMediaQuery(finePointerQuery);
watchMediaQuery(coarsePointerQuery);

applyTheme();
initializeControlledFields();
newEntry({ editing: false, focus: false });
updateColorModeControl();
syncFacetToggle();
updatePanelVisibility();
loadState().catch((error) => setStatus(`载入失败：${error.message}`, true));
