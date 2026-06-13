"use client";

import { FormEvent, useState } from "react";

type SubmitState =
  | { status: "idle"; message: string }
  | { status: "pending"; message: string }
  | { status: "success"; message: string }
  | { status: "error"; message: string };

export function ManualSubmitPanel() {
  const [token, setToken] = useState("");
  const [date, setDate] = useState("");
  const [state, setState] = useState<SubmitState>({
    status: "idle",
    message: "Ready",
  });

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setState({ status: "pending", message: "Dispatching" });

    try {
      const response = await fetch("/api/manual-submit", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "x-manual-submit-token": token,
        },
        body: JSON.stringify({ date }),
      });
      const payload = (await response.json()) as { ok?: boolean; error?: string };

      if (!response.ok || !payload.ok) {
        setState({
          status: "error",
          message: payload.error ?? `HTTP ${response.status}`,
        });
        return;
      }

      setState({ status: "success", message: "Queued on Lightsail" });
    } catch (error) {
      setState({
        status: "error",
        message: error instanceof Error ? error.message : "Request failed",
      });
    }
  }

  return (
    <form className="manual-submit" onSubmit={submit}>
      <div className="manual-submit-heading">
        <h3>Manual Submit</h3>
        <span className={`status-dot status-${state.status}`} aria-label={state.status} />
      </div>
      <label>
        Token
        <input
          autoComplete="off"
          onChange={(event) => setToken(event.target.value)}
          placeholder="admin token"
          type="password"
          value={token}
        />
      </label>
      <label>
        Date
        <input
          onChange={(event) => setDate(event.target.value)}
          pattern="\d{4}-\d{2}-\d{2}"
          placeholder="server today"
          type="text"
          value={date}
        />
      </label>
      <button disabled={state.status === "pending" || token.length === 0} type="submit">
        {state.status === "pending" ? "Submitting" : "Submit Now"}
      </button>
      <p className={`manual-submit-state state-${state.status}`}>{state.message}</p>
    </form>
  );
}
