import { leadLibrary, leadPromptOptions, library, promptOptions } from "./library";

/** The system-prompt sections the backend appends for bots with interactive UI. */
export function buildPrompts(): Record<string, string> {
  return {
    "openui_prompt.txt": library.prompt(promptOptions),
    "openui_prompt_leads.txt": leadLibrary.prompt(leadPromptOptions),
  };
}
