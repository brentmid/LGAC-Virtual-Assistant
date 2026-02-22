const authScreen = document.getElementById("auth-screen");
const chatScreen = document.getElementById("chat-screen");
const authForm = document.getElementById("auth-form");
const authError = document.getElementById("auth-error");
const passwordInput = document.getElementById("password-input");
const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");
const chatMessages = document.getElementById("chat-messages");
const sendBtn = document.getElementById("send-btn");

let sessionId = null;

// Auth
authForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  authError.hidden = true;

  try {
    const res = await fetch("/api/auth", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password: passwordInput.value }),
    });

    if (!res.ok) {
      authError.hidden = false;
      passwordInput.value = "";
      passwordInput.focus();
      return;
    }

    const data = await res.json();
    sessionId = data.session_id;
    authScreen.hidden = true;
    chatScreen.hidden = false;
    chatInput.focus();
  } catch (err) {
    authError.textContent = "Connection error. Please try again.";
    authError.hidden = false;
  }
});

// Chat
chatForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const message = chatInput.value.trim();
  if (!message || !sessionId) return;

  // Check for feedback: prefix
  const feedbackMatch = message.match(/^feedback:\s*([\s\S]+)/i);
  if (feedbackMatch) {
    const feedbackText = feedbackMatch[1].trim();
    if (!feedbackText) return;

    appendMessage("user", message);
    chatInput.value = "";
    chatInput.style.height = "auto";
    sendBtn.disabled = true;

    try {
      const res = await fetch("/api/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, feedback: feedbackText }),
      });

      if (res.ok) {
        const data = await res.json();
        appendMessage("assistant", data.message);
      } else {
        appendMessage("assistant", "Could not submit feedback. Please try again.");
      }
    } catch (err) {
      appendMessage("assistant", "Connection error. Could not submit feedback.");
    } finally {
      sendBtn.disabled = false;
      chatInput.focus();
    }
    return;
  }

  appendMessage("user", message);
  chatInput.value = "";
  chatInput.style.height = "auto";
  sendBtn.disabled = true;

  const typing = showTypingIndicator();

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, message }),
    });

    typing.remove();

    if (res.status === 401) {
      appendMessage(
        "assistant",
        "Your session has expired. Please refresh the page to sign in again."
      );
      sessionId = null;
      return;
    }

    if (!res.ok) {
      appendMessage("assistant", "Sorry, something went wrong. Please try again.");
      return;
    }

    const data = await res.json();
    appendMessage("assistant", data.answer, data.sources);
  } catch (err) {
    typing.remove();
    appendMessage("assistant", "Connection error. Please check your internet and try again.");
  } finally {
    sendBtn.disabled = false;
    chatInput.focus();
  }
});

// Auto-resize textarea
chatInput.addEventListener("input", () => {
  chatInput.style.height = "auto";
  chatInput.style.height = Math.min(chatInput.scrollHeight, 120) + "px";
});

// Enter to send, Shift+Enter for newline
chatInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    chatForm.dispatchEvent(new Event("submit"));
  }
});

function appendMessage(role, content, sources) {
  const msg = document.createElement("div");
  msg.className = `message ${role}`;

  const rendered = role === "assistant"
    ? DOMPurify.sanitize(marked.parse(content))
    : escapeHtml(content);
  let html = `<div class="message-content">${rendered}`;

  if (sources && sources.length > 0) {
    html += `<div class="sources"><strong>Sources:</strong><ul>`;
    for (const src of sources) {
      html += `<li>${escapeHtml(src.document)}</li>`;
    }
    html += `</ul></div>`;
  }

  html += `</div>`;
  msg.innerHTML = html;
  chatMessages.appendChild(msg);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function showTypingIndicator() {
  const indicator = document.createElement("div");
  indicator.className = "typing-indicator";
  indicator.innerHTML = "<span></span><span></span><span></span>";
  chatMessages.appendChild(indicator);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  return indicator;
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}
