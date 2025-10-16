const clientSelect = document.getElementById("client");
const dateInput = document.getElementById("target-date");
const pickDateButton = document.getElementById("pick-date-btn");
const passwordOutput = document.getElementById("password-output");
const statusEl = document.getElementById("status");
const customField = document.getElementById("custom-field");
const customInput = document.getElementById("custom-input");
const generateButton = document.getElementById("generate-btn");
const copyButton = document.getElementById("copy-btn");
const clearButton = document.getElementById("clear-btn");
const adminForm = document.getElementById("admin-form");
const adminClientNameInput = document.getElementById("admin-client-name");
const adminClientPrefixInput = document.getElementById("admin-client-prefix");
const adminPasswordInput = document.getElementById("admin-password");
const adminMessage = document.getElementById("admin-message");
const adminClientList = document.getElementById("admin-client-list");
const adminClientIdInput = document.getElementById("admin-client-id");
const adminSuffixRuleInput = document.getElementById("admin-client-suffix");
const adminCreateBtn = document.getElementById("admin-create-btn");
const adminUpdateBtn = document.getElementById("admin-update-btn");
const adminDeleteBtn = document.getElementById("admin-delete-btn");
const adminResetBtn = document.getElementById("admin-reset-btn");
const zipForm = document.getElementById("zip-form");
const zipFilesInput = document.getElementById("zip-files");
const zipBrowseBtn = document.getElementById("zip-browse-btn");
const zipFileList = document.getElementById("zip-file-list");
const zipNameInput = document.getElementById("zip-name");
const zipPasswordInput = document.getElementById("zip-password");
const zipModeSelect = document.getElementById("zip-mode");
const zipOsSelect = document.getElementById("zip-os-hint");
const zipAlgoHint = document.getElementById("zip-algo-hint");
const zipOsHintText = document.getElementById("zip-os-hint-text");
const zipGenerateBtn = document.getElementById("zip-generate-btn");
const zipClearBtn = document.getElementById("zip-clear-btn");
const zipStatus = document.getElementById("zip-status");
const zipDropZone = document.getElementById("zip-drop-zone");

const CUSTOM_CLIENT_KEY = "custom";
const DEFAULT_SUFFIX_RULE = "日付（月と日）";
let cachedClients = [];
let selectedAdminClientId = "";
let selectedAdminClient = null;
const ZIP_SIZE_LIMIT = 512 * 1024 * 1024; // 512MB

async function fetchClients() {
  try {
    const response = await fetch("/api/clients", {
      headers: {
        Accept: "application/json",
      },
    });
    if (response.status === 401) {
      window.location.href = "/login";
      return;
    }
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const data = await response.json();
    cachedClients = data.clients ?? [];
    populateClients(cachedClients);
    if (data.fallback && statusEl) {
      statusEl.textContent =
        "Supabase に接続できなかったため、ローカルの既定クライアントを表示しています。";
      statusEl.dataset.state = "warning";
    }
  } catch (error) {
    console.error("Failed to load clients", error);
    clientSelect.innerHTML =
      '<option value="" disabled selected>クライアント取得失敗</option>';
    statusEl.textContent = "取引先の読み込みに失敗しました。再読み込みしてください。";
  }
}

function populateClients(clients) {
  const previousSelection = clientSelect.value;

  if (!clients.length) {
    clientSelect.innerHTML =
      '<option value="" disabled selected>未登録</option>';
    statusEl.textContent = "使用可能なクライアントが登録されていません。";
    renderAdminClientList([]);
    resetAdminForm({ keepPassword: true, suppressMessage: true });
    return;
  }

  const seenKeys = new Set(clients.map((client) => client.key));
  if (!seenKeys.has(CUSTOM_CLIENT_KEY)) {
    clients = [
      ...clients,
      {
        key: CUSTOM_CLIENT_KEY,
        label: "Custom（自由入力）",
        rule: "自由入力 + 任意の日付(YYYYMMDD)",
      },
    ];
  }

  clientSelect.innerHTML =
    '<option value="" disabled selected>クライアントを選択</option>';
  for (const client of clients) {
    const option = document.createElement("option");
    option.value = client.key;
    if (client.rule) {
      option.textContent = `${client.label}（${client.rule}）`;
    } else {
      option.textContent = client.label;
    }
    clientSelect.appendChild(option);
  }

  const availableKeys = new Set(clients.map((client) => client.key));
  if (availableKeys.has(previousSelection)) {
      clientSelect.value = previousSelection;
  } else {
    clientSelect.selectedIndex = 0;
  }
  toggleCustomField();
  renderAdminClientList(cachedClients);
  syncSelectedAdminClient();
}

