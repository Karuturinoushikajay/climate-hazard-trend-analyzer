import type { HTMLAttributes } from "react"
import { cn } from "@/lib/utils"

export function Card({ className, ...props }: HTMLAttributes<HTMLElement>) {
  return (
    <section
      className={cn("rounded-2xl border border-line bg-card shadow-[0_1px_0_rgba(28,25,21,0.04)]", className)}
      {...props}
    />
  )
}
