import { Icon, type IconName } from "@/components/icons";

type Props = {
  label: string;
  icon: IconName;
  onClick?: () => void;
  disabled?: boolean;
  tone?: "default" | "danger";
  type?: "button" | "submit";
  pressed?: boolean;
};

/** Icon-only button: the label is both the accessible name and the tooltip. */
export function IconButton({ label, icon, onClick, disabled, tone = "default", type = "button", pressed }: Props) {
  return (
    <button
      type={type}
      className={`btn btn-icon${tone === "danger" ? " btn-danger" : ""}`}
      title={label}
      aria-label={label}
      aria-pressed={pressed}
      disabled={disabled}
      onClick={onClick}
    >
      <Icon name={icon} />
    </button>
  );
}
