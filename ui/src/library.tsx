import {
  action,
  createLibrary,
  defineComponent,
  tagSchemaId,
  useFormName,
  useIsStreaming,
  useTriggerAction,
  type PromptOptions,
} from "@openuidev/react-lang";
import { createContext, useContext, useState, type FormEvent } from "react";
import { z } from "zod/v4";
import { inline, webUrl } from "./inline";

/*
 * The components a Clippy bot may answer with. The set is deliberately small:
 * the widget is a narrow chat panel on a client's site, so answers are text,
 * tables, cards and a few buttons — no maps, drawings or embedded pages.
 * Prop order is the positional argument order the model writes.
 */

const node = z.any();
tagSchemaId(node, "Node");
const children = z.array(node);
const tone = z.enum(["neutral", "info", "success", "warning", "danger"]);

const isElement = (value: unknown, typeName?: string) =>
  !!value &&
  typeof value === "object" &&
  (value as { type?: unknown }).type === "element" &&
  (!typeName || (value as { typeName?: unknown }).typeName === typeName);

const Col = defineComponent({
  name: "Col",
  props: z.object({ children }),
  description: "Vertical stack. Every answer's root is a Col.",
  component: ({ props, renderNode }) => <div className="cui-col">{renderNode(props.children)}</div>,
});

const Row = defineComponent({
  name: "Row",
  props: z.object({ children }),
  description: "Items side by side; wraps on narrow screens. Use it for Badges, Stats or Buttons.",
  component: ({ props, renderNode }) => <div className="cui-row">{renderNode(props.children)}</div>,
});

const Card = defineComponent({
  name: "Card",
  props: z.object({ children, highlight: z.boolean().optional() }),
  description: "Bordered box for one item (an option, a summary). highlight marks the recommended one.",
  component: ({ props, renderNode }) => (
    <div className={props.highlight ? "cui-card cui-card-highlight" : "cui-card"}>{renderNode(props.children)}</div>
  ),
});

const Title = defineComponent({
  name: "Title",
  props: z.object({ text: z.string(), size: z.enum(["sm", "md", "lg"]).optional() }),
  description: "Heading: sm inside a Card, md for a section, lg for the answer's title.",
  component: ({ props }) => (
    <div role="heading" aria-level={props.size === "lg" ? 2 : props.size === "sm" ? 4 : 3} className={`cui-title cui-title-${props.size ?? "md"}`}>
      {inline(props.text)}
    </div>
  ),
});

const Text = defineComponent({
  name: "Text",
  props: z.object({
    text: z.union([z.string(), children]),
    size: z.enum(["sm", "md"]).optional(),
    muted: z.boolean().optional(),
  }),
  description: "Paragraph; supports **bold**, *italic*, `code` and [links](https://…). muted greys it out for side notes.",
  component: ({ props, renderNode }) => (
    <p className={`cui-text cui-text-${props.size ?? "md"}${props.muted ? " cui-muted" : ""}`}>
      {Array.isArray(props.text)
        ? props.text.map((part, i) => (isElement(part) ? <span key={i}>{renderNode(part)}</span> : <span key={i}>{inline(part)}</span>))
        : inline(props.text)}
    </p>
  ),
});

const ListItem = defineComponent({
  name: "ListItem",
  props: z.object({ title: z.string(), description: z.string().optional() }),
  description: "A List entry with a bold title and an optional description.",
  component: ({ props }) => (
    <>
      <span className="cui-li-title">{inline(props.title)}</span>
      {props.description ? <span className="cui-li-desc">{inline(props.description)}</span> : null}
    </>
  ),
});

const List = defineComponent({
  name: "List",
  props: z.object({ items: children, ordered: z.boolean().optional() }),
  description: "Bulleted list (numbered if ordered). items are strings or ListItem.",
  component: ({ props, renderNode }) => {
    const Tag = props.ordered ? "ol" : "ul";
    const items = Array.isArray(props.items) ? props.items : [];
    return (
      <Tag className="cui-list">
        {items.map((item, i) => (
          <li key={i}>{isElement(item) ? renderNode(item) : inline(item)}</li>
        ))}
      </Tag>
    );
  },
});

const Badge = defineComponent({
  name: "Badge",
  props: z.object({ text: z.string(), tone: tone.optional() }),
  description: "Small pill for a short fact: a deadline, a status, a category.",
  component: ({ props }) => <span className={`cui-badge cui-tone-${props.tone ?? "neutral"}`}>{props.text}</span>,
});

