/**
 * Local record of transactions this browser has seen (function + claim + hash). The contract does not store transaction
 * hashes, so this journal (plus manually pasted hashes) is how the frontend knows WHICH transaction to verify for
 * GenLayer Protocol Finality. It is a convenience index only: it never decides anything; finality is always re-verified
 * from the network. Browser storage may be empty or blocked - everything must work without it.
 */
export interface JournalEntry { claimId: number; functionName: string; hash: `0x${string}`; at: number }

interface StorageLike { getItem(k: string): string | null; setItem(k: string, v: string): void }

const KEY = "clause.txjournal.v1";
const HASH = /^0x[0-9a-fA-F]{64}$/;

export function isTxHash(v: string): v is `0x${string}` { return HASH.test(v.trim()); }

export class TxJournal {
  private memory: JournalEntry[] = [];
  constructor(private readonly storage: StorageLike | null = safeLocalStorage(), private readonly scope = "") {
    this.memory = this.load();
  }

  private key(): string { return `${KEY}:${this.scope}`; }

  private load(): JournalEntry[] {
    if (!this.storage) return [];
    try {
      const raw = this.storage.getItem(this.key());
      if (!raw) return [];
      const parsed: unknown = JSON.parse(raw);
      if (!Array.isArray(parsed)) return [];
      return parsed.filter((e): e is JournalEntry => !!e && typeof e === "object" && typeof (e as JournalEntry).claimId === "number"
        && typeof (e as JournalEntry).functionName === "string" && isTxHash(String((e as JournalEntry).hash)));
    } catch { return []; }
  }

  record(claimId: number, functionName: string, hash: `0x${string}`, at = Date.now()): void {
    this.memory = [...this.memory.filter((e) => !(e.claimId === claimId && e.functionName === functionName && e.hash === hash)), { claimId, functionName, hash, at }].slice(-500);
    try { this.storage?.setItem(this.key(), JSON.stringify(this.memory)); } catch { /* storage unavailable: memory only */ }
  }

  /** Most recent entry for the claim among the given function names. */
  find(claimId: number, functionNames: readonly string[]): JournalEntry | undefined {
    return this.memory.filter((e) => e.claimId === claimId && functionNames.includes(e.functionName)).sort((a, b) => b.at - a.at)[0];
  }

  all(): JournalEntry[] { return [...this.memory]; }
}

function safeLocalStorage(): StorageLike | null {
  try { return typeof localStorage !== "undefined" ? localStorage : null; } catch { return null; }
}
