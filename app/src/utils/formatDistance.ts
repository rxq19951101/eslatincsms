/**
 * 距离格式化工具函数
 * 将距离（千米）格式化为易读的字符串
 */

/**
 * 格式化距离
 * @param distanceKm 距离（千米）
 * @returns 格式化后的距离字符串
 * - 小于1千米：显示米（如："500 m"）
 * - 大于等于1千米：显示千米（如："2.5 km"）
 */
export const formatDistance = (distanceKm: number | undefined): string | null => {
  if (distanceKm === undefined || distanceKm === null) {
    return null;
  }

  if (distanceKm < 1) {
    // 小于1千米，显示米，保留整数
    const distanceM = Math.round(distanceKm * 1000);
    return `${distanceM} m`;
  } else {
    // 大于等于1千米，显示千米，保留1位小数
    return `${distanceKm.toFixed(1)} km`;
  }
};
