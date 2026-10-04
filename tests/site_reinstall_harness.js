// /get 화면의 재설치 안내가 steps.json 의 reinstall.command 를 그대로 보여 주는지 확인하는 최소 DOM 대역. node tests/site_reinstall_harness.js <app.js> <steps.json>
const fs = require("fs");
const [appPath, stepsPath] = process.argv.slice(2);
const mk = (text = "") => ({ textContent: text, dataset: {}, classList: { toggle() {} }, setAttribute() {}, addEventListener() {}, replaceChildren() {}, appendChild() {} });
const nodes = { "#install-command": mk(), "#command-label": mk(), "#copy-command": mk(), "#copy-status": mk(), "#steps-list": mk(), "#steps-source-status": mk(),
                "#reinstall-command": mk("curl -fsSL https://waveainetworks.com/mac | bash -s -- --reinstall") };
const winTab = { dataset: { os: "windows" }, classList: { toggle() {} }, setAttribute() {}, addEventListener(_, fn) { this.click = fn; } };
const tabs = [winTab];
global.window = { location: { hostname: process.argv[4] === "local" ? "localhost" : "waveainetworks.com" }, setTimeout() {} };
global.navigator = {};
global.document = { querySelector: (q) => nodes[q], querySelectorAll: () => tabs, createElement: () => mk() };
const steps = fs.readFileSync(stepsPath, "utf8");
global.fetch = async () => ({ ok: true, json: async () => JSON.parse(steps) });
const run = new Function(fs.readFileSync(appPath, "utf8"));
run();
setTimeout(() => {
  const out = { after_load: nodes["#reinstall-command"].textContent, install_mac: nodes["#install-command"].textContent };
  winTab.click();
  out.after_windows_tab = nodes["#reinstall-command"].textContent;
  out.install_windows = nodes["#install-command"].textContent;
  console.log(JSON.stringify(out));
}, 50);
