const jdInput = document.getElementById("jdInput");
const profileSelect = document.getElementById("profileSelect");
const fileInput = document.getElementById("fileInput");
const fileList = document.getElementById("fileList");
const uploadBtn = document.getElementById("uploadBtn");
const uploadNote = document.getElementById("uploadNote");
const dropzone = document.getElementById("dropzone");

const queuedCount = document.getElementById("queuedCount");
const processingCount = document.getElementById("processingCount");
const doneCount = document.getElementById("doneCount");
const errorCount = document.getElementById("errorCount");
const totalCount = document.getElementById("totalCount");
const jobIdValue = document.getElementById("jobIdValue");
const pollingState = document.getElementById("pollingState");
const resultsCount = document.getElementById("resultsCount");
const resultsHead = document.getElementById("resultsHead");
const resultsBody = document.getElementById("resultsBody");

const refreshBtn = document.getElementById("refreshBtn");
const exportExcelBtn = document.getElementById("exportExcelBtn");
const exportMdBtn = document.getElementById("exportMdBtn");

let selectedFiles = [];
let currentJobId = null;
let pollTimer = null;
let profiles = [];
const MAX_FILES = 100;
const MODULE_LABELS = {
  SkillMatch: "技能匹配",
  ProjectExperience: "项目经验",
  YearsExperience: "工作年限",
  Education: "教育背景",
  Collaboration: "协作沟通",
  Stability: "稳定性",
};
const BASE_HEADERS = ["姓名", "联系方式", "邮箱", "总分", "总评"];
const PROFILE_CACHE_KEY = "resume_profile_id";

function setNote(text, isError = false) {
  uploadNote.textContent = text;
  uploadNote.style.color = isError ? "#b42318" : "";
}

function renderFileList() {
  if (!selectedFiles.length) {
    fileList.textContent = "未选择文件。";
    return;
  }
  const names = selectedFiles.map((file) => file.name);
  fileList.innerHTML = names.map((name) => `<div>${name}</div>`).join("");
}

function handleFiles(files) {
  const incoming = Array.from(files || []).filter((file) =>
    file.name.toLowerCase().endsWith(".pdf")
  );
  if (incoming.length > MAX_FILES) {
    selectedFiles = incoming.slice(0, MAX_FILES);
    setNote(`仅保留前 ${MAX_FILES} 份 PDF。`, true);
  } else {
    selectedFiles = incoming;
    setNote("");
  }
  renderFileList();
}

function moduleName(module) {
  if (typeof module === "string") {
    return module;
  }
  return module && module.name ? module.name : "";
}

function moduleLabel(module) {
  if (typeof module === "string") {
    return MODULE_LABELS[module] || module;
  }
  const name = moduleName(module);
  const label = module && module.label ? module.label : "";
  if (label && label !== name) {
    return label;
  }
  return MODULE_LABELS[name] || label || name;
}

function renderProfileOptions() {
  if (!profileSelect) {
    return;
  }
  profileSelect.innerHTML = "";
  if (!profiles.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "暂无评分标准";
    profileSelect.appendChild(option);
    profileSelect.disabled = true;
    uploadBtn.disabled = true;
    setNote("请先在评分标准管理里创建评分标准。", true);
    return;
  }
  profiles.forEach((profile) => {
    const option = document.createElement("option");
    option.value = profile.id;
    option.textContent = profile.name || profile.id;
    profileSelect.appendChild(option);
  });
  profileSelect.disabled = false;
  uploadBtn.disabled = false;
  const saved = localStorage.getItem(PROFILE_CACHE_KEY);
  if (saved && profiles.some((profile) => profile.id === saved)) {
    profileSelect.value = saved;
  } else {
    profileSelect.value = profiles[0].id;
  }
}

async function loadProfiles() {
  if (!profileSelect) {
    return;
  }
  try {
    const res = await fetch("/api/score-profiles");
    if (!res.ok) {
      throw new Error("无法加载评分标准");
    }
    const data = await res.json();
    profiles = data.items || [];
    renderProfileOptions();
  } catch (err) {
    setNote(err.message || "无法加载评分标准", true);
  }
}

if (profileSelect) {
  profileSelect.addEventListener("change", () => {
    localStorage.setItem(PROFILE_CACHE_KEY, profileSelect.value);
  });
}

fileInput.addEventListener("change", (event) => {
  handleFiles(event.target.files);
});

