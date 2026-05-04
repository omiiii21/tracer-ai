import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export default function App() {
  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-8">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>Hello tracer-ai</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-muted-foreground mb-4">
            Phase 2 skeleton — RAG features land in Phase 3.
          </p>
          <Button onClick={() => console.log("phase 2 alive")}>Test</Button>
        </CardContent>
      </Card>
    </div>
  );
}
