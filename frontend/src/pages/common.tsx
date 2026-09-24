import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { useClause } from "../app/context";
import type { ClauseReader } from "../contract/reader";
import { ContractReadError } from "../contract/reader";
import { ErrorBox, Loading } from "../ui/kit";

/** Renders children only when a validated contract address exists; otherwise explains the situation honestly. */
export function NeedsContract({ children, what }: { children: (reader: ClauseReader) => ReactNode; what: string }) {
  const { reader, config } = useClause();
  if (!reader) {
    return (
      <section className="plate" aria-labelledby="nc-h">
        <h2 id="nc-h">{what}</h2>
        <p>{config.status === "not-configured" ? "This build has no canonical CLAUSE contract address yet, so there is nothing to read." : "The contract configuration is not valid, so nothing can be read."}</p>
        <p className="muted">Nothing on this page is mocked or made up. Once the canonical StudioNet address is configured, this page reads it live with no wallet required.</p>
        <p><Link className="btn secondary" to="/">Back to the overview</Link> <Link className="btn secondary" to="/limits">V1 limitations</Link></p>
      </section>
    );
  }
  return <>{children(reader)}</>;
}

export function AsyncBoundary({ loading, error, children, what = "Reading the contract" }: { loading: boolean; error?: Error; children: ReactNode; what?: string }) {
  if (error) {
    const kind = error instanceof ContractReadError ? error.kind : "contract-read-failed";
    const title = kind === "rpc-unavailable" ? "RPC unavailable" : kind === "malformed" ? "Unexpected contract response" : "Contract read failed";
    return <ErrorBox title={title} message={kind === "rpc-unavailable" ? "The StudioNet RPC could not be reached. Nothing was changed. Retry shortly." : "The contract did not return what the frozen interface promises."} technical={error.message} />;
  }
  if (loading) return <Loading what={what} />;
  return <>{children}</>;
}

export function NotFoundBox({ what }: { what: string }) {
  return (
    <section className="plate" role="status">
      <h2>{what} not found</h2>
      <p>The contract has no record with that id. Ids start at 1 and are assigned in order.</p>
      <Link className="btn secondary" to="/explore">Browse warranties</Link>
    </section>
  );
}

export function idParam(v: string | undefined): number | null {
  if (!v || !/^\d+$/.test(v)) return null;
  const n = Number(v);
  return Number.isSafeInteger(n) && n > 0 ? n : null;
}