function resetDateToToday({ silent = false } = {}) {
  const today = new Date();
  const iso = today.toISOString().split("T")[0];
  dateInput.value = iso;
  if (!silent) {
    statusEl.textContent = "日付を本日にリセットしました。";
    statusEl.dataset.state = "info";
  }
}

function openDatePicker() {
  if (typeof dateInput.showPicker === "function") {
    dateInput.showPicker();
    return;
  }
  dateInput.focus();
  statusEl.textContent = "日付欄をクリックして変更してください。";
  statusEl.dataset.state = "info";
}

function toggleCustomField() {
  const isCustom = clientSelect.value === CUSTOM_CLIENT_KEY;
  customField.hidden = !isCustom;
  if (!isCustom) {
    customInput.value = "";
  } else {
    customInput.focus();
  }

  if (!clientSelect.value) {
    passwordOutput.textContent = "------";
    statusEl.textContent = "クライアントを選択してください。";
    statusEl.dataset.state = "info";
  } else {
    passwordOutput.textContent = "------";
    statusEl.textContent = "生成ボタンを押してパスワードを作成してください。";
    statusEl.dataset.state = "info";
  }
}

async function triggerGeneration() {
  const clientKey = clientSelect.value;
  const targetDate = dateInput.value;
  const isCustom = clientKey === CUSTOM_CLIENT_KEY;
  const customValue = customInput.value;
  const trimmedCustomValue = customValue.trim();

  if (!clientKey) {
    passwordOutput.textContent = "------";
    statusEl.textContent = "クライアントを選択してください。";
    return;
  }

  if (isCustom && !trimmedCustomValue) {
    passwordOutput.textContent = "------";
    statusEl.textContent = "自由入力のテキストを入力してください。";
    statusEl.dataset.state = "warning";
    return;
  }

  if (isCustom) {
    const compactDate = targetDate ? targetDate.replaceAll("-", "") : "";
    const localPassword = `${trimmedCustomValue}${compactDate}`;
    passwordOutput.textContent = localPassword;
    statusEl.textContent = targetDate
      ? `生成日: ${targetDate}`
      : "生成しました。";
    statusEl.dataset.state = "success";
    return;
  }

  try {
    statusEl.textContent = "生成中...";
    const response = await fetch("/api/generate", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({
        clientKey,
        date: targetDate || null,
        customInput: isCustom ? trimmedCustomValue : undefined,
      }),
    });
    if (response.status === 401) {
      window.location.href = "/login";
      return;
    }

    const result = await response.json();
    if (!response.ok) {
      throw new Error(result.error || "生成に失敗しました。");
    }

    passwordOutput.textContent = result.password;
    statusEl.textContent = result.date ? `生成日: ${result.date}` : "生成しました。";
    statusEl.dataset.state = "success";
  } catch (error) {
    console.error(error);
    passwordOutput.textContent = "------";
    statusEl.textContent = error.message;
    statusEl.dataset.state = "error";
  }
}

async function copyPassword() {
  const value = passwordOutput.textContent;
  if (!value || value === "------") {
    statusEl.textContent = "コピーするパスワードがありません。";
    statusEl.dataset.state = "warning";
    return;
  }

  try {
    await navigator.clipboard.writeText(value);
    statusEl.textContent = "クリップボードにコピーしました。";
    statusEl.dataset.state = "success";
  } catch (error) {
    console.error(error);
    statusEl.textContent =
      "コピーに失敗しました。手動で選択してコピーしてください。";
    statusEl.dataset.state = "error";
  }
}

function clearForm() {
  clientSelect.selectedIndex = 0;
  toggleCustomField();
  customInput.value = "";
  resetDateToToday({ silent: true });
  passwordOutput.textContent = "------";
  statusEl.textContent = "";
  delete statusEl.dataset.state;
}

