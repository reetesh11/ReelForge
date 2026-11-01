export function LicenceBanner({ warning }: { warning: string }) {
  return (
    <div role="status" className="notice amber">
      {warning}
    </div>
  );
}
