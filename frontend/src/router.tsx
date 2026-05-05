import { createBrowserRouter, Navigate } from "react-router-dom";
import { AppShell } from "@/components/AppShell";
import { Chat } from "@/pages/Chat";
import { Admin } from "@/pages/Admin";
import { TraceStub } from "@/pages/TraceStub";

export const router = createBrowserRouter([
  { path: "/", element: <Navigate to="/chat" replace /> },
  {
    element: <AppShell />,
    children: [
      { path: "/chat", element: <Chat /> },
      { path: "/admin", element: <Admin /> },
    ],
  },
  { path: "/traces/:trace_id", element: <TraceStub /> },
]);
