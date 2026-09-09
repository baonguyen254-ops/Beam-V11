import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
  type FormEvent,
} from "react";
import { api } from "./api";
import "./hospital.css";
type User = { id: string; username: string; role: string };
const Identity = createContext<User | null>(null);
export const useIdentity = () => useContext(Identity);
export default function AuthGate({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<{
    user: User | null;
    needs_setup: boolean;
    demo_available?: boolean;
  } | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const refresh = () =>
    api("/api/session")
      .then(setSession)
      .catch((e) => setError(e.message));
  useEffect(() => {
    void refresh();
    const expired = () => {
      setSession(previous => ({ user: null, needs_setup: false, demo_available: previous?.demo_available }));
    };
    window.addEventListener("beam-auth-expired", expired);
    return () => window.removeEventListener("beam-auth-expired", expired);
  }, []);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      setSession(
        await api(
          session?.needs_setup ? "/api/setup" : "/api/login",
          Object.fromEntries(new FormData(event.currentTarget)),
        ),
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  if (session?.user)
    return (
      <Identity.Provider value={session.user}>
        <div className="hw-identity">
          <span>
            BEAM Hospital Intelligence · {session.demo_available ? "Demo presenter" : session.user.username} ·{" "}
            {session.user.role}
          </span>
          <button
            onClick={() => {
              void api("/api/logout", {})
                .then(() => setSession({ ...session, user: null }))
                .catch((e) => setError(e.message));
            }}
          >
            
            Sign out
          </button>
          {error && <span role="alert">{error}</span>}
        </div>
        {children}
      </Identity.Provider>
    );
  if (session?.demo_available) return (
    <div className="hw-auth hw">
      <section className="hw-panel">
        <span className="hw-eyebrow">BEAM v11.1 / ENGLISH DEMO</span>
        <h1>Your hospital demo is ready</h1>
        <p>Explore the original floorplan with simulated surgical cases, patients, teams, equipment, predictions and a full year of energy history.</p>
        <p className="hw-note">All operational and clinical data is synthetic. This workspace runs locally and is separate from connected hospital data.</p>
        {error && <p className="hw-error" role="alert">{error}</p>}
        <button className="hw-primary" disabled={busy} onClick={async () => {
          setBusy(true); setError("");
          try { setSession(await api("/api/demo/login", {})); }
          catch(e) { setError((e as Error).message); }
          finally { setBusy(false); }
        }}>{busy ? "Opening demo…" : "Open demo dashboard"}</button>
      </section>
    </div>
  );
  return (
    <div className="hw-auth hw">
      <form className="hw-panel" onSubmit={submit}>
        <span className="hw-eyebrow">BEAM / HOSPITAL INTELLIGENCE</span>
        <h1>
          {session?.needs_setup
            ? "Create an administrator"
            : "Sign in to BEAM"}
        </h1>
        <p>
          
          Manage operating rooms, clinical resources and energy in one workspace.
        </p>
        {session?.needs_setup && (
          <>
            <p className="hw-note">
              
              Read the setup key from the server's data directory, shown in the startup log. There is no default account or password.
            </p>
            <label>
              
              Setup key
              <input name="key" required autoComplete="off" />
            </label>
          </>
        )}
        <label>
          
          Username
          <input
            name="username"
            required
            minLength={3}
            maxLength={80}
            autoComplete="username"
          />
        </label>
        <label>
          
          Password
          <input
            name="password"
            type="password"
            required
            minLength={12}
            maxLength={256}
            autoComplete={
              session?.needs_setup ? "new-password" : "current-password"
            }
          />
        </label>
        {error && (
          <p className="hw-error" role="alert">
            {error}
          </p>
        )}
        <button className="hw-primary" disabled={busy || !session}>
          {busy
            ? "Signing in…"
            : session?.needs_setup
              ? "Create administrator account"
              : "Sign in"}
        </button>
        {!session && (
          <button type="button" onClick={() => void refresh()}>
            
            Retry connection
          </button>
        )}
      </form>
    </div>
  );
}
