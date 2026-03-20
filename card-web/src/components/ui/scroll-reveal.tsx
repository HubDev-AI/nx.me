'use client';

import { useEffect, useRef, useState } from 'react';

function useInView(threshold = 0.15) {
  const ref = useRef<HTMLDivElement>(null);
  const [isInView, setIsInView] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      (entries) => {
        const entry = entries[0];
        if (entry?.isIntersecting) {
          setIsInView(true);
          observer.unobserve(el);
        }
      },
      { threshold },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [threshold]);

  return { ref, isInView };
}

interface ScrollRevealProps {
  children: React.ReactNode;
  className?: string;
  delay?: number;
}

/**
 * Scroll-triggered reveal animation using Intersection Observer.
 * GPU-composited (opacity + transform + filter only).
 */
export function ScrollReveal({ children, className = '', delay = 0 }: ScrollRevealProps) {
  const { ref, isInView } = useInView();

  return (
    <div
      ref={ref}
      className={`motion-safe:transition-all motion-safe:duration-700 motion-safe:ease-out ${
        isInView
          ? 'opacity-100 translate-y-0 blur-0'
          : 'opacity-0 translate-y-8 blur-[2px]'
      } ${className}`}
      style={{ transitionDelay: isInView ? `${delay}ms` : '0ms' }}
    >
      {children}
    </div>
  );
}
