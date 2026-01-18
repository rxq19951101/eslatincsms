/**
 * 极简 design-system（仅供 UI 组件编译/运行）
 *
 * 说明：
 * - 之前 `app/components/ui/Modal.tsx` 引用了 `../../styles/design-system`，但项目中未提供该文件，
 *   会导致 `next build` 失败、进而阻塞 docker compose 启动全链路测试。
 * - 这里提供最小可用的 token 集合，避免影响现有 shadcn/tailwind 的视觉体系。
 */
export const colors = {
  background: {
    primary: "#FFFFFF",
    border: "#E5E7EB",
  },
  text: {
    primary: "#111827",
    secondary: "#6B7280",
  },
};

export const borderRadius = {
  xl: "16px",
};

export const spacing = {
  xs: "4px",
  base: "12px",
  xl: "24px",
};

export const typography = {
  fontSize: {
    h4: "18px",
  },
  fontWeight: {
    bold: 700,
  },
};

export const zIndex = {
  modal: 50,
};