function renderAdminClientList(clients) {
  if (!adminClientList) return;

  adminClientList.innerHTML = "";
  const realClients = clients.filter(
    (client) => client.key && client.key !== CUSTOM_CLIENT_KEY
  );

  if (!realClients.length) {
    const emptyItem = document.createElement("li");
    emptyItem.textContent = "登録されているルールがありません。";
    adminClientList.appendChild(emptyItem);
    return;
  }

  for (const client of realClients) {
    const item = document.createElement("li");
    const label = client.label || client.name || client.key;
    const prefix = client.prefix || "";
    const suffixRule = client.suffix_rule || client.suffixRule || DEFAULT_SUFFIX_RULE;
    item.classList.add("admin-list__item");
    item.dataset.key = client.key;
    if (client.key === selectedAdminClientId) {
      item.classList.add("is-selected");
    }

    const selectButton = document.createElement("button");
    selectButton.type = "button";
    selectButton.classList.add("admin-list__select");
    selectButton.dataset.key = client.key;

    const info = document.createElement("span");
    info.classList.add("admin-list__label");
    info.textContent = label;

    const rule = document.createElement("span");
    rule.classList.add("admin-list__rule");
    rule.textContent = `${prefix} + ${suffixRule}`;

    selectButton.appendChild(info);
    selectButton.appendChild(rule);
    item.appendChild(selectButton);
    adminClientList.appendChild(item);
  }
}

function setAdminMessage(message, state) {
  if (!adminMessage) return;
  adminMessage.textContent = message;
  if (state) {
    adminMessage.dataset.state = state;
  } else {
    delete adminMessage.dataset.state;
  }
}

function updateAdminControlsState() {
  const hasSelection = Boolean(selectedAdminClientId);
  if (adminUpdateBtn) {
    adminUpdateBtn.disabled = !hasSelection;
  }
  if (adminDeleteBtn) {
    adminDeleteBtn.disabled = !hasSelection;
  }
}

function getAdminFormValues() {
  const keyValue =
    (adminClientIdInput?.value || selectedAdminClientId || "").trim();
  return {
    key: keyValue,
    name: adminClientNameInput?.value.trim() || "",
    prefix: adminClientPrefixInput?.value.trim() || "",
    suffixRule: adminSuffixRuleInput?.value.trim() || "",
    adminPassword: adminPasswordInput?.value || "",
  };
}

function resetAdminForm({
  keepPassword = false,
  suppressMessage = false,
} = {}) {
  selectedAdminClientId = "";
  selectedAdminClient = null;
  if (adminClientIdInput) adminClientIdInput.value = "";
  if (adminClientNameInput) adminClientNameInput.value = "";
  if (adminClientPrefixInput) adminClientPrefixInput.value = "";
  if (adminSuffixRuleInput) adminSuffixRuleInput.value = DEFAULT_SUFFIX_RULE;
  if (!keepPassword && adminPasswordInput) {
    adminPasswordInput.value = "";
  }
  if (!suppressMessage) {
    setAdminMessage("", null);
  }
  renderAdminClientList(cachedClients);
  updateAdminControlsState();
}

function syncSelectedAdminClient() {
  if (!selectedAdminClientId) {
    updateAdminControlsState();
    if (adminClientIdInput) adminClientIdInput.value = "";
    return;
  }

  const match = cachedClients.find(
    (client) => client.key === selectedAdminClientId
  );
  if (!match) {
    resetAdminForm({ keepPassword: true, suppressMessage: true });
    return;
  }

  selectedAdminClient = match;
  if (adminClientIdInput) adminClientIdInput.value = match.key || "";
  if (adminClientNameInput && !adminClientNameInput.matches(":focus")) {
    adminClientNameInput.value = match.label || match.name || "";
  }
  if (adminClientPrefixInput && !adminClientPrefixInput.matches(":focus")) {
    adminClientPrefixInput.value = match.prefix || "";
  }
  if (adminSuffixRuleInput && !adminSuffixRuleInput.matches(":focus")) {
    adminSuffixRuleInput.value =
      match.suffix_rule || match.suffixRule || DEFAULT_SUFFIX_RULE;
  }
  updateAdminControlsState();
}

