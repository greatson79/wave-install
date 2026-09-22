(() => {
  "use strict";

  // S3의 steps.json이 배포 루트에 도착하면 원격 정본을 우선 사용합니다.
  // 현재 S4 staging에는 S3 파일을 복제하지 않으므로 로컬 렌더용 fixture를 둡니다.
  const fallbackSteps = {
    schema_version: "1.0",
    total: 10,
    steps: [
      { id: 0, title: "OS·셸·디스크·권한 검사", command: "환경 검사", pass_conditions: ["지원 OS", "사용자 폴더 쓰기 가능"], failure_guidance: "OS_UNSUPPORTED 또는 PERMISSION_DENIED" },
      { id: 1, title: "Claude Code 설치", command: "최소 버전 확인", pass_conditions: ["Claude Code 2.1.278 이상"], failure_guidance: "설치 로그의 오류 ID를 확인하세요." },
      { id: 2, title: "Claude 로그인", command: "브라우저 로그인", pass_conditions: ["유료 계정 인증 완료"], failure_guidance: "CLAUDE_LOGIN_REQUIRED" },
      { id: 3, title: "Wave Terminal 내려받기·검증", command: "Release + SHA256 + minisign", pass_conditions: ["해시 일치", "minisign 통과"], failure_guidance: "CHECKSUM_MISMATCH 또는 MINISIGN_INVALID" },
      { id: 4, title: "설치·cys 셸 연결", command: "사용자 폴더 설치", pass_conditions: ["cys 실행", "셸 연결"], failure_guidance: "SHELL_NOT_CONNECTED" },
      { id: 5, title: "데몬 등록", command: "선택 · 기본 on", pass_conditions: ["데몬 상태 확인"], failure_guidance: "DAEMON_START_FAILED" },
      { id: 6, title: "wave-pack 배치", command: "~/.cys/pack에 배치", pass_conditions: ["팩 파일 존재", "SHA256 확인"], failure_guidance: "PACK_DEPLOY_FAILED" },
      { id: 7, title: "초기 편성 기동", command: "마스터 + 부서 1", pass_conditions: ["좌석 2개 기동"], failure_guidance: "ROSTER_START_FAILED" },
      { id: 8, title: "검증", command: "cys identify", pass_conditions: ["지침 주입 실측", "주입량 ≤ 20KB"], failure_guidance: "VERIFY_FALSE_GREEN" },
      { id: 9, title: "완료 화면", command: "START-HERE로 이동", pass_conditions: ["단계별 exit·시각·버전 저장"], failure_guidance: "INSTALL_STATE_INCOMPLETE" }
    ]
  };

  const commands = {
    mac: {
      label: "macOS · 사용자 폴더 설치",
      command: 'curl -fsSL https://raw.githubusercontent.com/greatson79/wave-install/main/bootstrap.sh -o bootstrap.sh && bash bootstrap.sh'
    },
    windows: {
      label: "Windows · 준비 중",
      command: "Windows 설치기는 준비 중입니다."
    }
  };

  const commandNode = document.querySelector("#install-command");
  const labelNode = document.querySelector("#command-label");
  const copyButton = document.querySelector("#copy-command");
  const copyStatus = document.querySelector("#copy-status");
  const stepsList = document.querySelector("#steps-list");
  const sourceStatus = document.querySelector("#steps-source-status");

  function setOS(os) {
    const selected = commands[os] || commands.mac;
    commandNode.textContent = selected.command;
    labelNode.textContent = selected.label;
    document.querySelectorAll(".os-tab").forEach((button) => {
      const isActive = button.dataset.os === os;
      button.classList.toggle("is-active", isActive);
      button.setAttribute("aria-selected", String(isActive));
    });
    copyStatus.textContent = "전체 설치팩 폴더에서 실행하세요. v0.1.1 전체 설치 검증은 진행 중입니다.";
  }

  async function copyCommand() {
    const command = commandNode.textContent;
    try {
      await navigator.clipboard.writeText(command);
      copyButton.textContent = "복사됨";
      copyStatus.textContent = "명령을 클립보드에 복사했습니다. 전체 설치팩 폴더에서 실행하세요. v0.1.1 전체 설치 검증은 진행 중입니다.";
    } catch (error) {
      copyStatus.textContent = "자동 복사에 실패했습니다. 명령을 직접 선택해 복사하세요.";
    }
    window.setTimeout(() => { copyButton.textContent = "복사"; }, 1800);
  }

  function isValidSteps(payload) {
    return Boolean(
      payload &&
      Array.isArray(payload.steps) &&
      payload.steps.length === 10 &&
      payload.steps.every((step) =>
        step &&
        Number.isInteger(step.id) &&
        typeof step.title === "string" &&
        typeof step.command === "string" &&
        Array.isArray(step.pass_conditions) &&
        typeof step.failure_guidance === "string"
      )
    );
  }

  function normalizeSteps(payload) {
    if (payload && payload.schema === "wave-install.steps.v1" && Array.isArray(payload.steps)) {
      return {
        schema_version: "1.0",
        total: payload.steps.length,
        steps: payload.steps.map((step) => ({
          id: step.index,
          title: step.title,
          command: step.command?.macos || "사용자 폴더 설치 단계",
          pass_conditions: (step.pass || []).map((condition) => {
            if (condition.message) return condition.message;
            if (condition.kind === "exit_code") return `exit code = ${condition.equals}`;
            if (condition.kind === "file_exists") return `파일 존재 · ${condition.path}`;
            if (condition.kind === "sha256") return `SHA256 확인 · ${condition.source}`;
            if (condition.kind === "count") return `개수 확인 · ${condition.equals}`;
            if (condition.kind === "json_path") return `JSON 확인 · ${condition.json_path}`;
            return condition.kind || "통과 조건 확인";
          }),
          failure_guidance: step.on_fail?.message || step.on_fail?.error_id || "오류 ID를 확인하세요."
        }))
      };
    }
    return payload;
  }

  function addText(parent, tag, text, className) {
    const node = document.createElement(tag);
    node.textContent = text;
    if (className) node.className = className;
    parent.appendChild(node);
    return node;
  }

  function renderSteps(payload) {
    stepsList.replaceChildren();
    payload.steps.forEach((step) => {
      const item = document.createElement("li");
      item.className = "step-item";
      const content = document.createElement("div");
      addText(content, "h3", step.title);
      addText(content, "p", step.command);
      const meta = document.createElement("div");
      meta.className = "step-meta";
      step.pass_conditions.forEach((condition) => addText(meta, "span", condition, "pass"));
      addText(meta, "span", `실패 시 · ${step.failure_guidance}`);
      content.appendChild(meta);
      item.appendChild(content);
      stepsList.appendChild(item);
    });
  }

  async function loadSteps() {
    // 로컬 preview에서는 S3 산출물을 아직 복제하지 않으므로 404 요청을 만들지 않습니다.
    // 배포 호스트에서는 실제 steps.json을 먼저 읽고, 스키마가 맞을 때만 렌더합니다.
    const isLocalPreview = ["localhost", "127.0.0.1", "::1"].includes(window.location.hostname);
    const candidates = isLocalPreview ? [] : ["../steps.json", "./steps.json"];
    for (const path of candidates) {
      try {
        const response = await fetch(path, { cache: "no-store" });
        if (!response.ok) continue;
        const payload = normalizeSteps(await response.json());
        if (!isValidSteps(payload)) continue;
        renderSteps(payload);
        sourceStatus.textContent = `steps.json 연결됨 · ${payload.steps.length}/10 단계`;
        sourceStatus.dataset.source = "remote";
        return;
      } catch (error) {
        // 다음 후보 경로 또는 로컬 fixture로 진행합니다.
      }
    }
    renderSteps(fallbackSteps);
    sourceStatus.textContent = "S3 steps.json 대기 · 로컬 스키마 fixture 표시";
    sourceStatus.dataset.source = "fixture";
  }

  document.querySelectorAll(".os-tab").forEach((button) => {
    button.addEventListener("click", () => setOS(button.dataset.os));
  });
  copyButton.addEventListener("click", copyCommand);
  setOS("mac");
  loadSteps();
})();
