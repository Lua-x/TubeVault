import { Dialog } from "@/components/ui/Dialog";
import { ProgressBar } from "@/components/ui/ProgressBar";

export function RestartingDialog({ open, message }: { open: boolean; message?: string }) {
  return (
    <Dialog open={open} onClose={() => undefined} title="TubeVault startet neu …">
      <p className="text-[15px] text-secondary">
        {message ?? "Einen Moment, die Seite lädt gleich neu."}
      </p>
      <ProgressBar value={null} className="mt-4" />
    </Dialog>
  );
}
