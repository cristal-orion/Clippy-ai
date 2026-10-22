const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const { test } = require("node:test");
const vm = require("node:vm");

const html = readFileSync(`${__dirname}/../static/index.html`, "utf8");
const script = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].at(-1)[1];

function editor({ editing = true, authenticated = true, failSave = false } = {}) {
  const fields = {};
  for (const [id, value] of Object.entries({
    configName: "Test assistant", agentSelect: "Clippy", providerSelect: "openai",
    modelSelect: "gpt-4o", customModel: "", apiKey: "", systemPromptEditor: "",
    welcomeMessageEditor: "", ragContentArea: "", uiModeSelect: "classic",
    accentColor: "#4f46e5", maxMessages: "40", maxTokens: "1200", temperature: "0",
    darkMode: "", webSearchEnabled: "", generativeUi: "", providerInfo: "", apiKeyInfo: "",
    configIdDisplay: "", embedCode: "", embedOutput: "",
  })) fields[id] = { value, checked: false, style: {} };
  fields.animationGrid = { appendChild() {} };

  const requests = [];
  const statuses = [];
  const alerts = [];
  const previews = [];
  const storage = new Map(authenticated ? [["clippy_auth_token", "test-token"]] : []);
  let saved = { config_id: "test-config", max_messages_per_conversation: 0 };
  const context = vm.createContext({
    console: { log() {}, error() {} },
    document: {
      readyState: "loading", addEventListener() {},
      createElement: () => ({}),
      getElementById: (id) => fields[id], querySelector: () => null,
    },
    window: { addEventListener() {}, location: { origin: "http://localhost" } },
    localStorage: {
      getItem: (key) => storage.get(key), setItem: (key, value) => storage.set(key, value),
    },
    setTimeout() {},
    fetch: async (url, options = {}) => {
      requests.push({ url, ...options });
      if (options.method === "PUT" || options.method === "POST") {
        if (failSave) return { ok: false };
        saved = { ...saved, ...JSON.parse(options.body) };
      }
      return { ok: true, json: async () => ({ ...saved }) };
    },
  });
  vm.runInContext(script, context);
  Object.assign(context, {
    updateStatus: (message, type) => statuses.push({ message, type }),
    win95Alert: async (message) => alerts.push(message),
    win95Confirm: async () => false,
    switchPreview: () => previews.push(fields.uiModeSelect.value),
    populateModels() {}, onUiModeChange() {},
  });
  if (editing) vm.runInContext('editingConfigId = "test-config";', context);
  return { context, fields, requests, statuses, alerts, previews, storage };
}

test("Apply Changes saves limit 40 and restores it when reopening Edit", async () => {
  const { context, fields, requests, statuses } = editor();
  fields.customModel.value = "custom-model";
  fields.webSearchEnabled.checked = true;
  await context.reloadAgent();

  assert.equal(requests.length, 1);
  assert.equal(requests[0].url, "/api/configs/test-config");
  assert.equal(requests[0].method, "PUT");
  assert.equal(requests[0].headers.Authorization, "Bearer test-token");
  const body = JSON.parse(requests[0].body);
  assert.equal(body.max_messages_per_conversation, 40);
  assert.equal(body.temperature, 0);
  assert.equal(body.web_search_enabled, true);
  assert.equal(body.model, "custom-model");
  assert.equal(Object.hasOwn(body, "api_key"), false);
  assert.equal(fields.embedOutput.style.display, undefined);
  assert.equal(statuses.at(-1).type, "success");

  fields.maxMessages.value = "0";
  await context.loadConfigForEdit("test-config");
  assert.equal(requests.at(-1).url, "/api/configs/test-config");
  assert.equal(fields.maxMessages.value, 40);

  fields.maxMessages.value = "0";
  await context.reloadAgent();
  fields.maxMessages.value = "40";
  await context.loadConfigForEdit("test-config");
  assert.equal(fields.maxMessages.value, 0, "unlimited can still be saved explicitly");
});

test("failed saves do not report success or reload the preview", async () => {
  const { context, statuses, alerts, previews } = editor({ failSave: true });
  await context.reloadAgent();
  assert.equal(statuses.at(-1).type, "error");
  assert.equal(statuses.some(({ type }) => type === "success"), false);
  assert.equal(alerts.length, 1);
  assert.equal(previews.length, 0);
});

test("Apply Changes requires authentication before updating a saved config", async () => {
  const { context, requests, statuses, previews } = editor({ authenticated: false });
  await context.reloadAgent();
  assert.equal(requests.length, 0);
  assert.equal(previews.length, 0);
  assert.equal(statuses.some(({ type }) => type === "success"), false);
});

test("new configurations can still preview without creating a saved config", async () => {
  const { context, fields, requests, previews } = editor({ editing: false });
  fields.apiKey.value = "test-key";
  await context.reloadAgent();
  assert.equal(requests.length, 0);
  assert.deepEqual(previews, ["classic"]);
});

test("Update Configuration still saves and generates the embed code", async () => {
  const { context, fields, requests } = editor();
  await context.saveConfigAndGenerateEmbed();
  assert.equal(requests[0].method, "PUT");
  assert.equal(fields.embedOutput.style.display, "block");
  assert.match(fields.embedCode.value, /data-config-id="test-config"/);
});