function selectAdminClient(key) {
  if (!key) return;
  const match = cachedClients.find((client) => client.key === key);
  if (!match) {
    setAdminMessage("選択したクライアントが見つかりません。", "error");
    return;
  }

  selectedAdminClientId = match.key;
  selectedAdminClient = match;
  if (adminClientIdInput) adminClientIdInput.value = match.key || "";
  if (adminClientNameInput) {
    adminClientNameInput.value = match.label || match.name || "";
  }
  if (adminClientPrefixInput) {
    adminClientPrefixInput.value = match.prefix || "";
  }
  if (adminSuffixRuleInput) {
    adminSuffixRuleInput.value =
      match.suffix_rule || match.suffixRule || DEFAULT_SUFFIX_RULE;
  }
  renderAdminClientList(cachedClients);
  updateAdminControlsState();
  setAdminMessage(`${match.label || match.name} を編集中です。`, "info");
}

async function submitAdminUpdate() {
  const { key, name, prefix, suffixRule, adminPassword } =
    getAdminFormValues();

  if (!key) {
    setAdminMessage("上書き対象を選択してください。", "error");
    return;
  }

  if (!name || !prefix) {
    setAdminMessage("クライアント名と接頭語を入力してください。", "error");
    return;
  }

  if (!adminPassword) {
    setAdminMessage("管理者パスワードを入力してください。", "error");
    return;
  }

  setAdminMessage("更新しています...", "info");

  try {
    const response = await fetch("/api/update_client", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({
        key,
        name,
        prefix,
        suffix_rule: suffixRule,
        admin_password: adminPassword,
      }),
    });
    const result = await response.json().catch(() => ({}));
    if (response.status === 401) {
      window.location.href = "/login";
      return;
    }
    if (response.status === 403) {
      setAdminMessage(result.error || "認証に失敗しました。", "error");
      return;
    }
    if (!response.ok) {
      throw new Error(result.error || "更新に失敗しました。");
    }

    selectedAdminClientId = result.client?.key || key;
    setAdminMessage(result.message || "更新しました。", "success");
    await fetchClients();
    syncSelectedAdminClient();
  } catch (error) {
    console.error("Failed to update client", error);
    setAdminMessage(error.message || "クライアントの更新に失敗しました。", "error");
  }
}

async function submitAdminDelete() {
  const { key, adminPassword } = getAdminFormValues();
  if (!key) {
    setAdminMessage("削除対象を選択してください。", "error");
    return;
  }
  if (!adminPassword) {
    setAdminMessage("削除には管理者パスワードが必要です。", "error");
    return;
  }

  const target = cachedClients.find((client) => client.key === key);
  const targetLabel = target?.label || target?.name || "選択中のクライアント";
  const confirmed = window.confirm(`${targetLabel} を本当に削除しますか？`);
  if (!confirmed) {
    return;
  }

  setAdminMessage("削除しています...", "info");

  try {
    const response = await fetch("/api/delete_client", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({
        key,
        admin_password: adminPassword,
      }),
    });
    const result = await response.json().catch(() => ({}));
    if (response.status === 401) {
      window.location.href = "/login";
      return;
    }
    if (response.status === 403) {
      setAdminMessage(result.error || "認証に失敗しました。", "error");
      return;
    }
    if (!response.ok) {
      throw new Error(result.error || "削除に失敗しました。");
    }

    setAdminMessage(result.message || `${targetLabel} を削除しました。`, "success");
    resetAdminForm({ keepPassword: true, suppressMessage: true });
    await fetchClients();
    setAdminMessage(result.message || `${targetLabel} を削除しました。`, "success");
  } catch (error) {
    console.error("Failed to delete client", error);
    setAdminMessage(error.message || "クライアントの削除に失敗しました。", "error");
  }
}

function formatBytes(bytes) {
  if (!Number.isFinite(bytes) || bytes <= 0) {
    return "0 B";
  }
  const units = ["B", "KB", "MB", "GB", "TB"];
  const index = Math.min(
    Math.floor(Math.log10(bytes) / Math.log10(1024)),
    units.length - 1
  );
  const value = bytes / 1024 ** index;
  return `${value.toFixed(value >= 100 || index === 0 ? 0 : value >= 10 ? 1 : 2)} ${
    units[index]
  }`;
}

