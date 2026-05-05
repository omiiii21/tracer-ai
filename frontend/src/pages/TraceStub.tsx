import { Link, useParams } from "react-router-dom";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export function TraceStub() {
  const { trace_id } = useParams<{ trace_id: string }>();
  return (
    <div className="max-w-2xl mx-auto p-8">
      <Link
        to="/chat"
        className="text-sm text-muted-foreground hover:underline mb-4 inline-block"
      >
        ← Back to chat
      </Link>
      <Card>
        <CardHeader>
          <CardTitle>Trace</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground mb-2">
            The trace explorer ships in Phase 4. This page reserves the route
            so chat messages can link forward.
          </p>
          <p className="text-xs font-mono bg-muted px-2 py-1 rounded inline-block">
            trace_id: {trace_id}
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
