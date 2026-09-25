const root = document.querySelector(".chat");
const log = root.querySelector(".chat__log");
const empty = root.querySelector(".chat__empty");
const title = root.querySelector(".chat__title");
const typing = root.querySelector(".chat__typing");
const context = root.querySelector(".context");
const form = root.querySelector(".composer");
const input = form.querySelector("textarea");
const sendButton = form.querySelector("button[type=submit]");
const errorBox = form.querySelector(".composer__error");
const bubbleTemplate = document.getElementById("bubble-template");
const intentLabels = JSON.parse(document.getElementById("intent-labels").textContent);
const SLOT_LABELS = { nganh_hoc: "Ngành", nam: "Năm", phuong_thuc: "Phương thức" };
const NETWORK_ERROR = "Không kết nối được máy chủ. Kiểm tra mạng rồi gửi lại.";
const CUT_OFF = "Mất kết nối khi trợ lý đang trả lời. Hãy gửi lại câu hỏi.";
let conversationId = root.dataset.conversationId;

function scrollToLatest() {
  window.scrollTo({ top: document.documentElement.scrollHeight });
}

function addBubble(role, text) {
  const item = bubbleTemplate.content.firstElementChild.cloneNode(true);
  item.classList.add(role === "user" ? "bubble--user" : "bubble--bot");
  item.querySelector(".bubble__who").textContent = role === "user" ? "Bạn" : "Trợ lý";
  item.querySelector(".bubble__text").textContent = text;
  log.append(item);
  empty.hidden = true;
  scrollToLatest();
  return item;
}

function showSources(item, sources) {
  const links = sources.filter((url) => /^https?:\/\//.test(url));
  item.querySelector(".bubble__sources ul").replaceChildren(...links.map((url) => {
    const entry = document.createElement("li");
    const link = document.createElement("a");
    Object.assign(link, { href: url, textContent: url, target: "_blank", rel: "noopener noreferrer" });
    entry.append(link);
    return entry;
  }));
  item.querySelector(".bubble__sources").hidden = links.length === 0;
}

function renderContext(state) {
  const slots = state.slots || {};
  const chips = [
    intentLabels[state.intent],
    ...Object.entries(SLOT_LABELS).filter(([name]) => slots[name]).map(([name, label]) => `${label} ${slots[name]}`),
  ].filter(Boolean);
  context.querySelector(".context__chips").replaceChildren(...chips.map((text) => {
    const chip = document.createElement("li");
    chip.textContent = text;
    return chip;
  }));
  context.hidden = chips.length === 0;
}

function setBusy(busy) {
  sendButton.disabled = busy;
  typing.textContent = busy ? "Trợ lý đang trả lời…" : "";
}

async function post(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (response.status === 401) {
    window.location.assign("/login");
  }
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || `Máy chủ trả lỗi ${response.status}. Hãy gửi lại.`);
  }
  return response;
}

async function readEvents(response, onEvent) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const lines = buffer.split("\n");
    buffer = done ? "" : lines.pop();
    lines.filter((line) => line.trim()).forEach((line) => onEvent(JSON.parse(line)));
    if (done) return;
  }
}

async function ensureConversation() {
  if (!conversationId) {
    const created = await (await post("/chat/conversations")).json();
    conversationId = String(created.id);
    history.replaceState(null, "", created.url);
  }
  return conversationId;
}

async function send(text) {
  const question = text.trim();
  if (!question || sendButton.disabled) return;
  errorBox.textContent = "";
  const asked = addBubble("user", question);
  let answer = null;
  let finished = false;
  input.value = "";
  setBusy(true);
  try {
    const response = await post(`/chat/${await ensureConversation()}/messages`, { text: question });
    await readEvents(response, (event) => {
      if (event.type === "error") throw new Error(event.detail);
      answer = answer || addBubble("assistant", "");
      const reply = answer.querySelector(".bubble__text");
      if (event.type === "token") {
        reply.textContent += event.text;
        scrollToLatest();
        return;
      }
      reply.textContent = event.reply;
      showSources(answer, event.sources);
      renderContext(event.state);
      finished = true;
    });
    if (!finished) throw new Error(CUT_OFF);
    if (title.textContent === "Cuộc trò chuyện mới") title.textContent = question;
    scrollToLatest();
  } catch (error) {
    asked.remove();
    answer?.remove();
    empty.hidden = log.children.length > 0;
    input.value = question;
    errorBox.textContent = error instanceof TypeError ? NETWORK_ERROR : error.message;
  } finally {
    setBusy(false);
    input.focus();
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  send(input.value);
});

input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    form.requestSubmit();
  }
});

root.querySelectorAll(".suggestion").forEach((button) => {
  button.addEventListener("click", () => send(button.textContent));
});

if (window.matchMedia("(min-width: 801px)").matches) {
  root.querySelector(".chat__history").open = true;
}
renderContext(JSON.parse(context.dataset.state));
history.scrollRestoration = "manual";
if (log.lastElementChild) document.fonts.ready.then(scrollToLatest);
