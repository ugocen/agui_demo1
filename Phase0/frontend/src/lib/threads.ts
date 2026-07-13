export type ThreadRecord = {
  id: string;
  agentId: string;
  agentName: string;
  title: string;
  createdAt: number;
};

const STORAGE_KEY = "phase0-threads";
const MAX_THREADS = 50;

export function listThreads(): ThreadRecord[] {
  if (typeof window === "undefined") {
    return [];
  }
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    const parsed = raw ? (JSON.parse(raw) as ThreadRecord[]) : [];
    return parsed
      .filter((thread) => typeof thread.id === "string" && thread.id.length > 0)
      .sort((a, b) => b.createdAt - a.createdAt);
  } catch {
    return [];
  }
}

export function upsertThread(record: ThreadRecord): void {
  if (typeof window === "undefined" || !record.id) {
    return;
  }
  const threads = listThreads().filter((thread) => thread.id !== record.id);
  threads.unshift(record);
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(threads.slice(0, MAX_THREADS)));
  window.dispatchEvent(new Event("phase0-threads-changed"));
}

export function updateThreadTitle(id: string, title: string): void {
  if (typeof window === "undefined" || !title.trim()) {
    return;
  }
  const threads = listThreads();
  const target = threads.find((thread) => thread.id === id);
  if (!target || target.title !== target.agentName) {
    return;
  }
  target.title = title.trim().slice(0, 60);
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(threads));
  window.dispatchEvent(new Event("phase0-threads-changed"));
}

export function newThreadId(): string {
  return crypto.randomUUID();
}
