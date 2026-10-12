import type { InputHTMLAttributes } from "react"
import { cn } from "@/lib/utils"

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        "h-10 w-full rounded-xl border border-line bg-white px-3 text-sm text-ink outline-none placeholder:text-muted/80 focus-visible:ring-2 focus-visible:ring-tide/30",
        className,
      )}
      {...props}
    />
  )
}
