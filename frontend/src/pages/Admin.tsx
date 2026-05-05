// Minimal Admin route shell — full implementation lands in Task 2 of plan 03-09.
// Kept as a named export `Admin` so router.tsx imports cleanly.
export function Admin() {
  return (
    <div className="max-w-7xl mx-auto p-8 space-y-6">
      <h1 className="text-2xl font-semibold tracking-tight">Corpus</h1>
      <p className="text-sm text-muted-foreground">Loading admin UI…</p>
    </div>
  );
}