function setZipStatus(message, state) {
  if (!zipStatus) return;
  zipStatus.textContent = message;
  if (state) {
    zipStatus.dataset.state = state;
  } else {
    delete zipStatus.dataset.state;
  }
}

function updateZipFileList() {
  if (!zipFileList || !zipFilesInput) return;

  zipFileList.innerHTML = "";
  const files = Array.from(zipFilesInput.files || []);
  let totalSize = 0;

  if (!files.length) {
    const emptyItem = document.createElement("li");
    emptyItem.textContent = "ファイルが選択されていません。";
    zipFileList.appendChild(emptyItem);
  } else {
    for (const file of files) {
      totalSize += file.size;
      const item = document.createElement("li");
      item.textContent = `${file.name} (${formatBytes(file.size)})`;
      zipFileList.appendChild(item);
    }
    const totalItem = document.createElement("li");
    totalItem.classList.add("zip-file-list__total");
    totalItem.textContent = `合計: ${formatBytes(totalSize)}`;
    zipFileList.appendChild(totalItem);
  }

  if (totalSize > ZIP_SIZE_LIMIT) {
    setZipStatus(
      `アップロード合計サイズが上限(${formatBytes(
        ZIP_SIZE_LIMIT
      )})を超えています。`,
      "warning"
    );
  } else if (!zipStatus.textContent) {
    setZipStatus("必要項目を入力するとZIP生成が可能になります。", "info");
  }

  updateZipGenerateState();
}

function updateZipGenerateState() {
  if (!zipGenerateBtn) return;
  const hasFiles = zipFilesInput && zipFilesInput.files && zipFilesInput.files.length;
  const password = zipPasswordInput?.value || "";
  const totalSize = Array.from(zipFilesInput?.files || []).reduce(
    (acc, file) => acc + file.size,
    0
  );

  const canGenerate =
    Boolean(hasFiles) &&
    password.length > 0 &&
    totalSize <= ZIP_SIZE_LIMIT;

  zipGenerateBtn.disabled = !canGenerate;
}

function updateZipHints() {
  if (!zipAlgoHint || !zipModeSelect) return;

  const mode = zipModeSelect.value || "aes";
  const os = zipOsSelect?.value || "windows";

  if (mode === "aes") {
    zipAlgoHint.textContent =
      "AESで暗号化します。Windows標準のエクスプローラーでは解凍できないため、7-Zip（推奨）またはWinZipをご利用ください。";
    zipAlgoHint.dataset.state = "success";
  } else {
    zipAlgoHint.textContent =
      "ZipCryptoは互換性重視の方式です。暗号強度は低いため重要情報にはAESを推奨します。";
    zipAlgoHint.dataset.state = "warning";
  }

  if (zipOsHintText) {
    if (os === "windows") {
      if (mode === "aes") {
        zipOsHintText.textContent =
          "WindowsでAES暗号ZIPを開くには7-Zipなどの専用ソフトが必要です。";
        zipOsHintText.dataset.state = "warning";
      } else {
        zipOsHintText.textContent =
          "ZipCryptoはWindowsエクスプローラーで展開できますが、安全性は高くありません。";
        zipOsHintText.dataset.state = "warning";
      }
    } else {
      if (mode === "aes") {
        zipOsHintText.textContent =
          "macOS FinderはAES暗号ZIPに概ね対応していますが、最新環境での利用を推奨します。";
        zipOsHintText.dataset.state = "info";
      } else {
        zipOsHintText.textContent =
          "macOS FinderでもZipCryptoは利用可能ですが、暗号強度は低い点に注意してください。";
        zipOsHintText.dataset.state = "info";
      }
    }
  }
}

function clearZipForm() {
  if (!zipForm) return;
  zipForm.reset();
  if (zipFilesInput) {
    zipFilesInput.value = "";
  }
  if (zipFileList) {
    zipFileList.innerHTML = "";
  }
  updateZipFileList();
  updateZipHints();
  setZipStatus("", null);
  if (zipDropZone) {
    zipDropZone.classList.remove("is-dragover");
  }
}

