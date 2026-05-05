import { createBrowserRouter, Navigate } from "react-router-dom";
import { AppShell } from "@/components/AppShell";
import { Chat } from "@/pages/Chat";
import { TraceStub } from "@/pages/TraceStub";

// Placeholder for the Admin page — the real admin UI ships in Plan 09.
function AdminPlaceholder() {
  return (
    <div className="p-8 text-sm text-muted-foreground">
      Admin page ships in Plan 09.
    </div>
  );
}

export const router = createBrowserRouter([
  { path: "/", element: <Navigate to="/chat" replace /> },
  {
    element: <AppShell />,
    children: [
      { path: "/chat", element: <Chat /> },
      { path: "/admin", element: <AdminPlaceholder /> },
    ],
  },
  { path: "/traces/:trace_id", element: <TraceStub /> },
]);
