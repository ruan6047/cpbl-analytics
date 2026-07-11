"use client";

import React, { useState, useEffect, useRef, useId } from "react";
import { createPortal } from "react-dom";

export type TooltipProps = {
  content: React.ReactNode;
  children: React.ReactElement;
  placement?: "top" | "bottom";
  delayIn?: number; // in milliseconds
  suppressUnderline?: boolean; // suppress default dotted underline styles
};

export function Tooltip({
  content,
  children,
  placement = "top",
  delayIn = 150,
  suppressUnderline = false,
}: TooltipProps) {
  const [isVisible, setIsVisible] = useState(false);
  const [isMounted, setIsMounted] = useState(false);
  const [coords, setCoords] = useState({ top: 0, left: 0 });
  const [isCalculated, setIsCalculated] = useState(false);
  const [actualPlacement, setActualPlacement] = useState<"top" | "bottom">("top");

  const id = useId();
  const triggerRef = useRef<HTMLElement>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);
  const timerRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    setIsMounted(true);
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  const updatePosition = () => {
    if (!triggerRef.current || !tooltipRef.current) return;
    const triggerRect = triggerRef.current.getBoundingClientRect();
    const tooltipRect = tooltipRef.current.getBoundingClientRect();

    const offset = 8; // gap between trigger and tooltip
    let top = 0;
    let left = 0;
    let placementToUse = placement;

    if (placementToUse === "top") {
      top = triggerRect.top - tooltipRect.height - offset;
      if (top < 8) {
        // Collides with top of viewport -> flip to bottom
        top = triggerRect.bottom + offset;
        placementToUse = "bottom";
      }
    } else {
      top = triggerRect.bottom + offset;
      if (top + tooltipRect.height > window.innerHeight - 8) {
        // Collides with bottom of viewport -> flip to top
        top = triggerRect.top - tooltipRect.height - offset;
        placementToUse = "top";
      }
    }

    // Horizontal centering
    left = triggerRect.left + (triggerRect.width - tooltipRect.width) / 2;

    // Bounds checking (RWD protection for 375px)
    const margin = 16;
    if (left < margin) {
      left = margin;
    }
    const maxLeft = window.innerWidth - tooltipRect.width - margin;
    if (left > maxLeft) {
      left = maxLeft;
    }

    setCoords({ top, left });
    setActualPlacement(placementToUse);
  };

  useEffect(() => {
    if (isVisible) {
      updatePosition();
      setIsCalculated(true);

      const handleResize = () => {
        updatePosition();
      };

      const handleKeyDown = (e: KeyboardEvent) => {
        if (e.key === "Escape") {
          setIsVisible(false);
        }
      };

      const handleClickOutside = (e: MouseEvent | TouchEvent) => {
        if (
          triggerRef.current &&
          !triggerRef.current.contains(e.target as Node) &&
          tooltipRef.current &&
          !tooltipRef.current.contains(e.target as Node)
        ) {
          setIsVisible(false);
        }
      };

      const handleScroll = () => {
        setIsVisible(false);
      };

      window.addEventListener("resize", handleResize);
      window.addEventListener("keydown", handleKeyDown);
      document.addEventListener("mousedown", handleClickOutside);
      document.addEventListener("touchstart", handleClickOutside);
      window.addEventListener("scroll", handleScroll, { passive: true });

      return () => {
        window.removeEventListener("resize", handleResize);
        window.removeEventListener("keydown", handleKeyDown);
        document.removeEventListener("mousedown", handleClickOutside);
        document.removeEventListener("touchstart", handleClickOutside);
        window.removeEventListener("scroll", handleScroll);
        setIsCalculated(false);
      };
    }
  }, [isVisible]);

  const showTooltip = () => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      setIsVisible(true);
    }, delayIn);
  };

  const hideTooltip = () => {
    if (timerRef.current) clearTimeout(timerRef.current);
    setIsVisible(false);
  };

  const handleToggle = (e: React.MouseEvent) => {
    // Prevent hover states and touch states from overlapping on mobile
    const nativeEvent = e.nativeEvent as any;
    if (nativeEvent.pointerType === "touch" || !("pointerType" in nativeEvent)) {
      e.preventDefault();
      setIsVisible((prev) => !prev);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    const target = e.target as HTMLElement;
    const tagName = target.tagName.toLowerCase();
    const isInteractive =
      tagName === "button" ||
      tagName === "a" ||
      tagName === "input" ||
      target.getAttribute("role") === "button";

    if (e.key === "Enter" || e.key === " ") {
      if (!isInteractive) {
        e.preventDefault();
        setIsVisible((prev) => !prev);
      }
    }
  };

  const composeEventHandlers = <E extends React.SyntheticEvent>(
    theirHandler?: (event: E) => void,
    ourHandler?: (event: E) => void
  ) => {
    return (event: E) => {
      theirHandler?.(event);
      if (!event.defaultPrevented) {
        ourHandler?.(event);
      }
    };
  };

  const child = React.Children.only(children) as React.ReactElement<any>;
  const underlineClasses = suppressUnderline
    ? ""
    : "cursor-help border-b border-dotted border-muted/60";

  const triggerProps = {
    ref: triggerRef,
    "aria-describedby": isVisible ? id : undefined,
    tabIndex: child.props.tabIndex ?? 0,
    className: `${child.props.className ?? ""} ${underlineClasses}`.trim() || undefined,
    onMouseEnter: composeEventHandlers(child.props.onMouseEnter, showTooltip),
    onMouseLeave: composeEventHandlers(child.props.onMouseLeave, hideTooltip),
    onFocus: composeEventHandlers(child.props.onFocus, showTooltip),
    onBlur: composeEventHandlers(child.props.onBlur, hideTooltip),
    onClick: composeEventHandlers(child.props.onClick, handleToggle),
    onKeyDown: composeEventHandlers(child.props.onKeyDown, handleKeyDown),
  };

  const trigger = React.cloneElement(child, triggerProps);

  return (
    <>
      {trigger}
      {isMounted &&
        isVisible &&
        createPortal(
          <div
            ref={tooltipRef}
            id={id}
            role="tooltip"
            style={{
              position: "fixed",
              top: coords.top,
              left: coords.left,
              visibility: isCalculated ? "visible" : "hidden",
            }}
            className="z-50 max-w-[280px] break-words rounded-lg border border-line bg-ink px-3 py-2 text-xs leading-relaxed text-paper shadow-lg animate-fade-in pointer-events-none"
          >
            {content}
          </div>,
          document.body
        )}
    </>
  );
}
