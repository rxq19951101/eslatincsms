---
id: APP-EXTERNAL-NAV-001
status: ready-for-dev
---

# 验收标准

1. 原生 App 点击站点详情“导航”后可以选择 Google Maps 或 Waze。
2. iOS 额外提供 Apple 地图。
3. Google Maps 使用 `api=1`、经纬度目的地和驾车模式，不把站点名称误传为 Place ID。
4. Waze 使用 `ll`、`navigate=yes` 和 EsLatin 来源标识。
5. 通用链接打开失败时显示当前语言的错误提示。
6. 缺少或非法经纬度时不打开链接，并显示当前语言的提示；合法的零坐标不会被误判为缺失。
7. Web 运行环境直接使用 Google Maps 通用链接。
8. URL 生成、平台选项和错误路径有定向测试，TypeScript 检查通过。

