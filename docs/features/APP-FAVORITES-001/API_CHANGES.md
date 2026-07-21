---
id: APP-FAVORITES-001
status: ready-for-dev
contract: frozen
---

# API 契约

- `GET /api/v1/app/favorites`：返回当前用户收藏的有效站点数组，结构与站点列表相同，`is_favorite=true`。
- `PUT /api/v1/app/favorites/{site_id}`：幂等收藏，返回 `{"site_id":"...","is_favorite":true}`。
- `DELETE /api/v1/app/favorites/{site_id}`：幂等取消，返回 `{"site_id":"...","is_favorite":false}`。
- `GET /api/v1/app/sites` 和详情元素增加布尔字段 `is_favorite`。

所有接口要求 App 用户认证；收藏对象必须是启用站点。