async function submitZipForm(event) {
  event.preventDefault();
  if (!zipGenerateBtn) return;

  updateZipGenerateState();
  if (zipGenerateBtn.disabled) {
    setZipStatus(
      "必須入力が不足しています。ファイルとパスワードを確認してください。",
      "error"
    );
    return;
  }

  setZipStatus("ZIPを生成しています...", "info");
  zipGenerateBtn.disabled = true;

  try {
    const formData = new FormData();
    const files = Array.from(zipFilesInput?.files || []);
    for (const file of files) {
      formData.append("files", file);
    }
    formData.append("zip_name", (zipNameInput?.value || "").trim());
    formData.append("password", zipPasswordInput?.value || "");
    formData.append("mode", zipModeSelect?.value || "aes");

    const response = await fetch("/api/zip", {
      method: "POST",
      body: formData,
    });
    if (response.status === 401) {
      window.location.href = "/login";
      return;
    }

    const contentType = response.headers.get("content-type") || "";
    if (contentType.includes("application/zip")) {
      const blob = await response.blob();
      let downloadName = (zipNameInput?.value || "").trim();
      if (!downloadName) {
        downloadName = `monozip_${new Date()
          .toISOString()
          .replace(/[-:T]/g, "")
          .slice(0, 14)}`;
      }
      if (!downloadName.toLowerCase().endsWith(".zip")) {
        downloadName = `${downloadName}.zip`;
      }

      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = downloadName;
      document.body.appendChild(anchor);
      anchor.click();
      document.body.removeChild(anchor);
      setTimeout(() => URL.revokeObjectURL(url), 1000);

      setZipStatus("ZIPファイルをダウンロードしました。", "success");
    } else {
      let result;
      try {
        result = await response.json();
      } catch {
        throw new Error("不明なエラーが発生しました。");
      }

      const state = response.status === 413 ? "warning" : "error";
      setZipStatus(result.error || "ZIPの生成に失敗しました。", state);
    }
  } catch (error) {
    console.error("Failed to create zip", error);
    setZipStatus(error.message || "ZIP生成中にエラーが発生しました。", "error");
  } finally {
    updateZipGenerateState();
  }
}

async function submitAdminForm(event) {
  event.preventDefault();

  const { name, prefix, suffixRule, adminPassword } = getAdminFormValues();

  if (!name || !prefix || !adminPassword) {
    setAdminMessage("全ての項目を入力してください。", "error");
    return;
  }

  setAdminMessage("登録中です...", "info");

  try {
    const response = await fetch("/api/add_client", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({
        name,
        prefix,
        suffix_rule: suffixRule,
        admin_password: adminPassword,
      }),
    });
    const result = await response.json().catch(() => ({}));
    if (response.status === 401) {
      window.location.href = "/login";
      return;
    }
    if (response.status === 403) {
      setAdminMessage(result.error || "認証に失敗しました。", "error");
      return;
    }
    if (!response.ok) {
      throw new Error(result.error || "追加に失敗しました。");
    }

    const state = result.success ? "success" : "warning";
    setAdminMessage(result.message || "処理が完了しました。", state);

    if (result.client?.key) {
      selectedAdminClientId = result.client.key;
    }
    if (result.success) {
      if (adminClientNameInput) adminClientNameInput.value = "";
      if (adminClientPrefixInput) adminClientPrefixInput.value = "";
      if (adminSuffixRuleInput) adminSuffixRuleInput.value = DEFAULT_SUFFIX_RULE;
    }
    await fetchClients();
    if (selectedAdminClientId) {
      syncSelectedAdminClient();
    } else {
      updateAdminControlsState();
    }
  } catch (error) {
    console.error("Failed to add client", error);
    setAdminMessage(error.message, "error");
  }
}

