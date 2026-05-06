import { createBrowserRouter, Navigate } from "react-router-dom";

import { AppShell } from "@/components/AppShell";
import { Admin } from "@/pages/Admin";
import { Chat } from "@/pages/Chat";
import { Dashboard } from "@/pages/Dashboard";
import { TraceDetail } from "@/pages/TraceDetail";

export const router = createBrowserRouter([
  { path: "/", element: <Navigate to="/chat" replace /> },
  {
    element: <AppShell />,
    children: [
      { path: "/chat", element: <Chat /> },
      { path: "/admin", element: <Admin /> },
      { path: "/dashboard", element: <Dashboard /> },
      { path: "/dashboard/traces/:trace_id", element: <TraceDetail /> },
    ],
  },
]);
