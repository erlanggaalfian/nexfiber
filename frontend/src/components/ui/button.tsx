import type { ButtonHTMLAttributes } from "react";

const VARIANTS = {
  primary: "bg-amber text-white font-semibold border border-amber",
  secondary: "border border-line-strong text-ink hover:bg-sunken",
  quiet: "text-fiber hover:underline",
  danger: "border border-down text-down hover:bg-sunken",
};
const SIZES = { sm: "h-7 px-2", md: "h-8 px-3", lg: "h-10 px-4" };

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: keyof typeof VARIANTS;
  size?: keyof typeof SIZES;
};

export const buttonClass = (variant: keyof typeof VARIANTS = "secondary", size: keyof typeof SIZES = "md") =>
  `inline-flex items-center justify-center gap-1.5 rounded-sm text-sm whitespace-nowrap disabled:opacity-50 disabled:cursor-not-allowed ${VARIANTS[variant]} ${SIZES[size]}`;

export function Button({ variant = "secondary", size = "md", className = "", type = "button", ...rest }: Props) {
  return <button type={type} className={`${buttonClass(variant, size)} ${className}`} {...rest} />;
}
