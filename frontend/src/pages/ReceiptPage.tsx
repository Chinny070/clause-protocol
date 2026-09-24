import { Link, useParams } from "react-router-dom";
import { loadReceipt } from "../app/data";
import { useAsync } from "../app/useAsync";
import { Copyable } from "../ui/kit";
import { ReceiptView } from "../ui/receipt";
import { AsyncBoundary, NeedsContract, NotFoundBox, idParam } from "./common";
import type { ClauseReader } from "../contract/reader";

function Body({ reader, id }: { reader: ClauseReader; id: number }) {
  const q = useAsync(() => loadReceipt(reader, id), [reader, id]);
  return (
    <AsyncBoundary loading={q.loading} error={q.error} what="Reading Resolution Receipt">
      {!q.data ? <NotFoundBox what="Claim" /> : (
        <div className="stack">
          <div className="row noprint" style={{ justifyContent: "space-between" }}>
            <Link to={`/claim/${id}`} className="btn small secondary">Back to claim</Link>
            <span className="row"><button type="button" className="btn small secondary" onClick={() => window.print()}>Print / save PDF</button>
              <span className="small">Shareable link: <Copyable value={typeof window !== "undefined" ? window.location.href : ""} label="receipt link" /></span></span>
          </div>
          <ReceiptView r={q.data} />
        </div>
      )}
    </AsyncBoundary>
  );
}

export function ReceiptPage() {
  const { id } = useParams();
  const n = idParam(id);
  if (n === null) return <NotFoundBox what="Claim" />;
  return <NeedsContract what={`Resolution Receipt ${n}`}>{(reader) => <Body reader={reader} id={n} />}</NeedsContract>;
}
