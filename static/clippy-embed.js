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
      <div id="clippy-input-wrapper">
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

    if (!message || isProcessing) return;

    input.value = "";
    input.disabled = true;
    sendBtn.disabled = true;
    isProcessing = true;

    // Add to history
    conversationHistory.push({ role: "user", content: message });

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

    // Load dependencies and initialize
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
      if (clippyAgent) clippyAgent.show();
    },
    hide: function () {
      if (clippyAgent) clippyAgent.hide();
    },
    speak: function (text) {
      showMessage(text);
    },
  };
})();
