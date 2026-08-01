import { Compass, Home } from "lucide-react";
import { Link, useLocation } from "react-router-dom";

import { Card } from "../components/ui/card";

const destinations = [
  { to: "/", label: "Command Deck", hint: "Signals and live operations" },
  { to: "/lineage", label: "Lineage Explorer", hint: "Whole-namespace topology" },
  { to: "/memory", label: "Memory", hint: "Post-mortems the agent wrote" },
  { to: "/compare", label: "Compare", hint: "Cold versus memory-assisted runs" },
];

export default function NotFound() {
  const { pathname } = useLocation();
  return (
    <div className="mx-auto flex min-h-[calc(100vh-72px)] max-w-3xl items-center justify-center p-8">
      <Card className="relative w-full overflow-hidden p-10">
        <div className="absolute -right-16 -top-20 size-72 rounded-full bg-brand/10 blur-3xl" />
        <div className="relative">
          <span className="grid size-11 place-items-center rounded-xl border border-brand/35 bg-brand/10 text-brand">
            <Compass className="size-5" aria-hidden="true" />
          </span>
          <p className="section-label mt-8">Error 404</p>
          <h1 className="mt-2 text-3xl font-semibold tracking-[-.035em]">This route does not exist</h1>
          <p className="mt-4 max-w-xl text-sm leading-relaxed text-fg-muted">
            Nothing is served at{" "}
            <code className="rounded bg-bg/60 px-1.5 py-0.5 font-mono text-xs text-fg">{pathname}</code>.
            If you followed a link to a run that was cleared by a full reset, its record is gone —
            reruns are listed on the Command Deck.
          </p>
          <div className="mt-8 grid gap-2 sm:grid-cols-2">
            {destinations.map((item) => (
              <Link
                key={item.to}
                to={item.to}
                className="rounded-lg border border-border bg-surface px-4 py-3 transition-colors hover:border-border-strong hover:bg-surface-2 focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-bg"
              >
                <span className="block text-sm font-semibold text-fg">{item.label}</span>
                <span className="mt-0.5 block text-xs text-fg-muted">{item.hint}</span>
              </Link>
            ))}
          </div>
          <Link
            to="/"
            className="mt-8 inline-flex items-center gap-2 rounded-lg bg-brand px-4 py-2.5 text-sm font-semibold text-bg transition-opacity hover:opacity-90 focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-bg"
          >
            <Home className="size-4" aria-hidden="true" />
            Back to Command Deck
          </Link>
        </div>
      </Card>
    </div>
  );
}
