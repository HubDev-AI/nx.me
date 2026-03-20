'use client';

import { useRef, useCallback } from 'react';

const THRESHOLD = 14;

interface TiltCardProps {
  children: React.ReactNode;
  className?: string;
}

/**
 * 3D perspective tilt card — follows cursor on hover.
 * GPU-composited (transform + perspective only).
 * Disabled when prefers-reduced-motion is set.
 */
export function TiltCard({ children, className = '' }: TiltCardProps) {
  const cardRef = useRef<HTMLDivElement>(null);

  const handleMouseMove = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    const card = cardRef.current;
    if (!card) return;
    const { left, top, width, height } = card.getBoundingClientRect();
    const x = (e.clientX - left) / width;
    const y = (e.clientY - top) / height;
    const rotateY = (x - 0.5) * THRESHOLD * 2;
    const rotateX = (0.5 - y) * THRESHOLD * 2;
    card.style.transform =
      `perspective(${width}px) rotateX(${rotateX.toFixed(1)}deg) rotateY(${rotateY.toFixed(1)}deg) scale3d(1.03, 1.03, 1.03)`;
  }, []);

  const handleMouseLeave = useCallback(() => {
    const card = cardRef.current;
    if (!card) return;
    card.style.transform = 'perspective(800px) rotateX(0deg) rotateY(0deg) scale3d(1, 1, 1)';
  }, []);

  return (
    <div
      ref={cardRef}
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
      className={`motion-safe:transition-transform motion-safe:duration-200 motion-safe:ease-out will-change-transform [transform-style:preserve-3d] ${className}`}
    >
      <div className="[transform:translateZ(20px)] transition-transform duration-300">
        {children}
      </div>
    </div>
  );
}
