import { motion, type MotionProps } from "framer-motion";
import { cn } from "@/lib/utils";

interface FadeInProps extends MotionProps {
  as?: keyof JSX.IntrinsicElements;
  delay?: number;
  className?: string;
  children: React.ReactNode;
}

export function FadeIn({
  as: Tag = "div",
  delay = 0,
  className,
  children,
  ...motionProps
}: FadeInProps) {
  return (
    <motion.div
      className={cn(className)}
      initial={{ opacity: 0, y: 24 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.2 }}
      transition={{ duration: 0.6, ease: "easeOut", delay }}
      {...motionProps}
    >
      {children}
    </motion.div>
  );
}
