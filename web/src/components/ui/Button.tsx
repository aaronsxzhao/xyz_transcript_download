import type { ButtonHTMLAttributes } from "react";
export default function Button({
  variant = "secondary",
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "quiet" | "danger";
}) {
  return (
    <button
      {...props}
      className={`ui-button ui-button-${variant} ${className}`}
    />
  );
}
