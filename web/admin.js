const profileListEl = document.getElementById("profileList");
const profileCountEl = document.getElementById("profileCount");
const newProfileBtn = document.getElementById("newProfileBtn");
const profileNameInput = document.getElementById("profileName");
const profileVersionInput = document.getElementById("profileVersion");
const modulesContainer = document.getElementById("modulesContainer");
const addModuleBtn = document.getElementById("addModuleBtn");
const saveProfileBtn = document.getElementById("saveProfileBtn");
const deleteProfileBtn = document.getElementById("deleteProfileBtn");
const adminNote = document.getElementById("adminNote");
const weightTip = document.getElementById("weightTip");
const editorHint = document.getElementById("editorHint");

let profiles = [];
let currentProfileId = null;
const LABEL_MAP = {
  SkillMatch: "技能匹配",
  ProjectExperience: "项目经验",
  YearsExperience: "工作年限",
  Education: "教育背景",
  Collaboration: "协作沟通",
  Stability: "稳定性",
};

function setNote(text, isError = false) {
  if (!adminNote) {
    return;
  }
  adminNote.textContent = text || "";
  adminNote.style.color = isError ? "#b42318" : "";
}

function setHint(text) {
  if (!editorHint) {
    return;
  }
  editorHint.textContent = text || "";
}

function createModuleRow(data = {}) {
  const row = document.createElement("div");
  row.className = "module-row";

  const nameInput = document.createElement("input");
  nameInput.className = "module-name";
  nameInput.placeholder = "ModuleName";
  nameInput.value = data.name || "";

  const labelInput = document.createElement("input");
  labelInput.className = "module-label";
  labelInput.placeholder = "显示名";
  const suggestedLabel =
    (data.label && data.label !== data.name && data.label) ||
    LABEL_MAP[data.name] ||
    data.label ||
    "";
  labelInput.value = suggestedLabel;

  const descInput = document.createElement("input");
  descInput.className = "module-desc";
  descInput.placeholder = "说明";
  descInput.value = data.desc || "";

  const weightInput = document.createElement("input");
  weightInput.className = "module-weight";
  weightInput.type = "number";
  weightInput.min = "0";
  weightInput.step = "0.01";
  weightInput.value =
    data.weight !== undefined && data.weight !== null ? data.weight : 0.1;

  const mustLabel = document.createElement("label");
  mustLabel.className = "module-check";
  const mustInput = document.createElement("input");
  mustInput.className = "module-must";
  mustInput.type = "checkbox";
  mustInput.checked = Boolean(data.must_have);
  const mustText = document.createElement("span");
  mustText.textContent = "必备";
  mustLabel.appendChild(mustInput);
  mustLabel.appendChild(mustText);

  const thresholdInput = document.createElement("input");
  thresholdInput.className = "module-threshold";
  thresholdInput.type = "number";
  thresholdInput.min = "0";
  thresholdInput.max = "100";
  thresholdInput.step = "1";
  thresholdInput.value =
    data.threshold !== undefined && data.threshold !== null ? data.threshold : "";

  const removeBtn = document.createElement("button");
  removeBtn.type = "button";
  removeBtn.className = "ghost small";
  removeBtn.textContent = "删除";
  removeBtn.addEventListener("click", () => {
    row.remove();
    updateWeightTip();
  });

  row.appendChild(nameInput);
  row.appendChild(labelInput);
  row.appendChild(descInput);
  row.appendChild(weightInput);
  row.appendChild(mustLabel);
  row.appendChild(thresholdInput);
  row.appendChild(removeBtn);

  nameInput.addEventListener("blur", () => {
    if (labelInput.value.trim()) {
      return;
    }
    const mapped = LABEL_MAP[nameInput.value.trim()];
    if (mapped) {
      labelInput.value = mapped;
    }
  });

  return row;
}

function renderModules(modules) {
  if (!modulesContainer) {
    return;
  }
  modulesContainer.innerHTML = "";
  if (!modules || !modules.length) {
    modulesContainer.appendChild(createModuleRow({ weight: 1 }));
  } else {
    modules.forEach((module) => {
      modulesContainer.appendChild(createModuleRow(module));
    });
  }
  updateWeightTip();
}

function getModulesFromForm() {
  const rows = Array.from(modulesContainer.querySelectorAll(".module-row"));
  const modules = [];
  let hasInvalid = false;
  rows.forEach((row) => {
    const name = row.querySelector(".module-name").value.trim();
    const label = row.querySelector(".module-label").value.trim();
    const desc = row.querySelector(".module-desc").value.trim();
    const weightValue = row.querySelector(".module-weight").value;
    const mustHave = row.querySelector(".module-must").checked;
    const thresholdValue = row.querySelector(".module-threshold").value;

    if (!name && !label && !desc && !weightValue) {
      return;
    }

    if (!name) {
      hasInvalid = true;
      return;
    }

    modules.push({
      name,
      label: label || name,
      desc,
      weight: weightValue === "" ? 0 : Number(weightValue),
      must_have: mustHave,
      threshold: thresholdValue === "" ? null : Number(thresholdValue),
    });
  });

  if (hasInvalid) {
    setNote("模块名不能为空。", true);
    return null;
  }

  return modules;
}

