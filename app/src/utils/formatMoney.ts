/**
 * 哥伦比亚比索 COP 展示（拉美常见：$10.000 COP，避免误读为 USD）
 */

const COP_SUFFIX = 'COP';

/** 整数部分千分位用点（拉丁习惯），小数用逗号（本项目金额多为整数 COP） */
export function formatMoneyCOP(amount: number, options?: { decimals?: number }): string {
  const decimals = options?.decimals ?? 2;
  const negative = amount < 0;
  const abs = Math.abs(amount);
  const fixed = abs.toFixed(decimals);
  const [intPart, decPart] = fixed.split('.');
  const withThousands = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, '.');
  const num =
    decimals > 0 && decPart && Number(decPart) !== 0
      ? `${withThousands},${decPart}`
      : withThousands;
  return `${negative ? '-' : ''}$${num} ${COP_SUFFIX}`;
}

/** 简短展示（列表行） */
export function formatMoneyCOPShort(amount: number): string {
  return formatMoneyCOP(amount, { decimals: 0 });
}
