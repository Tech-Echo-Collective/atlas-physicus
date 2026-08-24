interface GlobalViewControlProps {
  isGlobalView: boolean;
  onReturn: () => void;
}

export function GlobalViewControl({
  isGlobalView,
  onReturn,
}: GlobalViewControlProps) {
  return (
    <button
      className="global-view-control"
      type="button"
      data-global={isGlobalView}
      onClick={onReturn}
      aria-label="Return to Global View and reset the map"
      title="Reset map to the global atlas"
    >
      <span aria-hidden="true">◯</span>
    </button>
  );
}
