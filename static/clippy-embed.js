/**
 * Clippy AI Embed Widget
 * Universal widget to embed Clippy on any website
 * Usage: <script src="https://your-backend.com/static/clippy-embed.js" data-config-id="YOUR_CONFIG_ID"></script>
 */

(function () {
  "use strict";

  // Configuration
  const BACKEND_URL = window.CLIPPY_BACKEND_URL || detectBackendUrl();
  const CONFIG_ID = getConfigId();

  // State
  let clippyAgent = null;
  let config = null;
  let conversationHistory = [];
  let isProcessing = false;

  // Detect backend URL from script source
  function detectBackendUrl() {
    const scripts = document.getElementsByTagName("script");
    for (let script of scripts) {
      if (script.src && script.src.includes("clippy-embed.js")) {
        const url = new URL(script.src);
        return url.origin;
      }
    }
    return "https://clippy-9clxe.ondigitalocean.app"; // Fallback
  }

  // Get config ID from script tag data attribute
  function getConfigId() {
    const scripts = document.getElementsByTagName("script");
    for (let script of scripts) {
      if (script.src && script.src.includes("clippy-embed.js")) {
        return script.getAttribute("data-config-id");
      }
    }
    return null;
  }

  // Load required dependencies
  function loadDependencies(callback) {
    console.log("Clippy Widget: Loading dependencies...");
    let jQueryLoaded = false;
    let clippyLoaded = false;

    function checkComplete() {
      if (jQueryLoaded && clippyLoaded) {
        console.log("Clippy Widget: All dependencies loaded!");
        callback();
      }
    }

    // Load jQuery 1.x (ClippyJS requires it, even if 3.x is present)
    const needsJQuery1 =
      typeof jQuery === "undefined" ||
      !jQuery.Deferred ||
      jQuery.fn.jquery.startsWith("3.");

    if (needsJQuery1) {
      console.log(
        "Clippy Widget: Loading jQuery 1.x (required by ClippyJS)..."
      );

      // Save existing jQuery if present
      const existingJQuery = window.jQuery;
      const existing$ = window.$;

      const jqueryScript = document.createElement("script");
      jqueryScript.src = "https://code.jquery.com/jquery-1.12.4.min.js";
      jqueryScript.onload = function () {
        console.log("Clippy Widget: jQuery 1.x loaded");

        // Save jQuery 1.x for ClippyJS
        window.clippy_jQuery = window.jQuery;

        // Restore original jQuery if it existed (but keep 1.x as default for now)
        // We'll restore after ClippyJS loads
        window._original_jQuery = existingJQuery;
        window._original_$ = existing$;

        jQueryLoaded = true;
        loadClippy(); // Load ClippyJS AFTER jQuery 1.x is ready
      };
      jqueryScript.onerror = function () {
        console.error("Clippy Widget: Failed to load jQuery");
      };
      document.head.appendChild(jqueryScript);
    } else {
      console.log("Clippy Widget: jQuery 1.x already loaded");
      window.clippy_jQuery = window.jQuery;
      jQueryLoaded = true;
      loadClippy();
    }

    function loadClippy() {
      // Load ClippyJS (now jQuery 1.x is available globally)
      if (typeof clippy === "undefined") {
        console.log("Clippy Widget: Loading ClippyJS...");
        const clippyScript = document.createElement("script");
        clippyScript.src = BACKEND_URL + "/static/clippy.js";
        clippyScript.onload = function () {
          console.log("Clippy Widget: ClippyJS loaded");

          // Now restore original jQuery if needed
          if (window._original_jQuery) {
            window.jQuery = window._original_jQuery;
            window.$ = window._original_$;
            delete window._original_jQuery;
            delete window._original_$;
          }

          clippyLoaded = true;
          checkComplete();
        };
        clippyScript.onerror = function () {
          console.error("Clippy Widget: Failed to load ClippyJS");
        };
        document.head.appendChild(clippyScript);

        // Load Clippy CSS
        const clippyCSS = document.createElement("link");
        clippyCSS.rel = "stylesheet";
        clippyCSS.href = BACKEND_URL + "/static/assets/clippy.css";
        document.head.appendChild(clippyCSS);
      } else {
        console.log("Clippy Widget: ClippyJS already loaded");
        clippyLoaded = true;
        checkComplete();
      }
    }
  }

  // Load configuration from backend
  async function loadConfig() {
    if (!CONFIG_ID) {
      console.error("Clippy Widget: No config ID provided!");
      return null;
    }

    try {
      const response = await fetch(`${BACKEND_URL}/api/widget/config/${CONFIG_ID}`);
      if (!response.ok) {
        throw new Error("Configuration not found");
      }
      const data = await response.json();
      return data.config;
    } catch (error) {
      console.error("Clippy Widget: Failed to load configuration:", error);
      return null;
    }
  }

  // Initialize Clippy agent
  function initClippy() {
    if (!config) {
      console.error("Clippy Widget: No configuration loaded");
      return;
    }

    console.log("Clippy Widget: Starting agent initialization...", {
      agent: config.agent,
      cdnPath: window.CLIPPY_CDN,
    });

    // Check if clippy is available
    if (typeof clippy === "undefined") {
      console.error("Clippy Widget: ClippyJS library not loaded!");
      return;
    }

    console.log("Clippy Widget: Loading agent:", config.agent || "Clippy");

    // Load agent (ClippyJS was loaded with jQuery 1.x available)
    clippy.load(
      config.agent || "Clippy",
      function (agent) {
        console.log("Clippy Widget: Agent loaded successfully!");
        clippyAgent = agent;

        // Disable sounds to avoid Chrome autoplay errors
        agent._sounds = false;

        // Position in bottom right, leaving room for balloon (300-400px wide)
        const startX = Math.max(0, window.innerWidth - 350);
        const startY = Math.max(0, window.innerHeight - 250);
        agent.moveTo(startX, startY);
        agent.show();
        agent.play("Greeting");

        // Create chat balloon
        createChatBalloon();
        updateBalloonPosition();

        // Update balloon position when agent moves
        setInterval(updateBalloonPosition, 100);

        // Add click handler to toggle balloon
        agent._el.on("click", function () {
          toggleBalloon();
        });

        // Show greeting in our custom balloon (not ClippyJS balloon)
        const greeting = config.welcome_message
          ? config.welcome_message
          : `Ciao! Sono ${config.agent}. Come posso aiutarti?`;

        setTimeout(() => {
          showMessage(greeting);
          // Show balloon on startup
          document.getElementById("clippy-balloon").style.display = "block";
        }, 500);

        console.log("Clippy Widget: Initialized successfully!", {
          agent: config.agent,
          provider: config.provider,
          model: config.model,
        });
      },
      function (error) {
        console.error("Clippy Widget: Failed to load agent:", error);
      }
    );
  }

  // Toggle balloon visibility
  function toggleBalloon() {
    const balloon = document.getElementById("clippy-balloon");
    if (!balloon) return;

    if (balloon.style.display === "none") {
      balloon.style.display = "block";
      if (clippyAgent) clippyAgent.play("Explain");
    } else {
      balloon.style.display = "none";
      if (clippyAgent) clippyAgent.play("Hide");
    }
  }

  // Update balloon position to follow Clippy, clamped to viewport
  function updateBalloonPosition() {
    if (!clippyAgent) return;

    const balloon = document.getElementById("clippy-balloon");
    if (!balloon) return;

    // Get Clippy's position
    const clippyEl = clippyAgent._el[0];
    const rect = clippyEl.getBoundingClientRect();
    const bw = balloon.offsetWidth;
    const bh = balloon.offsetHeight;
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const margin = 8;

    // Desired position: above Clippy, slightly to the left
    let left = rect.left + rect.width / 2 - bw / 2;
    let top = rect.top - bh - 20;

    // Clamp horizontal: keep balloon within viewport
    if (left + bw > vw - margin) left = vw - bw - margin;
    if (left < margin) left = margin;

    // If balloon goes above viewport, show it below Clippy instead
    if (top < margin) {
      top = rect.bottom + 20;
    }

    // Clamp bottom edge too
    if (top + bh > vh - margin) {
      top = vh - bh - margin;
    }

    balloon.style.left = left + "px";
    balloon.style.top = top + "px";
    balloon.style.right = "auto";
    balloon.style.bottom = "auto";
  }

  // Create chat balloon
  function createChatBalloon() {
    const balloon = document.createElement("div");
    balloon.id = "clippy-balloon";
    balloon.innerHTML = `
      <style>
        #clippy-balloon {
          position: fixed;
          min-width: 300px;
          max-width: 400px;
          background: #ffffc0;
          border: 2px solid #333;
          border-radius: 10px;
          padding: 15px;
          padding-top: 30px;
          box-shadow: 0 4px 15px rgba(0,0,0,0.3);
          font-family: 'Segoe UI', Arial, sans-serif;
          font-size: 14px;
          color: #000;
          display: none;
          z-index: 9999;
          transition: left 0.1s, top 0.1s;
        }
        #clippy-balloon::after {
          content: '';
          position: absolute;
          bottom: -16px;
          left: 50px;
          border-left: 15px solid transparent;
          border-right: 15px solid transparent;
          border-top: 16px solid #ffffc0;
        }
        #clippy-balloon::before {
          content: '';
          position: absolute;
          bottom: -19px;
          left: 48px;
          border-left: 17px solid transparent;
          border-right: 17px solid transparent;
          border-top: 19px solid #333;
        }
        #clippy-close {
          position: absolute;
          top: 5px;
          right: 5px;
          background: transparent;
          border: 1px solid #999;
          border-radius: 3px;
          width: 18px;
          height: 18px;
          cursor: pointer;
          font-size: 14px;
          line-height: 1;
        }
        #clippy-message {
          margin-bottom: 12px;
          line-height: 1.5;
          max-height: 200px;
          overflow-y: auto;
        }
        #clippy-input-wrapper {
          display: flex;
          gap: 5px;
          margin-top: 10px;
          padding-top: 10px;
          border-top: 1px solid rgba(0,0,0,0.2);
        }
        #clippy-attachments {
          display: flex;
          flex-wrap: wrap;
          gap: 4px;
          margin-top: 8px;
        }
        #clippy-attachments:empty { display: none; }
        .clippy-attach-chip {
          display: inline-flex; align-items: center; gap: 4px;
          background: rgba(0,0,0,0.08); border: 1px solid rgba(0,0,0,0.25);
          border-radius: 10px; padding: 2px 4px 2px 7px; font-size: 11px; max-width: 160px;
        }
        .clippy-attach-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .clippy-attach-chip button {
          background: transparent; border: none; cursor: pointer; font-size: 13px;
          line-height: 1; padding: 0 2px; color: #a00000; font-weight: bold;
        }
        #clippy-attach {
          padding: 0 10px; background: transparent; border: 1px solid #999;
          border-radius: 4px; cursor: pointer; font-size: 16px; flex-shrink: 0;
        }
        #clippy-attach:hover { background: rgba(0,0,0,0.06); }
        #clippy-input {
          flex: 1;
          padding: 8px;
          border: 1px solid #999;
          border-radius: 4px;
          font-size: 13px;
        }
        #clippy-send {
          padding: 8px 15px;
          background: #4caf50;
          color: white;
          border: none;
          border-radius: 4px;
          cursor: pointer;
          font-weight: bold;
        }
        #clippy-send:hover {
          background: #45a049;
        }
        #clippy-send:disabled {
          background: #ccc;
          cursor: not-allowed;
        }
      </style>
      <button id="clippy-close" onclick="document.getElementById('clippy-balloon').style.display='none'">×</button>
      <div id="clippy-message">Ciao! 👋</div>
      <div id="clippy-attachments"></div>
      <div id="clippy-input-wrapper">
        <input type="file" id="clippy-file" accept="image/*,application/pdf" multiple style="display:none" />
        <button id="clippy-attach" title="Allega immagine o PDF">📎</button>
        <input type="text" id="clippy-input" placeholder="Scrivi un messaggio..." />
        <button id="clippy-send">Invia</button>
      </div>
    `;
    document.body.appendChild(balloon);

    // Setup event listeners
    const input = document.getElementById("clippy-input");
    const sendBtn = document.getElementById("clippy-send");

    sendBtn.addEventListener("click", sendMessage);
    input.addEventListener("keypress", function (e) {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
    });

    // File attachments
    const fileInput = document.getElementById("clippy-file");
    document
      .getElementById("clippy-attach")
      .addEventListener("click", function () {
        fileInput.click();
      });
    fileInput.addEventListener("change", function () {
      const accepted = validateAttachments(Array.from(fileInput.files));
      classicAttachments = classicAttachments.concat(accepted);
      renderAttachChips("clippy-attachments", classicAttachments);
      fileInput.value = "";
    });
  }

  // Show message in balloon
  // Show message in custom balloon (NOT using ClippyJS native balloon)
  function formatMarkdown(text) {
    return text
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/\*(.+?)\*/g, "<em>$1</em>")
      .replace(/`(.+?)`/g, "<code style='background:#eee;padding:1px 4px;border-radius:3px;font-size:0.9em;'>$1</code>")
      .replace(/\n/g, "<br>");
  }

  function showMessage(text) {
    const balloon = document.getElementById("clippy-balloon");
    const messageDiv = document.getElementById("clippy-message");

    if (balloon && messageDiv) {
      messageDiv.innerHTML = formatMarkdown(text);
      balloon.style.display = "block";
    }

    // Play animation but DON'T use native balloon
    if (clippyAgent) {
      clippyAgent.play("Explain");
    }
  }

  // Send message to AI
  async function sendMessage() {
    const input = document.getElementById("clippy-input");
    const sendBtn = document.getElementById("clippy-send");
    const message = input.value.trim();

    if ((!message && classicAttachments.length === 0) || isProcessing) return;

    // Capture + clear attachments for this turn
    const sentAttachments = classicAttachments.slice();
    const userContent = await buildUserContent(message, sentAttachments);
    classicAttachments = [];
    renderAttachChips("clippy-attachments", classicAttachments);

    input.value = "";
    input.disabled = true;
    sendBtn.disabled = true;
    isProcessing = true;

    // Add to history
    conversationHistory.push({ role: "user", content: userContent });

    // Show thinking animation
    if (clippyAgent) {
      clippyAgent.play("Searching");
    }

    try {
      // Call backend API using secure widget endpoint (no API key exposed!)
      const response = await fetch(`${BACKEND_URL}/api/widget/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          config_id: CONFIG_ID, // Only config ID needed - backend uses stored API key
          messages: conversationHistory,
        }),
      });

      // Conversation message cap reached (server-side gate)
      if (response.status === 429) {
        showMessage("Hai raggiunto il limite di messaggi per questa conversazione.");
        if (clippyAgent) {
          clippyAgent.stop();
          clippyAgent.play("Alert");
        }
        lockClassicInput();
        isProcessing = false;
        return;
      }

      if (!response.ok) {
        throw new Error("API request failed");
      }

      const data = await response.json();
      const reply = data.choices[0].message.content;

      // Add to history
      conversationHistory.push({ role: "assistant", content: reply });

      // Show response
      showMessage(reply);

      // Play success animation
      if (clippyAgent) {
        clippyAgent.stop();
        clippyAgent.play("Congratulate");
      }

      // Lock the conversation if the message cap has now been reached
      if (isConversationLimitReached()) {
        const messageDiv = document.getElementById("clippy-message");
        if (messageDiv) {
          messageDiv.innerHTML +=
            '<div style="margin-top:8px;font-size:12px;color:#666;border-top:1px solid rgba(0,0,0,0.15);padding-top:6px;">Hai raggiunto il limite di messaggi per questa conversazione.</div>';
        }
        lockClassicInput();
        isProcessing = false;
        return;
      }
    } catch (error) {
      console.error("Clippy Widget: Chat error:", error);
      showMessage("Ops! Si è verificato un errore. Riprova!");

      if (clippyAgent) {
        clippyAgent.stop();
        clippyAgent.play("Alert");
      }
    }

    isProcessing = false;
    input.disabled = false;
    sendBtn.disabled = false;
    input.focus();
  }

  // Disable the classic balloon input once the conversation cap is hit
  function lockClassicInput() {
    const input = document.getElementById("clippy-input");
    const sendBtn = document.getElementById("clippy-send");
    if (input) {
      input.disabled = true;
      input.placeholder = "Limite raggiunto";
    }
    if (sendBtn) sendBtn.disabled = true;
  }

  // Shared: true when the per-conversation message cap has been reached
  function isConversationLimitReached() {
    const limit =
      config && config.max_messages_per_conversation
        ? config.max_messages_per_conversation
        : 0;
    if (limit <= 0) return false;
    const userMsgs = conversationHistory.filter((m) => m.role === "user").length;
    return userMsgs >= limit;
  }

  // Escape text for safe insertion into innerHTML
  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  // ============ File attachments (images / PDF) ============
  // Shared by the classic balloon and the modern panel. Attachments are sent to
  // /api/widget/chat as an OpenAI/LiteLLM content array; the backend turns PDFs
  // into text and forwards images to vision-capable models.

  const MAX_ATTACH_BYTES = 8 * 1024 * 1024; // 8 MB per file
  let classicAttachments = [];
  let modernAttachments = [];

  function readFileAsDataURL(file) {
    return new Promise(function (resolve, reject) {
      const r = new FileReader();
      r.onload = function () {
        resolve(r.result);
      };
      r.onerror = reject;
      r.readAsDataURL(file);
    });
  }

  // Keep only supported, reasonably-sized files
  function validateAttachments(fileList) {
    const ok = [];
    for (let i = 0; i < fileList.length; i++) {
      const f = fileList[i];
      const isImg = f.type.indexOf("image/") === 0;
      const isPdf = f.type === "application/pdf";
      if (!isImg && !isPdf) {
        alert("Only images and PDF files are supported: " + f.name);
        continue;
      }
      if (f.size > MAX_ATTACH_BYTES) {
        alert("File too large (max 8 MB): " + f.name);
        continue;
      }
      ok.push(f);
    }
    return ok;
  }

  // Build a message's content: plain string when there are no files, otherwise
  // a content array with text + image_url / file blocks.
  async function buildUserContent(text, files) {
    if (!files || files.length === 0) return text;
    const blocks = [];
    if (text) blocks.push({ type: "text", text: text });
    for (let i = 0; i < files.length; i++) {
      const f = files[i];
      const dataUrl = await readFileAsDataURL(f);
      if (f.type.indexOf("image/") === 0) {
        blocks.push({ type: "image_url", image_url: { url: dataUrl } });
      } else if (f.type === "application/pdf") {
        blocks.push({
          type: "file",
          file: { filename: f.name, file_data: dataUrl },
        });
      }
    }
    return blocks;
  }

  // Render attachment chips for a list into a container
  function renderAttachChips(containerId, list) {
    const wrap = document.getElementById(containerId);
    if (!wrap) return;
    wrap.innerHTML = "";
    list.forEach(function (f, i) {
      const chip = document.createElement("span");
      chip.className = "clippy-attach-chip";
      const name = document.createElement("span");
      name.className = "clippy-attach-name";
      name.textContent =
        (f.type.indexOf("image/") === 0 ? "🖼️ " : "📄 ") + f.name;
      const rm = document.createElement("button");
      rm.type = "button";
      rm.textContent = "×";
      rm.title = "Remove";
      rm.addEventListener("click", function () {
        list.splice(i, 1);
        renderAttachChips(containerId, list);
      });
      chip.appendChild(name);
      chip.appendChild(rm);
      wrap.appendChild(chip);
    });
  }

  // ============ Modern UI mode ============

  let modernPanelOpen = false;

  // Inject the modern widget stylesheet, driven by accent color + light/dark base
  function injectModernStyles() {
    if (document.getElementById("clippy-modern-styles")) return;

    const accent = config.accent_color || "#4f46e5";
    const dark = !!config.dark_mode;
    const v = dark
      ? {
          bg: "#26262e",
          text: "#f3f4f6",
          muted: "#9ca3af",
          border: "rgba(255,255,255,0.12)",
          assistantBg: "#33333d",
          inputBg: "#2d2d36",
        }
      : {
          bg: "#ffffff",
          text: "#1f2328",
          muted: "#6b7280",
          border: "rgba(0,0,0,0.10)",
          assistantBg: "#f1f3f5",
          inputBg: "#ffffff",
        };

    const style = document.createElement("style");
    style.id = "clippy-modern-styles";
    style.textContent = `
      #clippy-modern-root {
        --cm-accent: ${accent};
        --cm-bg: ${v.bg};
        --cm-text: ${v.text};
        --cm-muted: ${v.muted};
        --cm-border: ${v.border};
        --cm-assistant-bg: ${v.assistantBg};
        --cm-input-bg: ${v.inputBg};
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
      }
      #clippy-modern-fab {
        position: fixed; bottom: 24px; right: 24px; width: 60px; height: 60px;
        border-radius: 50%; background: var(--cm-accent); color: #fff; border: none;
        cursor: pointer; box-shadow: 0 6px 20px rgba(0,0,0,0.25); font-size: 26px;
        display: flex; align-items: center; justify-content: center;
        z-index: 2147483000; transition: transform 0.15s ease, box-shadow 0.15s ease;
      }
      #clippy-modern-fab:hover { transform: scale(1.06); box-shadow: 0 8px 26px rgba(0,0,0,0.3); }
      #clippy-modern-panel {
        position: fixed; bottom: 96px; right: 24px; width: 370px;
        max-width: calc(100vw - 32px); height: 520px; max-height: calc(100vh - 120px);
        background: var(--cm-bg); color: var(--cm-text); border: 1px solid var(--cm-border);
        border-radius: 16px; box-shadow: 0 12px 40px rgba(0,0,0,0.22); display: none;
        flex-direction: column; overflow: hidden; z-index: 2147483000; opacity: 0;
        transform: translateY(12px); transition: opacity 0.18s ease, transform 0.18s ease;
      }
      #clippy-modern-panel.cm-open { display: flex; opacity: 1; transform: translateY(0); }
      .cm-header {
        background: var(--cm-accent); color: #fff; padding: 14px 16px; display: flex;
        align-items: center; justify-content: space-between; font-weight: 600; font-size: 15px;
      }
      .cm-close {
        background: transparent; border: none; color: #fff; font-size: 22px;
        cursor: pointer; line-height: 1; padding: 0 4px; opacity: 0.85;
      }
      .cm-close:hover { opacity: 1; }
      .cm-messages {
        flex: 1; overflow-y: auto; padding: 16px; display: flex;
        flex-direction: column; gap: 10px;
      }
      .cm-bubble {
        max-width: 80%; padding: 10px 14px; border-radius: 14px; font-size: 14px;
        line-height: 1.45; word-wrap: break-word; overflow-wrap: anywhere;
      }
      .cm-bubble.cm-user {
        align-self: flex-end; background: var(--cm-accent); color: #fff;
        border-bottom-right-radius: 4px;
      }
      .cm-bubble.cm-assistant {
        align-self: flex-start; background: var(--cm-assistant-bg); color: var(--cm-text);
        border-bottom-left-radius: 4px;
      }
      .cm-bubble code {
        background: rgba(127,127,127,0.18); padding: 1px 5px; border-radius: 4px; font-size: 0.9em;
      }
      .cm-typing { display: inline-flex; gap: 4px; align-items: center; }
      .cm-typing span {
        width: 7px; height: 7px; border-radius: 50%; background: var(--cm-muted);
        animation: cm-blink 1.2s infinite both;
      }
      .cm-typing span:nth-child(2) { animation-delay: 0.2s; }
      .cm-typing span:nth-child(3) { animation-delay: 0.4s; }
      @keyframes cm-blink { 0%, 80%, 100% { opacity: 0.3; } 40% { opacity: 1; } }
      .cm-notice {
        align-self: center; font-size: 12px; color: var(--cm-muted);
        text-align: center; padding: 4px 8px;
      }
      .cm-input-row {
        display: flex; gap: 8px; padding: 12px; border-top: 1px solid var(--cm-border);
        background: var(--cm-bg);
      }
      .cm-input-row input {
        flex: 1; padding: 10px 12px; border: 1px solid var(--cm-border); border-radius: 10px;
        font-size: 14px; outline: none; background: var(--cm-input-bg); color: var(--cm-text);
      }
      .cm-input-row input:focus { border-color: var(--cm-accent); }
      .cm-input-row button.cm-send {
        width: 42px; border: none; border-radius: 10px; background: var(--cm-accent);
        color: #fff; font-size: 18px; cursor: pointer; flex-shrink: 0;
      }
      .cm-input-row button:disabled { opacity: 0.5; cursor: not-allowed; }
      .cm-attach-btn {
        width: 40px; border: none; border-radius: 10px; background: transparent;
        color: var(--cm-muted); font-size: 20px; cursor: pointer; flex-shrink: 0;
      }
      .cm-attach-btn:hover { background: rgba(127,127,127,0.15); }
      .cm-attach-row {
        display: flex; flex-wrap: wrap; gap: 4px; padding: 0 12px;
      }
      .cm-attach-row:empty { display: none; }
      #clippy-modern-root .clippy-attach-chip {
        display: inline-flex; align-items: center; gap: 4px;
        background: rgba(127,127,127,0.18); border: 1px solid var(--cm-border);
        border-radius: 10px; padding: 2px 4px 2px 7px; font-size: 11px;
        max-width: 160px; color: var(--cm-text);
      }
      #clippy-modern-root .clippy-attach-name {
        overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
      }
      #clippy-modern-root .clippy-attach-chip button {
        background: transparent; border: none; cursor: pointer; font-size: 13px;
        line-height: 1; padding: 0 2px; color: var(--cm-text); font-weight: bold;
      }
      .cm-bubble .cm-atts { font-size: 12px; opacity: 0.85; margin-top: 4px; }
    `;
    document.head.appendChild(style);
  }

  // Build the modern FAB bubble + chat panel and wire up events
  function initModern() {
    injectModernStyles();

    const title = config.name || config.agent || "Assistant";
    const root = document.createElement("div");
    root.id = "clippy-modern-root";
    root.innerHTML = `
      <div id="clippy-modern-panel" role="dialog" aria-label="${escapeHtml(title)}">
        <div class="cm-header">
          <span class="cm-title">${escapeHtml(title)}</span>
          <button class="cm-close" id="clippy-modern-close" aria-label="Chiudi">&times;</button>
        </div>
        <div class="cm-messages" id="clippy-modern-messages"></div>
        <div class="cm-attach-row" id="clippy-modern-attachments"></div>
        <div class="cm-input-row">
          <input type="file" id="clippy-modern-file" accept="image/*,application/pdf" multiple style="display:none" />
          <button class="cm-attach-btn" id="clippy-modern-attach" type="button" aria-label="Allega" title="Allega immagine o PDF">&#128206;</button>
          <input type="text" id="clippy-modern-input" placeholder="Scrivi un messaggio..." autocomplete="off" />
          <button class="cm-send" id="clippy-modern-send" aria-label="Invia">&#10148;</button>
        </div>
      </div>
      <button id="clippy-modern-fab" aria-label="Apri chat">&#128172;</button>
    `;
    document.body.appendChild(root);

    document
      .getElementById("clippy-modern-fab")
      .addEventListener("click", toggleModernPanel);
    document
      .getElementById("clippy-modern-close")
      .addEventListener("click", toggleModernPanel);
    document
      .getElementById("clippy-modern-send")
      .addEventListener("click", sendMessageModern);
    document
      .getElementById("clippy-modern-input")
      .addEventListener("keypress", function (e) {
        if (e.key === "Enter" && !e.shiftKey) {
          e.preventDefault();
          sendMessageModern();
        }
      });

    // File attachments
    const mpFile = document.getElementById("clippy-modern-file");
    document
      .getElementById("clippy-modern-attach")
      .addEventListener("click", function () {
        mpFile.click();
      });
    mpFile.addEventListener("change", function () {
      const accepted = validateAttachments(Array.from(mpFile.files));
      modernAttachments = modernAttachments.concat(accepted);
      renderAttachChips("clippy-modern-attachments", modernAttachments);
      mpFile.value = "";
    });

    // Seed the first assistant bubble with the welcome message
    const greeting = config.welcome_message
      ? config.welcome_message
      : `Ciao! Sono ${config.name || config.agent}. Come posso aiutarti?`;
    appendBubble("assistant", greeting);
  }

  // Open/close the modern chat panel
  function toggleModernPanel() {
    const panel = document.getElementById("clippy-modern-panel");
    if (!panel) return;
    modernPanelOpen = !modernPanelOpen;
    panel.classList.toggle("cm-open", modernPanelOpen);
    if (modernPanelOpen) {
      const input = document.getElementById("clippy-modern-input");
      if (input && !input.disabled) setTimeout(() => input.focus(), 50);
    }
  }

  // Append a styled message bubble (assistant rendered via formatMarkdown).
  // For user bubbles, optional attachments are listed under the text.
  function appendBubble(role, text, attachments) {
    const list = document.getElementById("clippy-modern-messages");
    if (!list) return null;
    const bubble = document.createElement("div");
    bubble.className = "cm-bubble " + (role === "user" ? "cm-user" : "cm-assistant");
    if (role === "user") {
      bubble.textContent = text || "";
      if (attachments && attachments.length) {
        const att = document.createElement("div");
        att.className = "cm-atts";
        att.textContent = attachments
          .map(function (f) {
            return (f.type.indexOf("image/") === 0 ? "🖼️ " : "📄 ") + f.name;
          })
          .join("  ");
        bubble.appendChild(att);
      }
    } else {
      bubble.innerHTML = formatMarkdown(text);
    }
    list.appendChild(bubble);
    list.scrollTop = list.scrollHeight;
    return bubble;
  }

  // Append a small centered notice (e.g. limit reached)
  function appendNotice(text) {
    const list = document.getElementById("clippy-modern-messages");
    if (!list) return;
    const el = document.createElement("div");
    el.className = "cm-notice";
    el.textContent = text;
    list.appendChild(el);
    list.scrollTop = list.scrollHeight;
  }

  // Show an animated typing indicator bubble; returns it for removal
  function showModernTyping() {
    const list = document.getElementById("clippy-modern-messages");
    if (!list) return null;
    const el = document.createElement("div");
    el.className = "cm-bubble cm-assistant";
    el.innerHTML =
      '<span class="cm-typing"><span></span><span></span><span></span></span>';
    list.appendChild(el);
    list.scrollTop = list.scrollHeight;
    return el;
  }

  // Disable the modern input once the conversation cap is hit
  function lockModernInput() {
    const input = document.getElementById("clippy-modern-input");
    const sendBtn = document.getElementById("clippy-modern-send");
    if (input) {
      input.disabled = true;
      input.placeholder = "Limite raggiunto";
    }
    if (sendBtn) sendBtn.disabled = true;
  }

  // Send flow for modern mode (mirrors classic sendMessage, different DOM)
  async function sendMessageModern() {
    const input = document.getElementById("clippy-modern-input");
    const sendBtn = document.getElementById("clippy-modern-send");
    const message = input.value.trim();

    if ((!message && modernAttachments.length === 0) || isProcessing) return;

    // Capture + clear attachments for this turn
    const sentAttachments = modernAttachments.slice();
    const userContent = await buildUserContent(message, sentAttachments);
    modernAttachments = [];
    renderAttachChips("clippy-modern-attachments", modernAttachments);

    input.value = "";
    input.disabled = true;
    sendBtn.disabled = true;
    isProcessing = true;

    conversationHistory.push({ role: "user", content: userContent });
    appendBubble("user", message, sentAttachments);

    const typing = showModernTyping();

    try {
      const response = await fetch(`${BACKEND_URL}/api/widget/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          config_id: CONFIG_ID,
          messages: conversationHistory,
        }),
      });

      if (typing) typing.remove();

      // Conversation message cap reached (server-side gate)
      if (response.status === 429) {
        appendNotice("Hai raggiunto il limite di messaggi per questa conversazione.");
        lockModernInput();
        isProcessing = false;
        return;
      }

      if (!response.ok) {
        throw new Error("API request failed");
      }

      const data = await response.json();
      const reply = data.choices[0].message.content;
      conversationHistory.push({ role: "assistant", content: reply });
      appendBubble("assistant", reply);
    } catch (error) {
      if (typing) typing.remove();
      console.error("Clippy Widget: Chat error:", error);
      appendBubble("assistant", "Ops! Si è verificato un errore. Riprova!");
    }

    isProcessing = false;

    if (isConversationLimitReached()) {
      appendNotice("Hai raggiunto il limite di messaggi per questa conversazione.");
      lockModernInput();
    } else {
      input.disabled = false;
      sendBtn.disabled = false;
      input.focus();
    }
  }

  // Initialize widget
  async function init() {
    console.log("Clippy Widget: Initializing...", {
      backendUrl: BACKEND_URL,
      configId: CONFIG_ID,
    });

    // Set CDN path BEFORE loading dependencies
    window.CLIPPY_CDN = BACKEND_URL + "/static/assets/agents/";
    console.log("Clippy Widget: CDN path set to:", window.CLIPPY_CDN);

    // Load configuration
    config = await loadConfig();
    if (!config) {
      console.error("Clippy Widget: Failed to load configuration");
      return;
    }

    // Modern mode: skip jQuery/ClippyJS entirely, render a clean chat widget.
    if (config.ui_mode === "modern") {
      console.log("Clippy Widget: Modern UI mode");
      initModern();
      return;
    }

    // Classic mode: load dependencies and initialize the retro agent (unchanged).
    loadDependencies(function () {
      initClippy();
    });
  }

  // Auto-initialize when DOM is ready
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  // Expose API
  window.ClippyWidget = {
    show: function () {
      if (config && config.ui_mode === "modern") {
        if (!modernPanelOpen) toggleModernPanel();
      } else if (clippyAgent) {
        clippyAgent.show();
      }
    },
    hide: function () {
      if (config && config.ui_mode === "modern") {
        if (modernPanelOpen) toggleModernPanel();
      } else if (clippyAgent) {
        clippyAgent.hide();
      }
    },
    speak: function (text) {
      if (config && config.ui_mode === "modern") {
        appendBubble("assistant", text);
      } else {
        showMessage(text);
      }
    },
  };
})();
