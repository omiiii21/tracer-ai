import { Link, NavLink, Outlet } from "react-router-dom";
import { cn } from "@/lib/utils";

export function AppShell() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="h-16 border-b border-border bg-card">
        <div className="max-w-7xl mx-auto h-full px-4 flex items-center gap-6">
          <Link
            to="/chat"
            className="font-semibold text-base tracking-tight"
          >
            tracer-ai
          </Link>
          <nav className="flex gap-4 text-sm">
            <NavLink
              to="/chat"
              className={({ isActive }) =>
                cn(
                  isActive
                    ? "font-medium text-foreground"
                    : "text-muted-foreground hover:text-foreground",
                )
              }
            >
              Chat
            </NavLink>
            <NavLink
              to="/admin"
              className={({ isActive }) =>
                cn(
                  isActive
                    ? "font-medium text-foreground"
                    : "text-muted-foreground hover:text-foreground",
                )
              }
            >
              Admin
            </NavLink>
          </nav>
        </div>
      </header>
      <main>
        <Outlet />
      </main>
    </div>
  );
}
