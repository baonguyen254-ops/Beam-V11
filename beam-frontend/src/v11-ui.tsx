import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { api } from "./api";

export type Row = Record<string, any>;
export type Send = (
  payload: Row,
) => Promise<{ ok: boolean; message: string; [key: string]: any }>;
export const fmt = (value: unknown, digits = 1) =>
  typeof value === "number" && Number.isFinite(value)
    ? value.toLocaleString("en-US", { maximumFractionDigits: digits })
    : "Not available";
export const time = (value: string | null | undefined) =>
  value ? new Date(value).toLocaleString("en-US") : "Not confirmed";
export function localDate(value?: string) {
  const d = value ? new Date(value) : new Date();
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 16);
}
export function useLive(url: string | null, refresh = 0) {
  const [data, setData] = useState<Row | null>(null),
    [error, setError] = useState("");
  useEffect(() => {
    let ended = false,
      timer: ReturnType<typeof setTimeout>;
    setData(null);
    setError("");
    async function load() {
      try {
        const response = await api(url!);
        if (!ended) {
          setData(response);
          setError("");
        }
      } catch (e) {
        if (!ended) setError((e as Error).message);
      } finally {
        if (!ended) timer = setTimeout(load, 5000);
      }
    }
    if (url) void load();
    return () => {
      ended = true;
      clearTimeout(timer);
    };
  }, [url, refresh]);
  return { data, error };
}
export function Metric({
  label,
  value,
  detail,
}: {
  label: string;
  value: ReactNode;
  detail?: ReactNode;
}) {
  return (
    <div className="v11-metric">
      <span>{label}</span>
      <strong>{value}</strong>
      {detail && <small>{detail}</small>}
    </div>
  );
}
export function Input({
  name,
  label,
  value = "",
  type = "text",
  required = true,
  min,
  max,
  step = "any",
}: {
  name: string;
  label: string;
  value?: any;
  type?: string;
  required?: boolean;
  min?: number;
  max?: number;
  step?: string;
}) {
  return (
    <label>
      {label}
      {type === "textarea" ? (
        <textarea name={name} defaultValue={value} required={required} />
      ) : (
        <input
          name={name}
          type={type}
          defaultValue={value}
          required={required}
          min={min}
          max={max}
          step={step}
        />
      )}
    </label>
  );
}
export function Modal({
  title,
  children,
  onClose,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
}) {
  const close = useRef(onClose),
    dialog = useRef<HTMLElement>(null);
  close.current = onClose;
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    dialog.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close.current();
      if (e.key === "Tab") {
        const nodes = dialog.current?.querySelectorAll<HTMLElement>(
          'button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),a[href],[tabindex="0"]',
        );
        if (!nodes?.length) {
          e.preventDefault();
          return;
        }
        const first = nodes[0],
          last = nodes[nodes.length - 1];
        if (
          e.shiftKey &&
          (document.activeElement === first ||
            document.activeElement === dialog.current)
        ) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = overflow;
      previous?.focus();
    };
  }, []);
  return createPortal(
    <div className="hw hw-overlay v11">
      <section
        ref={dialog}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="hw-dialog"
      >
        <div className="hw-heading">
          <h2>{title}</h2>
          <button type="button" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>
        {children}
      </section>
    </div>,
    document.fullscreenElement ?? document.body,
  );
}
export const stageName: Record<string, string> = {
  PRECONDITION: "Environmental preparation",
  SURGERY: "Surgical cases",
  TURNOVER: "Cleaning & turnover",
  PREPARATION: "Patient preparation",
  RECOVERY: "Recovery",
  ACTIVE: "Active",
  SETBACK: "Savings",
  PRECOOLING: "Preparing",
  ALARM: "Action needed",
};
