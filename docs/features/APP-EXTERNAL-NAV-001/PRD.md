---
id: APP-EXTERNAL-NAV-001
status: ready-for-dev
owner: product
---

# 站点外部导航

## 背景

站点详情当前按操作系统直接打开地图：iOS 固定使用 Apple 地图，Android 固定使用 Google Maps。哥伦比亚用户常用 Google Maps 和 Waze，需要由用户选择导航应用。

## 范围

- 在原生 App 的站点详情点击“导航”后显示地图应用选择。
- Android 提供 Google Maps、Waze。
- iOS 提供 Google Maps、Waze、Apple 地图。
- 使用地图服务官方通用链接；已安装应用时由系统打开应用，未安装时允许浏览器承接。
- 所有新增界面文案支持中文、英文和西班牙文。

## 不在范围

- 内嵌路线规划。
- 新增地图 SDK、API Key 或安装检测权限。
- 修改站点坐标数据或后端接口。