dropzone.addEventListener("dragover", (event) => {
  event.preventDefault();
  dropzone.classList.add("dragover");
});

dropzone.addEventListener("dragleave", () => {
  dropzone.classList.remove("dragover");
});

dropzone.addEventListener("drop", (event) => {
  event.preventDefault();
  dropzone.classList.remove("dragover");
  handleFiles(event.dataTransfer.files);
});

async function upload() {
  const jd = jdInput.value.trim();
  if (!jd) {
    setNote("请填写 JD。", true);
    return;
  }
  if (profileSelect && !profileSelect.value) {
    setNote("请选择评分标准。", true);
    return;
  }
  if (!selectedFiles.length) {
    setNote("请选择 PDF 文件。", true);
    return;
  }

  setNote("正在上传...");
  const formData = new FormData();
  formData.append("jd", jd);
  if (profileSelect) {
    formData.append("profile_id", profileSelect.value);
  }
  selectedFiles.forEach((file) => formData.append("files", file));

  try {
    const res = await fetch("/api/upload", {
      method: "POST",
      body: formData,
    });
    if (!res.ok) {
      const data = await res.json();
      throw new Error(data.detail || "Upload failed.");
    }
    const data = await res.json();
    currentJobId = data.job_id;
    jobIdValue.textContent = currentJobId;
    setNote("已开始上传，正在评分。");
    startPolling();
  } catch (err) {
    setNote(err.message, true);
  }
}

uploadBtn.addEventListener("click", upload);
refreshBtn.addEventListener("click", () => {
  if (currentJobId) {
    fetchStatus();
    fetchResults();
  }
});

exportExcelBtn.addEventListener("click", () => {
  if (!currentJobId) {
    setNote("暂无可导出的任务。", true);
    return;
  }
  window.location.href = `/api/jobs/${currentJobId}/export.xlsx`;
});

exportMdBtn.addEventListener("click", () => {
  if (!currentJobId) {
    setNote("暂无可导出的任务。", true);
    return;
  }
  window.location.href = `/api/jobs/${currentJobId}/export.md`;
});

async function fetchStatus() {
  if (!currentJobId) {
    return;
  }
  const res = await fetch(`/api/jobs/${currentJobId}/status`);
  if (!res.ok) {
    return;
  }
  const data = await res.json();
  queuedCount.textContent = data.queued || 0;
  processingCount.textContent = data.processing || 0;
  doneCount.textContent = data.done || 0;
  errorCount.textContent = data.error || 0;
  totalCount.textContent = data.total || 0;

  if (data.total && data.done + data.error >= data.total) {
    stopPolling("Complete");
  }
}

function buildTableHeader(modules) {
  const headers = BASE_HEADERS.slice();
  modules.forEach((module) => {
    const label = moduleLabel(module);
    headers.push(`${label}分数`);
    headers.push(`${label}评价`);
  });

  resultsHead.innerHTML =
    "<tr>" + headers.map((h) => `<th>${h}</th>`).join("") + "</tr>";
}

function buildTableBody(items, modules) {
  const rows = items.map((item) => {
    const cells = [
      item.name || "",
      item.phone || "",
      item.email || "",
      item.total_score == null ? "" : item.total_score.toFixed(1),
      item.summary || "",
    ];

    const moduleMap = {};
    (item.modules || []).forEach((m) => {
      moduleMap[m.name] = m;
    });

    modules.forEach((module) => {
      const name = moduleName(module);
      const mod = moduleMap[name] || {};
      const score = mod.score == null ? "" : Number(mod.score).toFixed(1);
      cells.push(score);
      cells.push(mod.comment || "");
    });

    return "<tr>" + cells.map((c) => `<td>${c}</td>`).join("") + "</tr>";
  });
  resultsBody.innerHTML = rows.join("");
  resultsCount.textContent = `${items.length} 条`;
}

async function fetchResults() {
  if (!currentJobId) {
    return;
  }
  const res = await fetch(`/api/jobs/${currentJobId}/results`);
  if (!res.ok) {
    return;
  }
  const data = await res.json();
  buildTableHeader(data.modules || []);
  buildTableBody(data.items || [], data.modules || []);
}

function startPolling() {
  stopPolling("进行中");
  pollingState.textContent = "进行中";
  pollTimer = setInterval(async () => {
    await fetchStatus();
    await fetchResults();
  }, 4000);
}

function stopPolling(state) {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
  pollingState.textContent = state || "空闲";
}

renderFileList();
loadProfiles();
