/**
 * Modal 组件
 * 用于显示对话框、确认框等
 */

"use client";

import React, { useEffect } from "react";
import { colors, borderRadius, spacing, typography, zIndex } from "../../styles/design-system";

type ModalSize = "small" | "medium" | "large" | "fullscreen";

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title?: string;
  children: React.ReactNode;
  size?: ModalSize;
  footer?: React.ReactNode;
  showCloseButton?: boolean;
}

export function Modal({
  isOpen,
  onClose,
  title,
  children,
  size = "medium",
  footer,
  showCloseButton = true,
}: ModalProps) {
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "unset";
    }
    return () => {
      document.body.style.overflow = "unset";
    };
  }, [isOpen]);

  if (!isOpen) return null;

  const sizeStyles: Record<ModalSize, React.CSSProperties> = {
    small: { maxWidth: "400px" },
    medium: { maxWidth: "600px" },
    large: { maxWidth: "900px" },
    fullscreen: {
      width: "100vw",
      height: "100vh",
      maxWidth: "100%",
      maxHeight: "100%",
      borderRadius: 0,
    },
  };

  const handleBackdropClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (e.target === e.currentTarget) {
      onClose();
    }
  };

  return (
    <div
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: "rgba(0,0,0,0.6)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: zIndex.modal,
        padding: spacing.xl,
        animation: "fadeIn 0.2s ease",
      }}
      onClick={handleBackdropClick}
    >
      <div
        style={{
          backgroundColor: colors.background.primary,
          borderRadius: size === "fullscreen" ? 0 : borderRadius.xl,
          width: "100%",
          maxHeight: "90vh",
          display: "flex",
          flexDirection: "column",
          boxShadow: "0 8px 32px rgba(0,0,0,0.3)",
          animation: "slideUp 0.2s ease",
          ...sizeStyles[size],
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        {(title || showCloseButton) && (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              padding: spacing.xl,
              borderBottom: `1px solid ${colors.background.border}`,
            }}
          >
            {title && (
              <h3
                style={{
                  fontSize: typography.fontSize.h4,
                  fontWeight: typography.fontWeight.bold,
                  color: colors.text.primary,
                  margin: 0,
                }}
              >
                {title}
              </h3>
            )}
            {showCloseButton && (
              <button
                onClick={onClose}
                style={{
                  background: "none",
                  border: "none",
                  color: colors.text.secondary,
                  fontSize: "24px",
                  cursor: "pointer",
                  padding: spacing.xs,
                  lineHeight: 1,
                  transition: "color 0.2s ease",
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.color = colors.text.primary;
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.color = colors.text.secondary;
                }}
              >
                ×
              </button>
            )}
          </div>
        )}

        {/* Body */}
        <div
          style={{
            padding: spacing.xl,
            overflowY: "auto",
            flex: 1,
          }}
        >
          {children}
        </div>

        {/* Footer */}
        {footer && (
          <div
            style={{
              padding: spacing.xl,
              borderTop: `1px solid ${colors.background.border}`,
              display: "flex",
              gap: spacing.base,
              justifyContent: "flex-end",
            }}
          >
            {footer}
          </div>
        )}

        <style jsx>{`
          @keyframes fadeIn {
            from {
              opacity: 0;
            }
            to {
              opacity: 1;
            }
          }

          @keyframes slideUp {
            from {
              opacity: 0;
              transform: translateY(20px) scale(0.95);
            }
            to {
              opacity: 1;
              transform: translateY(0) scale(1);
            }
          }
        `}</style>
      </div>
    </div>
  );
}
