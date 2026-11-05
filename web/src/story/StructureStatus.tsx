import type { Job } from "@/api/story";

export function StructureStatus({ job, error, onRetry }: { job: Job | undefined; error: string | null; onRetry: () => void }) {
  if (error) {
    return (
      <div role="alert" className="notice error">
        <p>{error}</p>
        <button type="button" className="btn btn-secondary" onClick={onRetry}>
          Try again
        </button>
      </div>
    );
  }
  if (!job) return null;
  if (job.status === "failed") {
    return (
      <div role="alert" className="notice error">
        <p>{job.error ?? "Structuring failed."}</p>
        <button type="button" className="btn btn-secondary" onClick={onRetry}>
          Try again
        </button>
      </div>
    );
  }
  if (job.status === "cancelled") {
    return (
      <div className="notice">
        <p>Structuring was cancelled.</p>
        <button type="button" className="btn btn-secondary" onClick={onRetry}>
          Try again
        </button>
      </div>
    );
  }
  if (job.status === "queued" || job.status === "running") {
    return (
      <p role="status" className="meta">
        {job.message ?? "Working"} ({job.progress}%)
      </p>
    );
  }
  return null;
}
