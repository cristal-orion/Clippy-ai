import { Renderer, type ActionEvent, type ParseResult } from "@openuidev/react-lang";
import { Component, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { webUrl } from "./inline";
import { LeadContext, leadLibrary, type LeadOptions } from "./library";
import css from "./styles.css";

type MountOptions = {
  /** Accent color of the widget (buttons, links). */
  accent?: string;
  dark?: boolean;
  /** A button asked to send a message to the assistant. */
  onMessage?: (text: string) => void;
  /** The reply could not be rendered as UI; show it as plain text instead. */
  onFallback?: () => void;
  /** Lead form settings; without them LeadForm says the form is unavailable. */
  lead?: LeadOptions;
};

function injectStyles() {
  if (document.getElementById("clippy-ui-styles")) return;
  const style = document.createElement("style");
  style.id = "clippy-ui-styles";
  style.textContent = css;
  document.head.appendChild(style);
}

/**
 * The OpenUI Lang program inside a model reply, or null when the reply is
 * ordinary text. Models sometimes wrap the program in a code fence or put a
 * sentence before it; both are tolerated.
 */
function extractProgram(text: unknown): string | null {
  if (typeof text !== "string") return null;
  let t = text.trim();
  const fenced = /^```[\w-]*[ \t]*\n([\s\S]*?)\n?```$/.exec(t);
  if (fenced) t = fenced[1].trim();
  const start = t.search(/^root\s*=/m);
  if (start < 0) return null;
  return t.slice(start).replace(/\n```\s*$/, "").trim();
}

class Boundary extends Component<{ onError: () => void; children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch() {
    this.props.onError();
  }
  render() {
    return this.state.failed ? null : this.props.children;
  }
}

/**
 * Render a model reply as interactive UI inside `el`. Returns false (and
 * renders nothing) when the reply is not an OpenUI program; onFallback fires
 * later if a program turns out to be unrenderable.
 */
function mount(el: HTMLElement, text: string, options: MountOptions = {}): boolean {
  const program = extractProgram(text);
  if (!program) return false;
  injectStyles();
  el.classList.add("cui-root");
  el.classList.toggle("cui-dark", !!options.dark);
  if (options.accent) el.style.setProperty("--cui-accent", options.accent);

  const root = createRoot(el);
  let failed = false;
  const fail = () => {
    if (failed) return;
    failed = true;
    setTimeout(() => {
      root.unmount();
      el.classList.remove("cui-root", "cui-dark");
      options.onFallback?.();
    }, 0);
  };
  const onParseResult = (result: ParseResult | null) => {
    if (!result || !result.root) fail();
  };
  const onAction = (event: ActionEvent) => {
    if (event.type === "continue_conversation") {
      const message = (event.humanFriendlyMessage || "").trim();
      if (message) options.onMessage?.(message);
    } else if (event.type === "open_url") {
      const url = webUrl(event.params?.url);
      if (url) window.open(url, "_blank", "noopener,noreferrer");
    }
  };

  root.render(
    <Boundary onError={fail}>
      <LeadContext.Provider value={options.lead ?? null}>
        <Renderer response={program} library={leadLibrary} isStreaming={false} onAction={onAction} onParseResult={onParseResult} onError={() => {}} />
      </LeadContext.Provider>
    </Boundary>,
  );
  return true;
}

declare global {
  interface Window {
    ClippyUI?: { version: string; mount: typeof mount; extractProgram: typeof extractProgram };
  }
}

window.ClippyUI = { version: "1", mount, extractProgram };
window.dispatchEvent(new Event("clippy-ui-ready"));