function updateWeightTip() {
  if (!modulesContainer || !weightTip) {
    return;
  }
  const rows = Array.from(modulesContainer.querySelectorAll(".module-row"));
  const total = rows.reduce((sum, row) => {
    const weightValue = row.querySelector(".module-weight").value;
    const weight = Number(weightValue);
    return sum + (Number.isFinite(weight) ? weight : 0);
  }, 0);
  weightTip.textContent = `权重合计：${total.toFixed(2)}（保存时会自动归一化）`;
}

async function loadProfiles() {
  setNote("");
  try {
    const res = await fetch("/api/score-profiles");
    if (!res.ok) {
      throw new Error("无法加载评分标准");
    }
    const data = await res.json();
    profiles = data.items || [];
    renderProfileList();
    if (profiles.length) {
      const exists = profiles.some((profile) => profile.id === currentProfileId);
      const targetId = exists ? currentProfileId : profiles[0].id;
      selectProfile(targetId);
    } else {
      currentProfileId = null;
      renderEmptyEditor();
    }
  } catch (err) {
    setNote(err.message || "无法加载评分标准", true);
  }
}

function renderProfileList() {
  if (!profileListEl) {
    return;
  }
  profileListEl.innerHTML = "";
  profiles.forEach((profile) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "profile-item";
    if (profile.id === currentProfileId) {
      button.classList.add("active");
    }
    button.textContent = profile.name || profile.id;
    button.addEventListener("click", () => selectProfile(profile.id));
    profileListEl.appendChild(button);
  });
  if (profileCountEl) {
    profileCountEl.textContent = `${profiles.length}`;
  }
}

function renderEmptyEditor() {
  if (profileNameInput) profileNameInput.value = "";
  if (profileVersionInput) profileVersionInput.value = "1";
  renderModules([{ weight: 1 }]);
  setHint("请先创建评分标准。");
  if (deleteProfileBtn) {
    deleteProfileBtn.disabled = true;
  }
}

function selectProfile(profileId) {
  currentProfileId = profileId;
  const profile = profiles.find((item) => item.id === profileId);
  if (!profile) {
    renderEmptyEditor();
    return;
  }
  if (profileNameInput) profileNameInput.value = profile.name || "";
  if (profileVersionInput)
    profileVersionInput.value = profile.version || 1;
  renderModules(profile.modules || []);
  setHint(profile.id === "default" ? "默认标准不可删除。" : "");
  if (deleteProfileBtn) {
    deleteProfileBtn.disabled = profile.id === "default";
  }
  renderProfileList();
}

async function saveProfile() {
  setNote("");
  const name = profileNameInput.value.trim();
  if (!name) {
    setNote("请输入标准名称。", true);
    return;
  }
  const versionRaw = profileVersionInput.value;
  const version = versionRaw ? Number(versionRaw) : 1;
  const modules = getModulesFromForm();
  if (!modules) {
    return;
  }
  if (!modules.length) {
    setNote("请至少填写一个模块。", true);
    return;
  }
  const payload = {
    name,
    version: Number.isFinite(version) ? Math.max(1, Math.floor(version)) : 1,
    modules,
    rules: [],
  };

  try {
    if (currentProfileId) {
      const current = profiles.find((item) => item.id === currentProfileId);
      if (current && Array.isArray(current.rules)) {
        payload.rules = current.rules;
      }
      const res = await fetch(`/api/score-profiles/${currentProfileId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || "保存失败");
      }
      setNote("已保存。");
    } else {
      const res = await fetch("/api/score-profiles", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || "保存失败");
      }
      const data = await res.json();
      currentProfileId = data.id;
      setNote("已创建。");
    }
    await loadProfiles();
  } catch (err) {
    setNote(err.message || "保存失败", true);
  }
}

async function deleteProfile() {
  if (!currentProfileId) {
    return;
  }
  if (currentProfileId === "default") {
    setNote("默认标准不可删除。", true);
    return;
  }
  const confirmed = window.confirm("确认删除当前评分标准吗？");
  if (!confirmed) {
    return;
  }
  try {
    const res = await fetch(`/api/score-profiles/${currentProfileId}`, {
      method: "DELETE",
    });
    if (!res.ok) {
      const data = await res.json();
      throw new Error(data.detail || "删除失败");
    }
    setNote("已删除。");
    currentProfileId = null;
    await loadProfiles();
  } catch (err) {
    setNote(err.message || "删除失败", true);
  }
}

newProfileBtn.addEventListener("click", () => {
  currentProfileId = null;
  renderProfileList();
  if (profileNameInput) profileNameInput.value = "";
  if (profileVersionInput) profileVersionInput.value = "1";
  renderModules([{ weight: 1 }]);
  setHint("新建评分标准");
  if (deleteProfileBtn) {
    deleteProfileBtn.disabled = true;
  }
});

addModuleBtn.addEventListener("click", () => {
  modulesContainer.appendChild(createModuleRow({ weight: 0.1 }));
  updateWeightTip();
});

saveProfileBtn.addEventListener("click", saveProfile);
deleteProfileBtn.addEventListener("click", deleteProfile);

modulesContainer.addEventListener("input", updateWeightTip);

loadProfiles();
