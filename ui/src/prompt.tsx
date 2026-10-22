import { library, promptOptions } from "./library";

/** The system-prompt section the backend appends for bots with interactive UI. */
export function buildPrompt(): string {
  return library.prompt(promptOptions);
}