const Stat = defineComponent({
  name: "Stat",
  props: z.object({ label: z.string(), value: z.string(), hint: z.string().optional() }),
  description: 'A key figure: a small label above a large value, e.g. Stat("Contributo", "fino al 50%").',
  component: ({ props }) => (
    <div className="cui-stat">
      <span className="cui-stat-label">{props.label}</span>
      <span className="cui-stat-value">{props.value}</span>
      {props.hint ? <span className="cui-stat-hint">{props.hint}</span> : null}
    </div>
  ),
});

const Link = defineComponent({
  name: "Link",
  props: z.object({ text: z.string(), url: z.string() }),
  description: "Opens an http(s) URL in a new tab. Only for real URLs you were given or found.",
  component: ({ props }) => {
    const href = webUrl(props.url);
    if (!href) return <span>{props.text}</span>;
    return (
      <a className="cui-link" href={href} target="_blank" rel="noopener noreferrer">
        {props.text || new URL(href).hostname} ↗
      </a>
    );
  },
});

const NUMERIC = /^[-+−]?[€$£]?\s?\d[\d.,]*\s?(%|€|k|K|M|mln|mld)?$/;

const Table = defineComponent({
  name: "Table",
  props: z.object({ columns: z.array(z.string()), rows: z.array(z.array(z.any())) }),
  description: "Comparison table: each row lists its cells in column order; keep to 2-4 columns with short cells. A cell may be a Badge or Link.",
  component: ({ props, renderNode }) => {
    const columns = Array.isArray(props.columns) ? props.columns.map((c) => String(c ?? "")) : [];
    const rows = (Array.isArray(props.rows) ? props.rows : []).filter(Array.isArray) as unknown[][];
    const numeric = columns.map((_, c) => {
      const cells = rows.map((r) => r[c]).filter((v) => v != null && v !== "");
      return cells.length > 0 && cells.every((v) => typeof v === "number" || (typeof v === "string" && NUMERIC.test(v.trim())));
    });
    const cell = (value: unknown) =>
      isElement(value) ? renderNode(value) : typeof value === "number" ? value.toLocaleString("it-IT") : inline(value);
    return (
      <div className="cui-table-wrap">
        <table className="cui-table">
          <thead>
            <tr>
              {columns.map((c, i) => (
                <th key={i} className={numeric[i] ? "cui-num" : undefined}>
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, r) => (
              <tr key={r}>
                {columns.map((_, c) => (
                  <td key={c} className={numeric[c] ? "cui-num" : undefined}>
                    {cell(row[c])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  },
});

type Plan = Parameters<ReturnType<typeof useTriggerAction>>[2];

const Button = defineComponent({
  name: "Button",
  props: z.object({
    label: z.string(),
    action: action().optional(),
    variant: z.enum(["primary", "secondary"]).optional(),
  }),
  description: "A next step. With no action it sends its label to the assistant.",
  component: ({ props }) => {
    const trigger = useTriggerAction();
    const formName = useFormName();
    const streaming = useIsStreaming();
    const label = String(props.label ?? "");
    return (
      <button
        type="button"
        className={`cui-button cui-button-${props.variant ?? "primary"}`}
        disabled={streaming}
        onClick={() => void (props.action ? trigger(label, formName, props.action as Plan) : trigger(label, formName))}
      >
        {label}
      </button>
    );
  },
});

const Divider = defineComponent({
  name: "Divider",
  props: z.object({}),
  description: "A thin separator line.",
  component: () => <hr className="cui-divider" />,
});

// ── Lead form ──────────────────────────────────────────────────────────────

export type LeadValues = {
  nome: string;
  azienda: string;
  email: string;
  telefono: string;
  note: string;
  consenso: boolean;
  website: string; // honeypot
};

export type LeadOptions = {
  consentText: string;
  policyUrl?: string;
  submit: (values: LeadValues) => Promise<{ ok: boolean; error?: string }>;
};

/** Provided by the widget: where the form goes and what the visitor agrees to. */
export const LeadContext = createContext<LeadOptions | null>(null);

const EMAIL = /^[^\s@,;:<>"']+@[^\s@,;:<>"']+\.[^\s@,;:<>"']{2,}$/;

function LeadFormView({ title, note, company }: { title?: string; note?: string; company?: string }) {
  const lead = useContext(LeadContext);
  const [values, setValues] = useState<LeadValues>({
    nome: "", azienda: company ?? "", email: "", telefono: "", note: note ?? "", consenso: false, website: "",
  });
  const [state, setState] = useState<"idle" | "sending" | "sent">("idle");
  const [error, setError] = useState("");
  const set = (key: keyof LeadValues) => (e: { target: { value: string; checked?: boolean; type?: string } }) =>
    setValues((v) => ({ ...v, [key]: e.target.type === "checkbox" ? !!e.target.checked : e.target.value }));

  if (!lead) return <p className="cui-text cui-text-sm cui-muted">Il modulo contatti non è disponibile in questa chat.</p>;
  if (state === "sent") {
    return (
      <div className="cui-card cui-form-done" role="status">
        <div className="cui-title cui-title-sm">✅ Richiesta inviata</div>
        <p className="cui-text cui-text-sm">Grazie{values.nome ? `, ${values.nome.split(" ")[0]}` : ""}! Ti ricontatteremo al più presto.</p>
      </div>
    );
  }

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (values.nome.trim().length < 2) return setError("Inserisci nome e cognome.");
    if (!EMAIL.test(values.email.trim())) return setError("Controlla l'indirizzo email.");
    if (!values.consenso) return setError("Per inviare la richiesta serve il consenso al trattamento dei dati.");
    setError("");
    setState("sending");
    const result = await lead.submit(values).catch(() => ({ ok: false, error: "Invio non riuscito, riprova." }));
    if (result.ok) setState("sent");
    else {
      setState("idle");
      setError(result.error || "Invio non riuscito, riprova.");
    }
  };

  const sending = state === "sending";
  const policy = webUrl(lead.policyUrl);
  return (
    <form className="cui-card cui-form" onSubmit={onSubmit} noValidate>
      {title ? <div className="cui-title cui-title-sm">{title}</div> : null}
      <label className="cui-field">
        <span>Nome e cognome *</span>
        <input type="text" autoComplete="name" value={values.nome} onChange={set("nome")} disabled={sending} required />
      </label>
      <label className="cui-field">
        <span>Azienda</span>
        <input type="text" autoComplete="organization" value={values.azienda} onChange={set("azienda")} disabled={sending} />
      </label>
      <div className="cui-row cui-fields">
        <label className="cui-field">
          <span>Email *</span>
          <input type="email" autoComplete="email" value={values.email} onChange={set("email")} disabled={sending} required />
        </label>
        <label className="cui-field">
          <span>Telefono</span>
          <input type="tel" autoComplete="tel" value={values.telefono} onChange={set("telefono")} disabled={sending} />
        </label>
      </div>
      <label className="cui-field">
        <span>Di cosa hai bisogno</span>
        <textarea rows={3} value={values.note} onChange={set("note")} disabled={sending} />
      </label>
      <label className="cui-hp" aria-hidden="true">
        Sito web <input type="text" tabIndex={-1} autoComplete="off" value={values.website} onChange={set("website")} />
      </label>
      <label className="cui-consent">
        <input type="checkbox" checked={values.consenso} onChange={set("consenso")} disabled={sending} />
        <span>
          {inline(lead.consentText)} *
          {policy ? (
            <>
              {" "}
              <a href={policy} target="_blank" rel="noopener noreferrer">Informativa privacy</a>
            </>
          ) : null}
        </span>
      </label>
      {error ? <p className="cui-form-error" role="alert">{error}</p> : null}
      <div className="cui-row">
        <button type="submit" className="cui-button cui-button-primary" disabled={sending}>
          {sending ? "Invio in corso…" : "Invia richiesta"}
        </button>
      </div>
    </form>
  );
}

const LeadForm = defineComponent({
  name: "LeadForm",
  props: z.object({ title: z.string().optional(), note: z.string().optional(), company: z.string().optional() }),
  description:
    "The contact form: name, company, email, phone, a note and the privacy consent. note pre-fills a short summary of what the user needs; company pre-fills their company if known.",
  component: ({ props }) => <LeadFormView title={props.title} note={props.note} company={props.company} />,
});

const baseComponents = [Col, Row, Card, Divider, Title, Text, List, ListItem, Badge, Stat, Link, Table, Button];
const baseGroups = [
  { name: "Layout", components: ["Col", "Row", "Card", "Divider"] },
  { name: "Text", components: ["Title", "Text", "List", "ListItem", "Badge", "Stat", "Link"] },
  { name: "Data and actions", components: ["Table", "Button"] },
];

export const library = createLibrary({ root: "Col", components: baseComponents, componentGroups: baseGroups });

/** Bots that collect leads: the same components plus LeadForm. The widget renders with this one. */
export const leadLibrary = createLibrary({
  root: "Col",
  components: [...baseComponents, LeadForm],
  componentGroups: [...baseGroups, { name: "Contact", components: ["LeadForm"] }],
});

const exampleCompare = `root = Col([intro, table, note, next])
intro = Text("Ecco i **tre piani** a confronto:")
table = Table(["Piano", "Prezzo", "Utenti"], [["Base", "19 €/mese", "1"], ["Team", "49 €/mese", "5"], [Badge("Business", "info"), "99 €/mese", "Illimitati"]])
note = Text("Tutti i piani includono 14 giorni di prova gratuita.", "sm", true)
next = Row([Button("Quale piano mi consigli?", @ToAssistant("Quale piano mi consigli per un team di 4 persone?")), Button("Vedi il listino", @OpenUrl("https://example.com/prezzi"), "secondary")])`;

const exampleCards = `root = Col([intro, c1, c2, next])
intro = Text("Ho trovato **2 corsi** adatti a te:")
c1 = Card([Row([Title("Excel avanzato", "sm"), Badge("Iscrizioni aperte", "success")]), Text("Tabelle pivot, formule e automazioni per l'ufficio.", "sm"), Row([Stat("Durata", "16 ore"), Stat("Costo", "240 €")]), Link("Programma completo", "https://example.com/corsi/excel")], true)
c2 = Card([Row([Title("Contabilità di base", "sm"), Badge("Ultimi posti", "warning")]), Text("Partita doppia e bilancio per chi parte da zero.", "sm"), Row([Stat("Durata", "24 ore"), Stat("Costo", "320 €")])])
next = Row([Button("Mi interessa Excel avanzato"), Button("Vorrei parlare con un consulente", @ToAssistant("Vorrei parlare con un consulente"), "secondary")])`;

const exampleChat = `root = Col([Text("Certo! Per aiutarti meglio: in quale **regione** ha sede la tua azienda?")])`;

const exampleLead = `root = Col([intro, form])
intro = Text("Perfetto! Lasciami i tuoi recapiti e un consulente ti ricontatterà per la **consulenza gratuita**.")
form = LeadForm("Richiedi la consulenza gratuita", "Interesse per il piano Team per 4 persone, con avvio previsto a gennaio.", "Studio Bianchi")`;

/** Appended to a bot's own instructions when its interactive UI is on. */
export const promptOptions: PromptOptions = {
  preamble:
    "RESPONSE FORMAT — The chat widget renders your replies as interactive UI. Your persona, goals and rules above still apply; this section only defines how every reply is written.",
  bindings: false,
  toolCalls: false,
  builtinFunctions: false,
  additionalRules: [
    "Every reply is an OpenUI Lang program starting with `root = Col([...])`, each referenced name defined on its own line. Output only the program: no Markdown code fences, no text before or after it.",
    "Write all visible text in the language of the conversation (usually Italian).",
    "The widget is a narrow chat panel, about 360px wide: keep answers compact and scannable. A short Text first, then the blocks that carry the content. At most 4 Cards per reply.",
    "Small talk, a question to the user or a short answer is just root = Col([Text(\"...\")]). Don't build cards or tables for a one-line reply.",
    "Use Table to compare a few options on the same attributes; one Card per item when each has several facts (name, who it is for, amount, deadline); Badge for short facts like a deadline or status; Stat for a key figure; List for steps or requirements.",
    "End with 1-3 Buttons for the most useful next steps when there are any. @ToAssistant(\"...\") sends a short first-person message, as if the user typed it. @OpenUrl only for real http(s) URLs you were given or found.",
    "Never invent URLs, figures or deadlines. Cite sources with Link.",
    "There are no input fields: when you need information, ask for it in a Text and let the user type the answer.",
  ],
  examples: [
    `Example 1: Comparing options with a Table and next steps:\n\n${exampleCompare}`,
    `Example 2: A few options as Cards with facts, a source link and next steps:\n\n${exampleCards}`,
    `Example 3: A simple conversational reply:\n\n${exampleChat}`,
  ],
};

/** For bots with lead recipients: the contact form replaces asking for details in chat. */
export const leadPromptOptions: PromptOptions = {
  ...promptOptions,
  additionalRules: [
    ...(promptOptions.additionalRules ?? []),
    "LeadForm is the only way to collect contact details. When the user wants to be contacted, book a call or a free consultation, or your instructions say to collect name, email or phone, show LeadForm instead: never ask for name, email or phone in the chat, not even one at a time.",
    "Pre-fill LeadForm's note with a one- or two-sentence summary of what the user needs (goal, budget, place, options that interested them), written as the user would, and company if you know it. Put a short Text before it.",
    "At most one LeadForm per reply. Once the conversation says the form was sent, don't show it again unless the user asks.",
  ],
  examples: [
    ...(promptOptions.examples ?? []),
    `Example 4: The user asks to be contacted:\n\n${exampleLead}`,
  ],
};