document.addEventListener("DOMContentLoaded", () => {
  fetchClients().then(() => resetDateToToday({ silent: true }));

  clientSelect.addEventListener("change", () => {
    toggleCustomField();
  });
  dateInput.addEventListener("change", () => {
    statusEl.textContent = "日付を変更しました。生成ボタンを押してください。";
    statusEl.dataset.state = "info";
    passwordOutput.textContent = "------";
  });
  pickDateButton.addEventListener("click", openDatePicker);
  generateButton.addEventListener("click", triggerGeneration);
  copyButton.addEventListener("click", copyPassword);
  clearButton.addEventListener("click", clearForm);
  customInput.addEventListener("input", () => {
    if (clientSelect.value === CUSTOM_CLIENT_KEY) {
      statusEl.textContent = "生成ボタンを押してパスワードを作成してください。";
      statusEl.dataset.state = "info";
      passwordOutput.textContent = "------";
    }
  });
  if (adminSuffixRuleInput && !adminSuffixRuleInput.value) {
    adminSuffixRuleInput.value = DEFAULT_SUFFIX_RULE;
  }
  updateAdminControlsState();
  if (adminForm) {
    adminForm.addEventListener("submit", submitAdminForm);
  }
  if (adminUpdateBtn) {
    adminUpdateBtn.addEventListener("click", submitAdminUpdate);
  }
  if (adminDeleteBtn) {
    adminDeleteBtn.addEventListener("click", submitAdminDelete);
  }
  if (adminResetBtn) {
    adminResetBtn.addEventListener("click", () =>
      resetAdminForm({ keepPassword: true })
    );
  }
  if (adminClientList) {
    adminClientList.addEventListener("click", (event) => {
      const target = event.target;
      if (!(target instanceof HTMLElement)) return;
      const button = target.closest(".admin-list__select");
      if (button instanceof HTMLElement) {
        const key = button.dataset.key;
        selectAdminClient(key || "");
      }
    });
  }
  document.querySelectorAll(".password-toggle").forEach((button) => {
    button.addEventListener("click", () => {
      const targetId = button.dataset.target;
      if (!targetId) return;
      const input = document.getElementById(targetId);
      if (!input) return;
      if (input.type === "password") {
        input.type = "text";
        button.textContent = "非表示";
      } else {
        input.type = "password";
        button.textContent = "表示";
      }
      input.focus();
    });
  });

  if (zipForm) {
    updateZipFileList();
    updateZipHints();
    zipForm.addEventListener("submit", submitZipForm);
  }

  if (zipClearBtn) {
    zipClearBtn.addEventListener("click", clearZipForm);
  }

  if (zipFilesInput) {
    zipFilesInput.addEventListener("change", () => {
      updateZipFileList();
    });
  }

  if (zipBrowseBtn) {
    zipBrowseBtn.addEventListener("click", () => {
      zipFilesInput?.click();
    });
  }

  if (zipNameInput) {
    zipNameInput.addEventListener("input", updateZipGenerateState);
  }

  if (zipPasswordInput) {
    zipPasswordInput.addEventListener("input", updateZipGenerateState);
  }

  if (zipModeSelect) {
    zipModeSelect.addEventListener("change", () => {
      updateZipHints();
    });
  }

  if (zipOsSelect) {
    zipOsSelect.addEventListener("change", () => {
      updateZipHints();
    });
  }

  if (zipDropZone) {
    const activateDrag = () => zipDropZone.classList.add("is-dragover");
    const deactivateDrag = () => zipDropZone.classList.remove("is-dragover");

    ["dragenter", "dragover"].forEach((eventName) => {
      zipDropZone.addEventListener(eventName, (event) => {
        event.preventDefault();
        event.stopPropagation();
        activateDrag();
      });
    });

    ["dragleave", "dragend"].forEach((eventName) => {
      zipDropZone.addEventListener(eventName, (event) => {
        event.preventDefault();
        event.stopPropagation();
        deactivateDrag();
      });
    });

    zipDropZone.addEventListener("drop", (event) => {
      event.preventDefault();
      event.stopPropagation();
      deactivateDrag();
      const files = event.dataTransfer?.files;
      if (!files || !files.length) {
        return;
      }
      const dataTransfer = new DataTransfer();
      Array.from(files).forEach((file) => dataTransfer.items.add(file));
      if (zipFilesInput) {
        zipFilesInput.files = dataTransfer.files;
        updateZipFileList();
      }
    });

    zipDropZone.addEventListener("click", (event) => {
      const target = event.target;
      if (
        target instanceof HTMLElement &&
        target.closest("button") &&
        target !== zipDropZone
      ) {
        return;
      }
      zipFilesInput?.click();
    });
  }
});
