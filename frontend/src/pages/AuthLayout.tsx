import { motion } from "motion/react";
import type { ReactNode } from "react";

export function AuthLayout({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle: string;
  children: ReactNode;
}) {
  return (
    <main className="flex min-h-dvh items-center justify-center px-5 py-12">
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
        className="w-full max-w-sm"
      >
        <div className="mb-8 flex flex-col items-center text-center">
          <img src="./favicon.svg" alt="" className="mb-5 size-16 rounded-[18px] shadow-card" />
          <h1 className="text-[28px] font-bold tracking-tight">{title}</h1>
          <p className="mt-1.5 text-[15px] text-secondary">{subtitle}</p>
        </div>
        {children}
      </motion.div>
    </main>
  );
}
