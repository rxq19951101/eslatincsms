'use client';

import {
  Children,
  cloneElement,
  createContext,
  isValidElement,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';

export type Locale = 'zh-CN' | 'en' | 'es';

const messages = {
  'zh-CN': {
    brand: '运营平台',
    adminPortal: '后台管理',
    dashboard: '仪表板',
    sites: '站点管理',
    transactions: '交易管理',
    sessions: '活跃会话',
    payments: '支付管理',
    reports: '统计报表',
    alerts: '告警管理',
    users: '用户管理',
    tenants: '租户管理',
    map: '地图视图',
    settings: '系统设置',
    search: '搜索...',
    allPlatform: '全平台',
    tenant: '租户',
    language: '语言',
    chinese: '中文',
    english: 'English',
    spanish: 'Español',
    loginTitle: '充电桩运营平台',
    loginSubtitle: '请输入您的账号和密码登录',
    username: '用户名',
    password: '密码',
    usernamePlaceholder: '请输入用户名',
    passwordPlaceholder: '请输入密码',
    usernameRequired: '用户名不能为空',
    passwordRequired: '密码不能为空',
    login: '登录',
    loggingIn: '登录中...',
    loginFailed: '登录失败，请稍后重试',
    invalidCredentials: '用户名或密码错误，请重新输入',
    networkError: '网络连接失败，请检查网络或后端服务是否正常运行',
    loading: '加载中...',
    refresh: '刷新',
    adminUsersAndAppUsers: '管理管理员与 App 用户钱包。',
    appUsers: 'App 用户',
    adminUsers: '管理员用户',
    walletBalance: '钱包余额',
    active: '活跃',
    disabled: '禁用',
    logout: '退出登录',
    superAdmin: '超级管理员',
    administrator: '管理员',
    'validation.required': '此字段为必填项',
    'validation.siteNameLength': '站点名称需为 2–120 个字符',
    'validation.addressLength': '地址需为 5–300 个字符',
    'validation.latitude': '纬度必须在 -90 到 90 之间',
    'validation.longitude': '经度必须在 -180 到 180 之间',
    'validation.zeroCoordinates': '坐标不能为 (0, 0)',
    'validation.operatingHoursLength': '营业时间不能超过 500 个字符',
    'validation.ocppIdentity': 'OCPP 身份仅可包含 1–64 位 ASCII 字母、数字、点、下划线、冒号或连字符',
    'validation.textTooLong': '输入内容过长或格式不正确',
    'validation.connectorCount': 'EVSE 数量必须是 1–16 的整数',
    'validation.positiveAmount': '金额不能为零',
    'validation.moneyPrecision': '金额必须是数字且最多保留两位小数',
    'validation.reasonRequired': '调整原因不能为空',
    'validation.reasonLength': '调整原因需为 1–500 个字符',
    'validation.tenantNameLength': '租户名称需为 2–200 个字符',
    'validation.domain': '请输入有效域名（最多 200 个字符）',
    'validation.plan': '请选择有效套餐',
    'validation.limit': '上限必须是大于 0 的整数',
    'validation.username': '用户名需为 3–100 位 ASCII 字母、数字、点、下划线或连字符',
    'validation.email': '请输入有效邮箱地址',
    'validation.passwordLength': '密码需为 8–128 个字符',
    'validation.passwordMismatch': '两次输入的密码不一致',
    'validation.price': '请输入有效的正数价格',
    'validation.configKey': '请选择已注册的配置键',
    'validation.configValue': '配置值不能超过 5000 个字符',
    'api.unauthorized': '登录已失效，请重新登录',
    'api.forbidden': '没有权限执行此操作',
    'api.notFound': '请求的资源不存在',
    'api.conflict': '该值已存在或与当前数据冲突',
    'api.validation': '提交内容无效，请检查标出的字段',
    'api.server': '服务器暂时无法处理请求，请稍后重试',
  },
  en: {
    brand: 'Operations', adminPortal: 'Admin Portal', dashboard: 'Dashboard', sites: 'Sites',
    transactions: 'Transactions', sessions: 'Active Sessions', payments: 'Payments', reports: 'Reports',
    alerts: 'Alerts', users: 'Users', tenants: 'Tenants', map: 'Map', settings: 'Settings',
    search: 'Search...', allPlatform: 'All platform', tenant: 'Tenant', language: 'Language',
    chinese: '中文', english: 'English', spanish: 'Español', loginTitle: 'EV Charging Platform',
    loginSubtitle: 'Enter your account and password to continue', username: 'Username', password: 'Password',
    usernamePlaceholder: 'Enter username', passwordPlaceholder: 'Enter password', login: 'Log in',
    usernameRequired: 'Username is required', passwordRequired: 'Password is required',
    loggingIn: 'Logging in...', loginFailed: 'Login failed. Please try again.',
    invalidCredentials: 'Invalid username or password.', networkError: 'Network error. Check the backend service.',
    loading: 'Loading...', refresh: 'Refresh', adminUsersAndAppUsers: 'Manage administrators and App user wallets.',
    appUsers: 'App Users', adminUsers: 'Administrators', walletBalance: 'Wallet Balance', active: 'Active',
    disabled: 'Disabled', superAdmin: 'Super Administrator', administrator: 'Administrator',
    logout: 'Log out',
    'validation.required': 'This field is required',
    'validation.siteNameLength': 'Site name must be 2–120 characters',
    'validation.addressLength': 'Address must be 5–300 characters',
    'validation.latitude': 'Latitude must be between -90 and 90',
    'validation.longitude': 'Longitude must be between -180 and 180',
    'validation.zeroCoordinates': 'Coordinates cannot be (0, 0)',
    'validation.operatingHoursLength': 'Operating hours cannot exceed 500 characters',
    'validation.ocppIdentity': 'OCPP identity must be 1–64 ASCII letters, numbers, dots, underscores, colons, or hyphens',
    'validation.textTooLong': 'The value is too long or has an invalid format',
    'validation.connectorCount': 'EVSE count must be an integer from 1 to 16',
    'validation.positiveAmount': 'Amount cannot be zero',
    'validation.moneyPrecision': 'Amount must be numeric with at most two decimal places',
    'validation.reasonRequired': 'A reason is required',
    'validation.reasonLength': 'Reason must be 1–500 characters',
    'validation.tenantNameLength': 'Tenant name must be 2–200 characters',
    'validation.domain': 'Enter a valid domain (up to 200 characters)',
    'validation.plan': 'Select a valid plan',
    'validation.limit': 'Limit must be a positive integer',
    'validation.username': 'Username must be 3–100 ASCII letters, numbers, dots, underscores, or hyphens',
    'validation.email': 'Enter a valid email address',
    'validation.passwordLength': 'Password must be 8–128 characters',
    'validation.passwordMismatch': 'Passwords do not match',
    'validation.price': 'Enter a valid positive price',
    'validation.configKey': 'Select a registered configuration key',
    'validation.configValue': 'Configuration value cannot exceed 5000 characters',
    'api.unauthorized': 'Your session expired. Log in again',
    'api.forbidden': 'You do not have permission to perform this action',
    'api.notFound': 'The requested resource was not found',
    'api.conflict': 'This value already exists or conflicts with current data',
    'api.validation': 'The submitted data is invalid. Check the highlighted fields',
    'api.server': 'The server cannot process the request right now. Try again later',
  },
  es: {
    brand: 'Operaciones', adminPortal: 'Portal de administración', dashboard: 'Panel', sites: 'Sitios',
    transactions: 'Transacciones', sessions: 'Sesiones activas', payments: 'Pagos', reports: 'Reportes',
    alerts: 'Alertas', users: 'Usuarios', tenants: 'Inquilinos', map: 'Mapa', settings: 'Configuración',
    search: 'Buscar...', allPlatform: 'Toda la plataforma', tenant: 'Inquilino', language: 'Idioma',
    chinese: '中文', english: 'English', spanish: 'Español', loginTitle: 'Plataforma de carga eléctrica',
    loginSubtitle: 'Ingresa tu cuenta y contraseña para continuar', username: 'Usuario', password: 'Contraseña',
    usernamePlaceholder: 'Ingresa el usuario', passwordPlaceholder: 'Ingresa la contraseña', login: 'Iniciar sesión',
    usernameRequired: 'El usuario es obligatorio', passwordRequired: 'La contraseña es obligatoria',
    loggingIn: 'Iniciando sesión...', loginFailed: 'No se pudo iniciar sesión. Inténtalo de nuevo.',
    invalidCredentials: 'Usuario o contraseña incorrectos.', networkError: 'Error de red. Verifica el backend.',
    loading: 'Cargando...', refresh: 'Actualizar', adminUsersAndAppUsers: 'Administra administradores y billeteras de usuarios App.',
    appUsers: 'Usuarios App', adminUsers: 'Administradores', walletBalance: 'Saldo de billetera', active: 'Activo',
    disabled: 'Deshabilitado', superAdmin: 'Superadministrador', administrator: 'Administrador',
    logout: 'Cerrar sesión',
    'validation.required': 'Este campo es obligatorio',
    'validation.siteNameLength': 'El nombre del sitio debe tener entre 2 y 120 caracteres',
    'validation.addressLength': 'La dirección debe tener entre 5 y 300 caracteres',
    'validation.latitude': 'La latitud debe estar entre -90 y 90',
    'validation.longitude': 'La longitud debe estar entre -180 y 180',
    'validation.zeroCoordinates': 'Las coordenadas no pueden ser (0, 0)',
    'validation.operatingHoursLength': 'El horario no puede superar los 500 caracteres',
    'validation.ocppIdentity': 'La identidad OCPP debe tener 1–64 letras ASCII, números, puntos, guiones bajos, dos puntos o guiones',
    'validation.textTooLong': 'El valor es demasiado largo o tiene un formato inválido',
    'validation.connectorCount': 'La cantidad de EVSE debe ser un entero entre 1 y 16',
    'validation.positiveAmount': 'El monto no puede ser cero',
    'validation.moneyPrecision': 'El monto debe ser numérico y tener como máximo dos decimales',
    'validation.reasonRequired': 'El motivo es obligatorio',
    'validation.reasonLength': 'El motivo debe tener entre 1 y 500 caracteres',
    'validation.tenantNameLength': 'El nombre del inquilino debe tener entre 2 y 200 caracteres',
    'validation.domain': 'Ingresa un dominio válido (máximo 200 caracteres)',
    'validation.plan': 'Selecciona un plan válido',
    'validation.limit': 'El límite debe ser un entero positivo',
    'validation.username': 'El usuario debe tener 3–100 letras ASCII, números, puntos, guiones bajos o guiones',
    'validation.email': 'Ingresa un correo electrónico válido',
    'validation.passwordLength': 'La contraseña debe tener entre 8 y 128 caracteres',
    'validation.passwordMismatch': 'Las contraseñas no coinciden',
    'validation.price': 'Ingresa un precio positivo válido',
    'validation.configKey': 'Selecciona una clave de configuración registrada',
    'validation.configValue': 'El valor no puede superar los 5000 caracteres',
    'api.unauthorized': 'Tu sesión venció. Inicia sesión de nuevo',
    'api.forbidden': 'No tienes permiso para realizar esta acción',
    'api.notFound': 'No se encontró el recurso solicitado',
    'api.conflict': 'Este valor ya existe o entra en conflicto con los datos actuales',
    'api.validation': 'Los datos enviados no son válidos. Revisa los campos marcados',
    'api.server': 'El servidor no puede procesar la solicitud ahora. Inténtalo más tarde',
  },
} as const;

// 旧页面仍有少量直接写入 JSX 的文案，单独维护覆盖表，避免遗漏时回退到中文。
const legacyText = {
  en: {
    '租户资料已更新': 'Tenant profile updated', '个人资料已更新': 'Profile updated', '密码修改成功': 'Password changed successfully', '密码修改失败': 'Password change failed',
    '新密码至少需要 8 位': 'The new password must be at least 8 characters', '两次输入的新密码不一致': 'The passwords do not match', '在 Google 地图上查看各站点位置（数据来自站点列表）': 'View all site locations on Google Maps (data from the site list)', '加载站点数据…': 'Loading site data…',
    '加载地图中...': 'Loading map...', '地图加载中...': 'Loading map...', '加载地图中…': 'Loading map...', '出现了错误': 'Something went wrong', '发生了未知错误，请刷新页面重试': 'An unknown error occurred. Refresh and try again.', '刷新页面': 'Refresh page',
    '系统租户管理': 'System tenant management', '租户管理': 'Tenant management', '管理系统租户（仅超级管理员）': 'Manage system tenants (super administrators only)', '租户列表': 'Tenant list', '搜索租户 ID / 名称 / 域名...': 'Search tenant ID / name / domain...', '名称': 'Name', '域名': 'Domain', '套餐': 'Plan', '桩数上限': 'Charger limit', '用户上限': 'User limit', '暂无租户': 'No tenants', '创建租户（注册/开通）': 'Create tenant (register/activate)', '创建成功': 'Created successfully', '租户管理员账号': 'Tenant administrator account', '租户名称': 'Tenant name', '选择套餐': 'Select plan', '创建租户管理员账号': 'Create tenant administrator account', '管理员用户名 *': 'Administrator username *', '管理员邮箱 *': 'Administrator email *', '姓名（可选）': 'Name (optional)', '初始密码（可选）': 'Initial password (optional)', '留空将自动生成': 'Leave blank to generate automatically',
    '充电桩管理': 'Charger management', '该模块已迁移：请以站点为单位进行管理': 'This module has moved: manage chargers by site', '迁移说明': 'Migration note', '从现在开始，运营后台以“站点”为单位管理：': 'From now on, manage operations by site:', '前往站点管理': 'Go to site management',
    '筛选状态': 'Filter status', '没有找到交易记录': 'No transactions found', '没有找到告警': 'No alerts found', '加载规则...': 'Loading rules...', '暂无告警规则，可通过 API 创建': 'No alert rules. Create them via the API.', '支付配置': 'Payment settings', '查看支付配置状态（当前版本默认关闭应用内支付）': 'View payment configuration (in-app payments are disabled by default)', '应用内支付轨已关闭': 'In-app payment rail is disabled', '环境': 'Environment', '已配置': 'Configured', '未配置': 'Not configured', '配置说明：': 'Configuration notes:', '用户:': 'User:', '类型:': 'Type:', '金额:': 'Amount:', '创建时间:': 'Created at:', '支付时间:': 'Paid at:',
    '地图': 'Map', '站点地图': 'Site map', '新增站点': 'Add site', '创建一个新的运营站点。': 'Create a new operating site.', '站点名称': 'Site name', '营业时间（可选）': 'Business hours (optional)', '搜索地址（自动填充经纬度）': 'Search address (fills coordinates automatically)', '地图选点': 'Select on map', '提示：搜索地址后自动定位，也可点击地图任意位置更新坐标': 'Tip: search an address to locate it, or click the map to update coordinates', '纬度': 'Latitude', '经度': 'Longitude', '暂无站点': 'No sites',
    '基本信息': 'Basic information', '状态监控': 'Status monitoring', '历史记录': 'History', '远程控制': 'Remote control', '二维码': 'QR codes', '状态': 'Status', '当前状态': 'Current status', '最后在线时间': 'Last online time', 'EVSE 列表': 'EVSE list', '历史记录功能待实现': 'History is not implemented yet', '启动充电': 'Start charging', '停止充电': 'Stop charging', '重置充电桩': 'Reset charger', '解锁连接器': 'Unlock connector', '配置管理': 'Configuration management', '暂无connector信息': 'No connector information',
  },
  es: {
    '租户资料已更新': 'Perfil del inquilino actualizado', '个人资料已更新': 'Perfil actualizado', '密码修改成功': 'Contraseña cambiada correctamente', '密码修改失败': 'No se pudo cambiar la contraseña',
    '新密码至少需要 8 位': 'La nueva contraseña debe tener al menos 8 caracteres', '两次输入的新密码不一致': 'Las contraseñas no coinciden', '在 Google 地图上查看各站点位置（数据来自站点列表）': 'Consulta todos los sitios en Google Maps (datos de la lista de sitios)', '加载站点数据…': 'Cargando datos de sitios…',
    '加载地图中...': 'Cargando mapa...', '地图加载中...': 'Cargando mapa...', '加载地图中…': 'Cargando mapa...', '出现了错误': 'Ocurrió un error', '发生了未知错误，请刷新页面重试': 'Ocurrió un error desconocido. Actualiza e inténtalo de nuevo.', '刷新页面': 'Actualizar página',
    '租户管理': 'Gestión de inquilinos', '管理系统租户（仅超级管理员）': 'Gestiona los inquilinos del sistema (solo superadministradores)', '租户列表': 'Lista de inquilinos', '搜索租户 ID / 名称 / 域名...': 'Buscar ID / nombre / dominio del inquilino...', '名称': 'Nombre', '域名': 'Dominio', '套餐': 'Plan', '桩数上限': 'Límite de cargadores', '用户上限': 'Límite de usuarios', '暂无租户': 'No hay inquilinos', '创建租户（注册/开通）': 'Crear inquilino (registro/activación)', '创建成功': 'Creado correctamente', '租户管理员账号': 'Cuenta administradora del inquilino', '租户名称': 'Nombre del inquilino', '选择套餐': 'Seleccionar plan', '创建租户管理员账号': 'Crear cuenta administradora del inquilino', '管理员用户名 *': 'Usuario administrador *', '管理员邮箱 *': 'Correo del administrador *', '姓名（可选）': 'Nombre (opcional)', '初始密码（可选）': 'Contraseña inicial (opcional)', '留空将自动生成': 'Déjalo vacío para generar automáticamente',
    '充电桩管理': 'Gestión de cargadores', '该模块已迁移：请以站点为单位进行管理': 'Este módulo se migró: gestiona los cargadores por sitio', '迁移说明': 'Nota de migración', '从现在开始，运营后台以“站点”为单位管理：': 'Desde ahora, gestiona la operación por sitio:', '前往站点管理': 'Ir a gestión de sitios',
    '筛选状态': 'Filtrar estado', '没有找到交易记录': 'No se encontraron transacciones', '没有找到告警': 'No se encontraron alertas', '加载规则...': 'Cargando reglas...', '暂无告警规则，可通过 API 创建': 'No hay reglas de alertas. Créelas mediante la API.', '支付配置': 'Configuración de pagos', '查看支付配置状态（当前版本默认关闭应用内支付）': 'Consulta la configuración de pagos (los pagos en la app están desactivados por defecto)', '应用内支付轨已关闭': 'Los pagos dentro de la app están desactivados', '环境': 'Entorno', '已配置': 'Configurado', '未配置': 'No configurado', '配置说明：': 'Notas de configuración:', '用户:': 'Usuario:', '类型:': 'Tipo:', '金额:': 'Monto:', '创建时间:': 'Creado:', '支付时间:': 'Pagado:',
    '地图': 'Mapa', '站点地图': 'Mapa de sitios', '新增站点': 'Agregar sitio', '创建一个新的运营站点。': 'Crear un nuevo sitio operativo.', '站点名称': 'Nombre del sitio', '营业时间（可选）': 'Horario (opcional)', '搜索地址（自动填充经纬度）': 'Buscar dirección (completa las coordenadas)', '地图选点': 'Seleccionar en el mapa', '提示：搜索地址后自动定位，也可点击地图任意位置更新坐标': 'Consejo: busca una dirección para ubicarla o haz clic en el mapa para actualizar las coordenadas', '纬度': 'Latitud', '经度': 'Longitud', '暂无站点': 'No hay sitios',
    '基本信息': 'Información básica', '状态监控': 'Monitoreo del estado', '历史记录': 'Historial', '远程控制': 'Control remoto', '二维码': 'Códigos QR', '状态': 'Estado', '当前状态': 'Estado actual', '最后在线时间': 'Última conexión', 'EVSE 列表': 'Lista de EVSE', '历史记录功能待实现': 'El historial aún no está disponible', '启动充电': 'Iniciar carga', '停止充电': 'Detener carga', '重置充电桩': 'Restablecer cargador', '解锁连接器': 'Desbloquear conector', '配置管理': 'Gestión de configuración', '暂无connector信息': 'No hay información del conector',
  },
} as const;

// 页面仍存在的旧 JSX/弹窗文案统一从这里翻译。该表只负责界面文案，
// 不翻译租户名称、站点名称等业务数据。
const moreLegacyText = {
  en: {
    '充电站位置': 'Charging station location', 'Google Maps API 密钥未配置': 'Google Maps API key is not configured', '地图加载失败，请检查网络连接或 Google Cloud 中 API/引荐来源限制': 'Map failed to load. Check the network connection and Google Cloud API/referrer restrictions', '地图服务加载失败': 'Map service failed to load', '地图服务未就绪': 'Map service is not ready', '地址搜索失败': 'Address search failed', '获取地址详情失败': 'Failed to get address details', '搜索中...': 'Searching...',
    '暂无数据': 'No data', '没有找到数据': 'No data found', '请尝试调整筛选条件': 'Try adjusting the filters', '已复制到剪贴板': 'Copied to clipboard', '复制失败，请手动复制': 'Copy failed. Please copy manually', '请填写租户名称': 'Enter a tenant name', '请填写租户管理员用户名': 'Enter the tenant administrator username', '请填写租户管理员邮箱': 'Enter the tenant administrator email', '确定要删除该租户吗？此操作不可恢复。': 'Delete this tenant? This action cannot be undone.', '已删除': 'Deleted', '删除失败': 'Delete failed', '当前账号不是超级管理员，无法创建/管理租户。': 'This account is not a super administrator and cannot manage tenants.', '添加租户': 'Add tenant', '共': 'Total', '个': '', '租户 ID': 'Tenant ID', '租户 ID：': 'Tenant ID:', '用户名：': 'Username:', '密码：': 'Password:', '复制': 'Copy', '请尽快让租户管理员登录后修改密码。': 'Ask the tenant administrator to sign in and change the password promptly.', '已创建租户（未创建租户管理员账号）。': 'Tenant created (no tenant administrator account was created).', '租户名称 *': 'Tenant name *', '例如：EsLatin Colombia': 'Example: EsLatin Colombia', '例如：tenant1.eslatin.com.co': 'Example: tenant1.eslatin.com.co', '用于该租户登录后台（建议开启）。': 'Used by the tenant to sign in to the admin portal (recommended).', '已开启': 'Enabled', '已关闭': 'Disabled', '例如：tenant_admin': 'Example: tenant_admin', '例如：admin@tenant.com': 'Example: admin@tenant.com', '生成': 'Generate', '完成': 'Done',
    '调余额': 'Adjust balance', '金额（正数入账）': 'Amount (positive credits balance)', '余额 (COP)': 'Balance (COP)', '邮箱': 'Email', '姓名': 'Name', '角色': 'Role', '加载失败': 'Failed to load', '删除': 'Delete', '编辑': 'Edit',
    '站点 ID': 'Site ID', '站点详情': 'Site details', '创建站点': 'Create site', '保存修改': 'Save changes', '返回': 'Back', '设备': 'Devices', '站点下充电桩': 'Chargers at this site', '暂无充电桩': 'No chargers', '加载站点详情失败': 'Failed to load site details', '充电桩详情': 'Charger details', '连接器': 'Connector', '连接器状态': 'Connector status', '启动': 'Start', '停止': 'Stop',
    '支付详情': 'Payment details', '支付状态': 'Payment status', '付款方式': 'Payment method', '订单号': 'Order number', '金额': 'Amount', '币种': 'Currency', '更新时间': 'Updated at', '加载支付订单失败': 'Failed to load payment order', '返回支付列表': 'Back to payments',
    '交易详情': 'Transaction details', '加载交易详情失败': 'Failed to load transaction details', '会话详情': 'Session details', '加载会话失败': 'Failed to load session', '开始时间': 'Start time', '结束时间': 'End time', '充电量（kWh）': 'Energy (kWh)', '费用': 'Cost', '未知': 'Unknown',
    '刷新页面': 'Refresh page', '保存成功': 'Saved successfully', '保存失败': 'Save failed', '请求失败': 'Request failed', '操作成功': 'Operation successful',
    'OCPP 身份': 'OCPP identity', 'OCPP 交易号': 'OCPP transaction ID', '没有可停止的活动会话': 'There is no active session to stop', '未提供': 'Not provided', '调整原因（必填）': 'Adjustment reason (required)', '选择已注册配置键': 'Select a registered configuration key', '搜索租户名称 / 域名...': 'Search tenant name / domain...', '搜索 OCPP 交易号、OCPP 身份...': 'Search OCPP transaction ID or identity...', '搜索 OCPP 身份、描述...': 'Search OCPP identity or description...', '租户、首个管理员和成员关系将以单个事务创建。': 'The tenant, first administrator, and membership are created in one transaction.', '例如：CO.BOGOTA:CP-01': 'Example: CO.BOGOTA:CP-01',
  },
  es: {
    '充电站位置': 'Ubicación de la estación', 'Google Maps API 密钥未配置': 'La clave de Google Maps API no está configurada', '地图加载失败，请检查网络连接或 Google Cloud 中 API/引荐来源限制': 'No se pudo cargar el mapa. Verifica la red y las restricciones de API/referentes en Google Cloud', '地图服务加载失败': 'No se pudo cargar el servicio de mapas', '地图服务未就绪': 'El servicio de mapas no está listo', '地址搜索失败': 'No se pudo buscar la dirección', '获取地址详情失败': 'No se pudieron obtener los detalles de la dirección', '搜索中...': 'Buscando...',
    '暂无数据': 'No hay datos', '没有找到数据': 'No se encontraron datos', '请尝试调整筛选条件': 'Intenta ajustar los filtros', '已复制到剪贴板': 'Copiado al portapapeles', '复制失败，请手动复制': 'No se pudo copiar. Copia el texto manualmente', '请填写租户名称': 'Ingresa el nombre del inquilino', '请填写租户管理员用户名': 'Ingresa el usuario administrador del inquilino', '请填写租户管理员邮箱': 'Ingresa el correo del administrador del inquilino', '确定要删除该租户吗？此操作不可恢复。': '¿Eliminar este inquilino? Esta acción no se puede deshacer.', '已删除': 'Eliminado', '删除失败': 'No se pudo eliminar', '当前账号不是超级管理员，无法创建/管理租户。': 'Esta cuenta no es superadministradora y no puede gestionar inquilinos.', '添加租户': 'Agregar inquilino', '共': 'Total', '个': '', '租户 ID': 'ID del inquilino', '租户 ID：': 'ID del inquilino:', '用户名：': 'Usuario:', '密码：': 'Contraseña:', '复制': 'Copiar', '请尽快让租户管理员登录后修改密码。': 'Indica al administrador del inquilino que inicie sesión y cambie la contraseña cuanto antes.', '已创建租户（未创建租户管理员账号）。': 'Inquilino creado (no se creó una cuenta administradora).', '租户名称 *': 'Nombre del inquilino *', '例如：EsLatin Colombia': 'Ejemplo: EsLatin Colombia', '例如：tenant1.eslatin.com.co': 'Ejemplo: tenant1.eslatin.com.co', '用于该租户登录后台（建议开启）。': 'Se usa para que el inquilino acceda al portal (recomendado).', '已开启': 'Activado', '已关闭': 'Desactivado', '例如：tenant_admin': 'Ejemplo: tenant_admin', '例如：admin@tenant.com': 'Ejemplo: admin@tenant.com', '生成': 'Generar', '完成': 'Listo',
    '调余额': 'Ajustar saldo', '金额（正数入账）': 'Monto (los positivos abonan saldo)', '余额 (COP)': 'Saldo (COP)', '邮箱': 'Correo electrónico', '姓名': 'Nombre', '角色': 'Rol', '加载失败': 'No se pudo cargar', '删除': 'Eliminar', '编辑': 'Editar',
    '站点 ID': 'ID del sitio', '站点详情': 'Detalles del sitio', '创建站点': 'Crear sitio', '保存修改': 'Guardar cambios', '返回': 'Volver', '设备': 'Dispositivos', '站点下充电桩': 'Cargadores del sitio', '暂无充电桩': 'No hay cargadores', '加载站点详情失败': 'No se pudieron cargar los detalles del sitio', '充电桩详情': 'Detalles del cargador', '连接器': 'Conector', '连接器状态': 'Estado del conector', '启动': 'Iniciar', '停止': 'Detener',
    '支付详情': 'Detalles del pago', '支付状态': 'Estado del pago', '付款方式': 'Método de pago', '订单号': 'Número de pedido', '金额': 'Monto', '币种': 'Moneda', '更新时间': 'Actualizado', '加载支付订单失败': 'No se pudo cargar el pedido de pago', '返回支付列表': 'Volver a pagos',
    '交易详情': 'Detalles de la transacción', '加载交易详情失败': 'No se pudieron cargar los detalles de la transacción', '会话详情': 'Detalles de la sesión', '加载会话失败': 'No se pudo cargar la sesión', '开始时间': 'Inicio', '结束时间': 'Fin', '充电量（kWh）': 'Energía (kWh)', '费用': 'Costo', '未知': 'Desconocido',
    '刷新页面': 'Actualizar página', '保存成功': 'Guardado correctamente', '保存失败': 'No se pudo guardar', '请求失败': 'No se pudo completar la solicitud', '操作成功': 'Operación exitosa',
    'OCPP 身份': 'Identidad OCPP', 'OCPP 交易号': 'ID de transacción OCPP', '没有可停止的活动会话': 'No hay una sesión activa para detener', '未提供': 'No disponible', '调整原因（必填）': 'Motivo del ajuste (obligatorio)', '选择已注册配置键': 'Selecciona una clave de configuración registrada', '搜索租户名称 / 域名...': 'Buscar nombre o dominio del inquilino...', '搜索 OCPP 交易号、OCPP 身份...': 'Buscar ID de transacción o identidad OCPP...', '搜索 OCPP 身份、描述...': 'Buscar identidad OCPP o descripción...', '租户、首个管理员和成员关系将以单个事务创建。': 'El inquilino, el primer administrador y la membresía se crean en una sola transacción.', '例如：CO.BOGOTA:CP-01': 'Ejemplo: CO.BOGOTA:CP-01',
  },
} as const;

// 页面业务组件历史上直接写入了中文文案。集中翻译这些展示文本，保证旧页面
// 也能随全局语言切换，不让每个页面各自实现一套语言状态。
const pageText = {
  en: {
    '加载中...': 'Loading...', '加载地图中...': 'Loading map...', '加载失败，请刷新页面重试': 'Failed to load. Refresh and try again.',
    '站点管理': 'Sites', '以站点为单位管理充电桩与运营数据': 'Manage chargers and operations by site', '新增站点': 'Add site',
    '站点列表': 'Site list', '站点': 'Site', '地址': 'Address', '充电桩': 'Chargers', '在线': 'Online', '操作': 'Actions',
    '详情': 'Details', '暂无站点': 'No sites', '取消': 'Cancel', '创建': 'Create', '创建中...': 'Creating...',
    '活跃会话': 'Active sessions', '实时监控进行中的充电会话（5 秒刷新）': 'Monitor active charging sessions (refreshes every 5 seconds)',
    '刷新': 'Refresh', '进行中': 'In progress', '当前无进行中的充电会话': 'No active charging sessions', '会话 ID': 'Session ID',
    '用户': 'User', '已充电量': 'Energy', '功率': 'Power', '时长(分)': 'Duration (min)', '状态': 'Status',
    '支付管理': 'Payments', '查看和管理所有支付订单（Wompi）': 'View and manage payment orders (Wompi)', '订单状态': 'Order status',
    '全部状态': 'All statuses', '已创建': 'Created', '处理中': 'Processing', '已批准': 'Approved', '已拒绝': 'Declined',
    '错误': 'Error', '已过期': 'Expired', '订单类型': 'Order type', '全部类型': 'All types', '钱包充值': 'Wallet top-up',
    '充电支付': 'Charging payment', '支付订单列表': 'Payment orders', '查看详情': 'View details', '暂无支付订单': 'No payment orders',
    '统计报表': 'Reports', '查看运营数据和趋势分析': 'View operational data and trends', '导出报表': 'Export report', '导出失败': 'Export failed',
    '收入报表': 'Revenue report', '充电量报表': 'Energy report', '订单报表': 'Orders report', '暂无数据': 'No data',
    '交易管理': 'Transactions', '查看和管理所有充电交易记录': 'View and manage charging transactions', '导出数据': 'Export data',
    '交易列表': 'Transaction list', '交易 ID': 'Transaction ID', '充电桩 ID': 'Charger ID', '开始时间': 'Start time',
    '结束时间': 'End time', '已完成': 'Completed', '已取消': 'Cancelled',
    '没有找到交易记录': 'No transactions found', '地图视图': 'Map', '站点地图': 'Site map', '地图加载中...': 'Loading map...',
    '用户统计': 'User statistics', '告警统计': 'Alert statistics', '充电桩总数': 'Total chargers', '充电桩状态': 'Charger status',
    '订单': 'Orders', '充电量': 'Energy', '总数': 'Total', '健康': 'Health', '运营': 'Operations',
    '收入': 'Revenue', '加载失败': 'Failed to load', '在线/总桩': 'Online/Total', '充电量趋势': 'Energy trend',
    '收入趋势': 'Revenue trend', '订单趋势': 'Orders trend', '订单数': 'Order count',
    '按站点拆分：在线/故障、订单、充电量、收入（点击行可切换站点视角）': 'By site: online/faults, orders, energy and revenue (click a row to switch site view)',
    '选择站点': 'Select site', '全部站点（租户汇总）': 'All sites (tenant summary)',
    '租户汇总 + 站点维度运营分析': 'Tenant summary + site operations analysis',
    '今日数据': 'Today', '今日收入': 'Today revenue', '严重': 'Critical', '警告': 'Warning', '信息': 'Info',
    '充电中': 'Charging', '可用': 'Available', '故障': 'Faulted', '系统设置': 'Settings', '个人设置': 'Profile settings',
    '个人信息': 'Profile', '退出登录': 'Log out', '切换租户': 'Switch tenant', '当前': 'Current', '未选择租户': 'No tenant selected',
    '调整余额': 'Adjust balance', '确认': 'Confirm', '解决': 'Resolve', '提交中…': 'Submitting…', '活跃': 'Active', '禁用': 'Disabled',
    '超级管理员': 'Super Administrator', '管理员': 'Administrator',
    '搜索订单号、用户邮箱...': 'Search order number or user email...',
    '搜索站点 ID/名称/地址...': 'Search site ID/name/address...', '创建一个新的运营站点。': 'Create a new operating site.',
    '站点名称': 'Site name', '营业时间（可选）': 'Business hours (optional)', '筛选状态': 'Filter status',
    '最近 7 天': 'Last 7 days', '最近 30 天': 'Last 30 days', '最近 90 天': 'Last 90 days',
    '共 0 个站点': '0 sites', '列表': 'List', '搜索交易 ID、充电桩 ID...': 'Search transaction ID or charger ID...',
    '充电量 (kWh)': 'Energy (kWh)', '时长 (分钟)': 'Duration (min)', '导出功能待实现': 'Export is not implemented yet',
    '新站点': 'New site', '提示：搜索地址后自动定位，也可点击地图任意位置更新坐标': 'Tip: search an address to locate it, or click the map to update coordinates',
    '搜索地址（自动填充经纬度）': 'Search address (fills coordinates automatically)', '地图选点': 'Select on map', '纬度': 'Latitude', '经度': 'Longitude',
    '站点 ID': 'Site ID', '共': 'Total', '个站点': 'sites',
    '账户余额': 'Account balance', '充电记录': 'Charging records', '用户管理': 'User management',
    '告警管理': 'Alert management', '查看和处理系统告警': 'View and handle system alerts', '严重程度': 'Severity', '全部': 'All', '搜索告警 ID、充电桩 ID、描述...': 'Search alert ID, charger ID, description...',
    '待处理': 'Pending', '已确认': 'Acknowledged', '已解决': 'Resolved', '告警已确认': 'Alert acknowledged', '确认失败': 'Acknowledgement failed', '告警已解决': 'Alert resolved', '解决失败': 'Resolution failed', '启用': 'Enabled', '没有找到告警': 'No alerts found', '告警规则': 'Alert rules', '加载规则...': 'Loading rules...', '暂无告警规则，可通过 API 创建': 'No alert rules. Create them via the API.',
    '描述': 'Description', '发生时间': 'Occurred at', '过去 7 天收入趋势': 'Revenue trend over the last 7 days', '过去 30 天收入趋势': 'Revenue trend over the last 30 days', '过去 90 天收入趋势': 'Revenue trend over the last 90 days',
    '过去 7 天充电量趋势': 'Energy trend over the last 7 days', '过去 30 天充电量趋势': 'Energy trend over the last 30 days', '过去 90 天充电量趋势': 'Energy trend over the last 90 days',
    '过去 7 天订单趋势': 'Order trend over the last 7 days', '过去 30 天订单趋势': 'Order trend over the last 30 days', '过去 90 天订单趋势': 'Order trend over the last 90 days',
    '暂无 App 用户': 'No App users', '管理员用户': 'Administrator users', '暂无管理员用户': 'No administrator users', '用户名': 'Username', '余额 (COP)': 'Balance (COP)', '金额（正数入账）': 'Amount (positive credits balance)', '备注（可选）': 'Note (optional)',
    '姓名': 'Name', '保存资料': 'Save profile', '修改密码': 'Change password', '保存密码': 'Save password', '租户设置': 'Tenant settings', '系统配置': 'System configuration', '保存租户资料': 'Save tenant profile', '保存': 'Save', '配置键': 'Config key', '配置值': 'Config value', '当前密码': 'Current password', '新密码（至少 8 位）': 'New password (at least 8 characters)', '确认新密码': 'Confirm new password',
    '管理系统配置和个人设置': 'Manage system configuration and personal settings', '用户名：': 'Username:', '当前租户：': 'Current tenant:', '未选择': 'Not selected', '域名（可选）': 'Domain (optional)',
    '邮箱': 'Email', '角色': 'Role', '确定': 'Confirm', '请输入非零金额（正数入账，负数扣减）': 'Enter a non-zero amount (positive adds, negative deducts)', '调整失败': 'Balance adjustment failed', '租户资料已更新': 'Tenant profile updated', '个人资料已更新': 'Profile updated', '密码修改成功': 'Password changed successfully', '密码修改失败': 'Password change failed', '新密码至少需要 8 位': 'The new password must be at least 8 characters', '两次输入的新密码不一致': 'The passwords do not match', '在 Google 地图上查看各站点位置（数据来自站点列表）': 'View all site locations on Google Maps (data from the site list)', '加载站点数据…': 'Loading site data…',
    '搜索站点名称/地址...': 'Search site name or address...', '请填写站点名称': 'Enter a site name', '请填写站点地址': 'Enter a site address', '请填写正确的经纬度': 'Enter valid coordinates', '创建失败': 'Creation failed',
    '站点名称 *': 'Site name *', '地址 *': 'Address *', '纬度 *': 'Latitude *', '经度 *': 'Longitude *', '例如：00:00-24:00': 'Example: 00:00-24:00',
    '默认站点': 'Default site', '未设置': 'Not configured', '无权限编辑站点信息': 'You do not have permission to edit site information', '站点名称/地址不能为空': 'Site name and address are required', '已保存': 'Saved',
    '无权限编辑定价': 'You do not have permission to edit pricing', '请填写正确的电价（>0）': 'Enter a valid price (>0)', '站点定价已保存': 'Site pricing saved', '保存定价失败': 'Failed to save pricing',
    '无权限执行绑定操作': 'You do not have permission to bind chargers', '加载可绑定充电桩失败': 'Failed to load available chargers', '请至少选择一个充电桩': 'Select at least one charger', '绑定/迁移成功': 'Charger binding/migration completed', '绑定失败': 'Binding failed',
    '无权限添加充电桩': 'You do not have permission to add chargers', '请填写充电桩硬件码（charge_point_id）': 'Enter the charger hardware identifier', '枪口数量需为 1-16 的整数': 'The EVSE count must be an integer from 1 to 16', '充电桩已添加并绑定到站点': 'Charger added and bound to this site',
    '无权限编辑': 'You do not have permission to edit', '退出编辑': 'Exit edit mode', '添加充电桩': 'Add charger', '绑定充电桩': 'Bind chargers', '保存中...': 'Saving...', '保存站点信息': 'Save site information', '站点信息': 'Site information', '营业时间': 'Business hours',
    '输入地址后选择建议，将自动填充经纬度': 'Enter an address and select a suggestion to fill the coordinates', '站点定价（每kWh）': 'Site price (per kWh)', '保存定价': 'Save pricing', '当前生效电价：': 'Current effective price: ',
    '点击地图可自动填充经纬度（lat/lng），用于站点定位。': 'Click the map to fill the site coordinates.', '地图展示站点位置，点击“编辑”按钮后可修改位置。': 'The map shows the site location. Select Edit to change it.',
    '厂商/型号': 'Vendor / model', '最后在线': 'Last online', '点击查看详情': 'Open details', '覆盖定价': 'Override pricing', '暂无充电桩，请先绑定。': 'No chargers are bound to this site.',
    '设置充电桩覆盖定价': 'Set charger price override', '桩级覆盖价优先于站点默认价（用于少数桩特殊价格）。': 'A charger-level price overrides the site default.', '覆盖电价（每kWh）': 'Override price (per kWh)', '例如：1.50': 'Example: 1.50', '覆盖定价已保存': 'Price override saved',
    '绑定充电桩到站点': 'Bind chargers to site', '从“可绑定”列表中选择充电桩，系统将迁移到当前站点。': 'Select chargers to move and bind to this site.', '选择': 'Select', '当前站点': 'Current site', '未分配': 'Unassigned', '当前没有可绑定的充电桩。': 'No chargers are available to bind.', '已选择': 'Selected:', '绑定/迁移': 'Bind / move',
    '在站点下添加充电桩': 'Add a charger to this site', '输入充电桩硬件码进行预注册，并自动绑定到当前站点。': 'Pre-register a charger using its hardware identifier and bind it to this site.', '充电桩硬件码 *': 'Charger hardware identifier *', '例如：635310462（只能字母数字）': 'Example: 635310462 (letters and numbers only)', '该值必须与充电桩 WebSocket 连接参数一致。': 'This value must match the identifier used by the charger WebSocket connection.', '厂商（可选）': 'Vendor (optional)', '型号（可选）': 'Model (optional)', '枪口数量（EVSE 数）': 'EVSE count', '连接器类型': 'Connector type', '创建并绑定': 'Create and bind',
    'available': 'Available', 'charging': 'Charging', 'faulted': 'Faulted', 'unavailable': 'Unavailable', 'Available': 'Available', 'Charging': 'Charging', 'Faulted': 'Faulted', 'Unavailable': 'Unavailable', 'Offline': 'Offline', '处理中...': 'Processing...',
    '地图加载失败，请检查网络连接、项目结算账号以及 Maps JavaScript API 是否启用': 'Map failed to load. Check the network, project billing account, and whether Maps JavaScript API is enabled.',
    '在站点详情页查看、绑定和迁移该站点的充电桩。': 'View, bind, and move chargers from the site details page.',
    '对账成功': 'Reconciliation completed', '支付订单详情': 'Payment order details', '订单 ID': 'Order ID', '参考号': 'Reference', '用户邮箱': 'User email', 'Wompi 交易 ID': 'Wompi transaction ID', '创建时间': 'Created at', '支付时间': 'Paid at', '过期时间': 'Expires at', 'Webhook 事件记录': 'Webhook event history', '元数据': 'Metadata',
    'Private Key 状态': 'Private Key status', 'Private Key 和 Integrity Secret 存储在服务端环境变量中': 'Private Key and Integrity Secret are stored in server environment variables', '这些敏感信息不会在界面中显示': 'Sensitive values are never displayed in the interface', '如需修改配置，请更新服务端环境变量并重启服务': 'Update the server environment variables and restart the service to change the configuration', 'Webhook URL 在 Wompi 后台配置': 'Configure the Webhook URL in Wompi', '当前应用内支付功能默认关闭。用户余额可在用户管理中调整；接入第三方支付后再启用服务端支付配置。': 'In-app payments are disabled by default. Adjust balances in User Management and enable server payment settings after integrating a payment provider.', 'Wompi 配置信息': 'Wompi configuration', 'Private Key 和 Integrity Secret 通过环境变量配置，不在界面中显示': 'Private Key and Integrity Secret are configured through environment variables and are not displayed.',
    '所有二维码生成成功': 'All QR codes were generated', '二维码生成成功': 'QR code generated', '生成二维码失败': 'Failed to generate QR code', '远程启动充电请求已发送': 'Remote start request sent', '远程启动充电失败': 'Remote start failed', '远程停止充电请求已发送': 'Remote stop request sent', '远程停止充电失败': 'Remote stop failed', '确定要重置充电桩吗？': 'Reset this charger?', '重置请求已发送': 'Reset request sent', '重置失败': 'Reset failed', '加载失败，充电桩不存在或已被删除': 'Failed to load. The charger does not exist or was deleted', '厂商': 'Vendor', '型号': 'Model', '序列号': 'Serial number', '固件版本': 'Firmware version', '位置': 'Location', '定价': 'Pricing',
    '账户已被禁用，请联系管理员': 'This account is disabled. Contact an administrator.', '服务器内部错误，请联系技术支持': 'Server error. Contact technical support.',
    '生成所有二维码': 'Generate all QR codes', '每个连接器对应一个二维码，用户扫码后可启动充电': 'Each connector has a QR code that users can scan to start charging', '生成中': 'Generating', '下载': 'Download', '二维码未生成': 'QR code not generated',
    '沙盒环境': 'Sandbox', '生产环境': 'Production', '测试': 'Test', '生产': 'Production',
    '创建租户后可选自动创建一个“租户管理员账号”，用于该租户登录运营后台。': 'Optionally create a tenant administrator account for access to the operations portal.',
    '对账': 'Reconcile', '订单信息': 'Order information', '已处理': 'Processed', '未处理': 'Not processed', '处理时间:': 'Processed at:',
  },
  es: {
    '加载中...': 'Cargando...', '加载地图中...': 'Cargando mapa...', '加载失败，请刷新页面重试': 'No se pudo cargar. Actualiza e inténtalo de nuevo.',
    '站点管理': 'Sitios', '以站点为单位管理充电桩与运营数据': 'Gestiona cargadores y operaciones por sitio', '新增站点': 'Agregar sitio',
    '站点列表': 'Lista de sitios', '站点': 'Sitio', '地址': 'Dirección', '充电桩': 'Cargadores', '在线': 'En línea', '操作': 'Acciones',
    '详情': 'Detalles', '暂无站点': 'No hay sitios', '取消': 'Cancelar', '创建': 'Crear', '创建中...': 'Creando...',
    '活跃会话': 'Sesiones activas', '实时监控进行中的充电会话（5 秒刷新）': 'Monitorea sesiones activas (actualiza cada 5 segundos)',
    '刷新': 'Actualizar', '进行中': 'En curso', '当前无进行中的充电会话': 'No hay sesiones activas', '会话 ID': 'ID de sesión',
    '用户': 'Usuario', '已充电量': 'Energía', '功率': 'Potencia', '时长(分)': 'Duración (min)', '状态': 'Estado',
    '支付管理': 'Pagos', '查看和管理所有支付订单（Wompi）': 'Consulta y administra pagos (Wompi)', '订单状态': 'Estado del pedido',
    '全部状态': 'Todos los estados', '已创建': 'Creado', '处理中': 'Procesando', '已批准': 'Aprobado', '已拒绝': 'Rechazado',
    '错误': 'Error', '已过期': 'Expirado', '订单类型': 'Tipo de pedido', '全部类型': 'Todos los tipos', '钱包充值': 'Recarga de billetera',
    '充电支付': 'Pago de carga', '支付订单列表': 'Pedidos de pago', '查看详情': 'Ver detalles', '暂无支付订单': 'No hay pedidos de pago',
    '统计报表': 'Reportes', '查看运营数据和趋势分析': 'Consulta datos operativos y tendencias', '导出报表': 'Exportar reporte', '导出失败': 'No se pudo exportar',
    '收入报表': 'Reporte de ingresos', '充电量报表': 'Reporte de energía', '订单报表': 'Reporte de pedidos', '暂无数据': 'Sin datos',
    '交易管理': 'Transacciones', '查看和管理所有充电交易记录': 'Consulta y administra transacciones', '导出数据': 'Exportar datos',
    '交易列表': 'Lista de transacciones', '交易 ID': 'ID de transacción', '充电桩 ID': 'ID del cargador', '开始时间': 'Inicio',
    '结束时间': 'Fin', '已完成': 'Completado', '已取消': 'Cancelado',
    '没有找到交易记录': 'No se encontraron transacciones', '地图视图': 'Mapa', '站点地图': 'Mapa de sitios', '地图加载中...': 'Cargando mapa...',
    '用户统计': 'Usuarios', '告警统计': 'Alertas', '充电桩总数': 'Total de cargadores', '充电桩状态': 'Estado de cargadores',
    '订单': 'Pedidos', '充电量': 'Energía', '总数': 'Total', '健康': 'Salud', '运营': 'Operaciones',
    '收入': 'Ingresos', '加载失败': 'No se pudo cargar', '在线/总桩': 'En línea/Total', '充电量趋势': 'Tendencia de energía',
    '收入趋势': 'Tendencia de ingresos', '订单趋势': 'Tendencia de pedidos', '订单数': 'Cantidad de pedidos',
    '按站点拆分：在线/故障、订单、充电量、收入（点击行可切换站点视角）': 'Por sitio: en línea/fallos, pedidos, energía e ingresos (haz clic en una fila para cambiar de sitio)',
    '选择站点': 'Seleccionar sitio', '全部站点（租户汇总）': 'Todos los sitios (resumen)',
    '租户汇总 + 站点维度运营分析': 'Resumen del inquilino + operaciones por sitio',
    '今日数据': 'Hoy', '今日收入': 'Ingresos de hoy', '严重': 'Crítico', '警告': 'Advertencia', '信息': 'Información',
    '充电中': 'Cargando', '可用': 'Disponible', '故障': 'Fallo', '系统设置': 'Configuración', '个人设置': 'Perfil',
    '个人信息': 'Información personal', '退出登录': 'Cerrar sesión', '切换租户': 'Cambiar inquilino', '当前': 'Actual', '未选择租户': 'Sin inquilino',
    '调整余额': 'Ajustar saldo', '确认': 'Confirmar', '解决': 'Resolver', '提交中…': 'Enviando…', '活跃': 'Activo', '禁用': 'Deshabilitado',
    '超级管理员': 'Superadministrador', '管理员': 'Administrador',
    '搜索订单号、用户邮箱...': 'Buscar número de pedido o correo...',
    '搜索站点 ID/名称/地址...': 'Buscar ID/nombre/dirección del sitio...', '创建一个新的运营站点。': 'Crear un nuevo sitio operativo.',
    '站点名称': 'Nombre del sitio', '营业时间（可选）': 'Horario (opcional)', '筛选状态': 'Filtrar estado',
    '最近 7 天': 'Últimos 7 días', '最近 30 天': 'Últimos 30 días', '最近 90 天': 'Últimos 90 días',
    '共 0 个站点': '0 sitios', '列表': 'Lista', '搜索交易 ID、充电桩 ID...': 'Buscar ID de transacción o cargador...',
    '充电量 (kWh)': 'Energía (kWh)', '时长 (分钟)': 'Duración (min)', '导出功能待实现': 'La exportación aún no está disponible',
    '新站点': 'Nuevo sitio', '提示：搜索地址后自动定位，也可点击地图任意位置更新坐标': 'Consejo: busca una dirección para ubicarla o haz clic en el mapa para actualizar las coordenadas',
    '搜索地址（自动填充经纬度）': 'Buscar dirección (completa las coordenadas)', '地图选点': 'Seleccionar en el mapa', '纬度': 'Latitud', '经度': 'Longitud',
    '站点 ID': 'ID del sitio', '共': 'Total', '个站点': 'sitios',
    '账户余额': 'Saldo de la cuenta', '充电记录': 'Registros de carga', '用户管理': 'Gestión de usuarios',
    '告警管理': 'Gestión de alertas', '查看和处理系统告警': 'Consulta y gestiona alertas del sistema', '严重程度': 'Severidad', '全部': 'Todos', '搜索告警 ID、充电桩 ID、描述...': 'Buscar ID de alerta, cargador o descripción...',
    '待处理': 'Pendiente', '已确认': 'Confirmada', '已解决': 'Resuelta', '告警已确认': 'Alerta confirmada', '确认失败': 'No se pudo confirmar la alerta', '告警已解决': 'Alerta resuelta', '解决失败': 'No se pudo resolver la alerta', '启用': 'Activada', '没有找到告警': 'No se encontraron alertas', '告警规则': 'Reglas de alertas', '加载规则...': 'Cargando reglas...', '暂无告警规则，可通过 API 创建': 'No hay reglas de alertas. Créelas mediante la API.',
    '描述': 'Descripción', '发生时间': 'Ocurrió en', '过去 7 天收入趋势': 'Tendencia de ingresos de los últimos 7 días', '过去 30 天收入趋势': 'Tendencia de ingresos de los últimos 30 días', '过去 90 天收入趋势': 'Tendencia de ingresos de los últimos 90 días',
    '过去 7 天充电量趋势': 'Tendencia de energía de los últimos 7 días', '过去 30 天充电量趋势': 'Tendencia de energía de los últimos 30 días', '过去 90 天充电量趋势': 'Tendencia de energía de los últimos 90 días',
    '过去 7 天订单趋势': 'Tendencia de pedidos de los últimos 7 días', '过去 30 天订单趋势': 'Tendencia de pedidos de los últimos 30 días', '过去 90 天订单趋势': 'Tendencia de pedidos de los últimos 90 días',
    '暂无 App 用户': 'No hay usuarios de App', '管理员用户': 'Usuarios administradores', '暂无管理员用户': 'No hay usuarios administradores', '用户名': 'Usuario', '余额 (COP)': 'Saldo (COP)', '金额（正数入账）': 'Monto (los positivos abonan saldo)', '备注（可选）': 'Nota (opcional)',
    '姓名': 'Nombre', '保存资料': 'Guardar perfil', '修改密码': 'Cambiar contraseña', '保存密码': 'Guardar contraseña', '租户设置': 'Configuración del inquilino', '系统配置': 'Configuración del sistema', '保存租户资料': 'Guardar perfil del inquilino', '保存': 'Guardar', '配置键': 'Clave de configuración', '配置值': 'Valor de configuración', '当前密码': 'Contraseña actual', '新密码（至少 8 位）': 'Nueva contraseña (mínimo 8 caracteres)', '确认新密码': 'Confirmar nueva contraseña',
    '管理系统配置和个人设置': 'Gestiona la configuración del sistema y tus preferencias', '用户名：': 'Usuario:', '当前租户：': 'Inquilino actual:', '未选择': 'No seleccionado', '域名（可选）': 'Dominio (opcional)',
    '邮箱': 'Correo electrónico', '角色': 'Rol', '确定': 'Confirmar', '请输入非零金额（正数入账，负数扣减）': 'Ingresa un monto distinto de cero (positivo suma, negativo resta)', '调整失败': 'No se pudo ajustar el saldo', '租户资料已更新': 'Perfil del inquilino actualizado', '个人资料已更新': 'Perfil actualizado', '密码修改成功': 'Contraseña cambiada correctamente', '密码修改失败': 'No se pudo cambiar la contraseña', '新密码至少需要 8 位': 'La nueva contraseña debe tener al menos 8 caracteres', '两次输入的新密码不一致': 'Las contraseñas no coinciden', '在 Google 地图上查看各站点位置（数据来自站点列表）': 'Consulta todos los sitios en Google Maps (datos de la lista de sitios)', '加载站点数据…': 'Cargando datos de sitios…',
    '搜索站点名称/地址...': 'Buscar por nombre o dirección...', '请填写站点名称': 'Ingresa el nombre del sitio', '请填写站点地址': 'Ingresa la dirección del sitio', '请填写正确的经纬度': 'Ingresa coordenadas válidas', '创建失败': 'No se pudo crear',
    '站点名称 *': 'Nombre del sitio *', '地址 *': 'Dirección *', '纬度 *': 'Latitud *', '经度 *': 'Longitud *', '例如：00:00-24:00': 'Ejemplo: 00:00-24:00',
    '默认站点': 'Sitio predeterminado', '未设置': 'Sin configurar', '无权限编辑站点信息': 'No tienes permiso para editar la información del sitio', '站点名称/地址不能为空': 'El nombre y la dirección son obligatorios', '已保存': 'Guardado',
    '无权限编辑定价': 'No tienes permiso para editar precios', '请填写正确的电价（>0）': 'Ingresa un precio válido (>0)', '站点定价已保存': 'Precio del sitio guardado', '保存定价失败': 'No se pudo guardar el precio',
    '无权限执行绑定操作': 'No tienes permiso para vincular cargadores', '加载可绑定充电桩失败': 'No se pudieron cargar los cargadores disponibles', '请至少选择一个充电桩': 'Selecciona al menos un cargador', '绑定/迁移成功': 'Vinculación o traslado completado', '绑定失败': 'No se pudo vincular',
    '无权限添加充电桩': 'No tienes permiso para agregar cargadores', '请填写充电桩硬件码（charge_point_id）': 'Ingresa el identificador de hardware del cargador', '枪口数量需为 1-16 的整数': 'La cantidad de EVSE debe ser un entero entre 1 y 16', '充电桩已添加并绑定到站点': 'Cargador agregado y vinculado al sitio',
    '无权限编辑': 'No tienes permiso para editar', '退出编辑': 'Salir de edición', '添加充电桩': 'Agregar cargador', '绑定充电桩': 'Vincular cargadores', '保存中...': 'Guardando...', '保存站点信息': 'Guardar información del sitio', '站点信息': 'Información del sitio', '营业时间': 'Horario',
    '输入地址后选择建议，将自动填充经纬度': 'Ingresa una dirección y selecciona una sugerencia para completar las coordenadas', '站点定价（每kWh）': 'Precio del sitio (por kWh)', '保存定价': 'Guardar precio', '当前生效电价：': 'Precio vigente: ',
    '点击地图可自动填充经纬度（lat/lng），用于站点定位。': 'Haz clic en el mapa para completar las coordenadas del sitio.', '地图展示站点位置，点击“编辑”按钮后可修改位置。': 'El mapa muestra la ubicación del sitio. Selecciona Editar para cambiarla.',
    '厂商/型号': 'Fabricante / modelo', '最后在线': 'Última conexión', '点击查看详情': 'Abrir detalles', '覆盖定价': 'Precio específico', '暂无充电桩，请先绑定。': 'No hay cargadores vinculados a este sitio.',
    '设置充电桩覆盖定价': 'Configurar precio específico del cargador', '桩级覆盖价优先于站点默认价（用于少数桩特殊价格）。': 'El precio del cargador reemplaza el precio predeterminado del sitio.', '覆盖电价（每kWh）': 'Precio específico (por kWh)', '例如：1.50': 'Ejemplo: 1.50', '覆盖定价已保存': 'Precio específico guardado',
    '绑定充电桩到站点': 'Vincular cargadores al sitio', '从“可绑定”列表中选择充电桩，系统将迁移到当前站点。': 'Selecciona cargadores para trasladarlos y vincularlos a este sitio.', '选择': 'Seleccionar', '当前站点': 'Sitio actual', '未分配': 'Sin asignar', '当前没有可绑定的充电桩。': 'No hay cargadores disponibles para vincular.', '已选择': 'Seleccionados:', '绑定/迁移': 'Vincular / trasladar',
    '在站点下添加充电桩': 'Agregar un cargador a este sitio', '输入充电桩硬件码进行预注册，并自动绑定到当前站点。': 'Pre-registra un cargador con su identificador de hardware y vincúlalo a este sitio.', '充电桩硬件码 *': 'Identificador de hardware *', '例如：635310462（只能字母数字）': 'Ejemplo: 635310462 (solo letras y números)', '该值必须与充电桩 WebSocket 连接参数一致。': 'Este valor debe coincidir con el identificador usado en la conexión WebSocket del cargador.', '厂商（可选）': 'Fabricante (opcional)', '型号（可选）': 'Modelo (opcional)', '枪口数量（EVSE 数）': 'Cantidad de EVSE', '连接器类型': 'Tipo de conector', '创建并绑定': 'Crear y vincular',
    'available': 'Disponible', 'charging': 'Cargando', 'faulted': 'Con fallo', 'unavailable': 'No disponible', 'Available': 'Disponible', 'Charging': 'Cargando', 'Faulted': 'Con fallo', 'Unavailable': 'No disponible', 'Offline': 'Sin conexión', '处理中...': 'Procesando...',
    '地图加载失败，请检查网络连接、项目结算账号以及 Maps JavaScript API 是否启用': 'No se pudo cargar el mapa. Verifica la red, la facturación del proyecto y que Maps JavaScript API esté habilitada.',
    '在站点详情页查看、绑定和迁移该站点的充电桩。': 'Consulta, vincula y traslada cargadores desde los detalles del sitio.',
    '对账成功': 'Conciliación completada', '支付订单详情': 'Detalles del pedido de pago', '订单 ID': 'ID del pedido', '参考号': 'Referencia', '用户邮箱': 'Correo del usuario', 'Wompi 交易 ID': 'ID de transacción de Wompi', '创建时间': 'Creado', '支付时间': 'Pagado', '过期时间': 'Vence', 'Webhook 事件记录': 'Historial de eventos Webhook', '元数据': 'Metadatos',
    'Private Key 状态': 'Estado de la Private Key', 'Private Key 和 Integrity Secret 存储在服务端环境变量中': 'Private Key e Integrity Secret se almacenan en variables de entorno del servidor', '这些敏感信息不会在界面中显示': 'Los valores sensibles nunca se muestran en la interfaz', '如需修改配置，请更新服务端环境变量并重启服务': 'Actualiza las variables de entorno y reinicia el servicio para cambiar la configuración', 'Webhook URL 在 Wompi 后台配置': 'Configura la URL del Webhook en Wompi', '当前应用内支付功能默认关闭。用户余额可在用户管理中调整；接入第三方支付后再启用服务端支付配置。': 'Los pagos dentro de la app están desactivados por defecto. Ajusta saldos en Usuarios y activa la configuración del servidor al integrar un proveedor de pagos.', 'Wompi 配置信息': 'Configuración de Wompi', 'Private Key 和 Integrity Secret 通过环境变量配置，不在界面中显示': 'Private Key e Integrity Secret se configuran mediante variables de entorno y no se muestran.',
    '所有二维码生成成功': 'Todos los códigos QR fueron generados', '二维码生成成功': 'Código QR generado', '生成二维码失败': 'No se pudo generar el código QR', '远程启动充电请求已发送': 'Solicitud de inicio remoto enviada', '远程启动充电失败': 'Falló el inicio remoto', '远程停止充电请求已发送': 'Solicitud de parada remota enviada', '远程停止充电失败': 'Falló la parada remota', '确定要重置充电桩吗？': '¿Restablecer este cargador?', '重置请求已发送': 'Solicitud de restablecimiento enviada', '重置失败': 'No se pudo restablecer', '加载失败，充电桩不存在或已被删除': 'No se pudo cargar. El cargador no existe o fue eliminado', '厂商': 'Fabricante', '型号': 'Modelo', '序列号': 'Número de serie', '固件版本': 'Versión de firmware', '位置': 'Ubicación', '定价': 'Precio',
    '账户已被禁用，请联系管理员': 'Esta cuenta está deshabilitada. Contacta a un administrador.', '服务器内部错误，请联系技术支持': 'Error del servidor. Contacta al soporte técnico.',
    '生成所有二维码': 'Generar todos los códigos QR', '每个连接器对应一个二维码，用户扫码后可启动充电': 'Cada conector tiene un código QR que el usuario puede escanear para iniciar la carga', '生成中': 'Generando', '下载': 'Descargar', '二维码未生成': 'Código QR no generado',
    '沙盒环境': 'Entorno de pruebas', '生产环境': 'Producción', '测试': 'Prueba', '生产': 'Producción',
    '创建租户后可选自动创建一个“租户管理员账号”，用于该租户登录运营后台。': 'Puedes crear una cuenta administradora del inquilino para acceder al portal de operaciones.',
    '对账': 'Conciliar', '订单信息': 'Información del pedido', '已处理': 'Procesado', '未处理': 'Sin procesar', '处理时间:': 'Procesado:',
  },
} as const;

function translateDynamicText(text: string, locale: Locale): string {
  if (locale === 'zh-CN') return text;
  const scope = (value: string) => value.replace('（租户汇总）', locale === 'en' ? ' (tenant summary)' : ' (resumen del inquilino)');
  const templates = locale === 'en' ? {
    totalUsers: (total: string, active: string) => `Total users ${total} | Active today ${active}`,
    alerts: (critical: string, warning: string, info: string) => `Critical ${critical} | Warning ${warning} | Info ${info}`,
    chargers: (online: string, offline: string) => `Online ${online} | Offline ${offline}`,
    chargerHealth: (faulted: string, charging: string, available: string) => `Faulted ${faulted} | Charging ${charging} | Available ${available}`,
    chargingStatus: (charging: string, available: string, faulted: string) => `Charging ${charging} | Available ${available} | Faulted ${faulted}`,
    daysOrders: (days: string) => `Orders in the last ${days} days`,
    daysRevenue: (days: string) => `Revenue in the last ${days} days`,
    siteView: (name: string) => `Site view: ${name}`,
    siteCount: (count: string) => `${count} sites`,
    siteOverview: (days: string) => `Site operations overview (last ${days} days)`,
    energyTrend: (days: string, scope: string) => `Energy over the last ${days} days (kWh)${scope}`,
    revenueTrend: (days: string, scope: string) => `Revenue over the last ${days} days (¥)${scope}`,
    ordersTrend: (days: string, scope: string) => `Orders over the last ${days} days${scope}`,
    chargerOffline: (id: string) => `Charger ${id} offline`,
    chargerHeartbeatMissing: (seconds: string) => `Charger has not sent a heartbeat for ${seconds} seconds`,
  } : {
    totalUsers: (total: string, active: string) => `Usuarios totales ${total} | Activos hoy ${active}`,
    alerts: (critical: string, warning: string, info: string) => `Críticas ${critical} | Advertencias ${warning} | Información ${info}`,
    chargers: (online: string, offline: string) => `En línea ${online} | Fuera de línea ${offline}`,
    chargerHealth: (faulted: string, charging: string, available: string) => `Fallos ${faulted} | Cargando ${charging} | Disponibles ${available}`,
    chargingStatus: (charging: string, available: string, faulted: string) => `Cargando ${charging} | Disponibles ${available} | Fallos ${faulted}`,
    daysOrders: (days: string) => `Pedidos de los últimos ${days} días`,
    daysRevenue: (days: string) => `Ingresos de los últimos ${days} días`,
    siteView: (name: string) => `Vista del sitio: ${name}`,
    siteCount: (count: string) => `${count} sitios`,
    siteOverview: (days: string) => `Resumen de operaciones del sitio (últimos ${days} días)`,
    energyTrend: (days: string, scope: string) => `Energía de los últimos ${days} días (kWh)${scope}`,
    revenueTrend: (days: string, scope: string) => `Ingresos de los últimos ${days} días (¥)${scope}`,
    ordersTrend: (days: string, scope: string) => `Pedidos de los últimos ${days} días${scope}`,
    chargerOffline: (id: string) => `Cargador ${id} fuera de línea`,
    chargerHeartbeatMissing: (seconds: string) => `El cargador no ha enviado un latido durante ${seconds} segundos`,
  };

  const fixedAlertLabels: Record<string, { en: string; es: string }> = {
    critical: { en: 'Critical', es: 'Crítica' },
    warning: { en: 'Warning', es: 'Advertencia' },
    info: { en: 'Info', es: 'Información' },
    pending: { en: 'Pending', es: 'Pendiente' },
    acknowledged: { en: 'Acknowledged', es: 'Confirmada' },
    resolved: { en: 'Resolved', es: 'Resuelta' },
    enabled: { en: 'Enabled', es: 'Activada' },
    disabled: { en: 'Disabled', es: 'Desactivada' },
  };
  const fixedAlertLabel = fixedAlertLabels[text];
  if (fixedAlertLabel) return fixedAlertLabel[locale];

  const chargerOfflineMatch = text.match(/^充电桩 (.+) 离线$/);
  if (chargerOfflineMatch) return templates.chargerOffline(chargerOfflineMatch[1]);
  const heartbeatMissingMatch = text.match(/^充电桩超过 (\d+) 秒未发送心跳$/);
  if (heartbeatMissingMatch) return templates.chargerHeartbeatMissing(heartbeatMissingMatch[1]);

  let match = text.match(/^总用户 (\d+) \| 今日活跃 (\d+)$/);
  if (match) return templates.totalUsers(match[1], match[2]);
  match = text.match(/^严重 (\d+) \| 警告 (\d+) \| 信息 (\d+)$/);
  if (match) return templates.alerts(match[1], match[2], match[3]);
  match = text.match(/^在线 (\d+) \| 离线 (\d+)$/);
  if (match) return templates.chargers(match[1], match[2]);
  match = text.match(/^故障 (\d+) \| 充电中 (\d+) \| 可用 (\d+)$/);
  if (match) return templates.chargerHealth(match[1], match[2], match[3]);
  match = text.match(/^充电中 (\d+) \| 可用 (\d+) \| 故障 (\d+)$/);
  if (match) return templates.chargingStatus(match[1], match[2], match[3]);
  match = text.match(/^近(\d+)天订单$/);
  if (match) return templates.daysOrders(match[1]);
  match = text.match(/^近(\d+)天收入$/);
  if (match) return templates.daysRevenue(match[1]);
  match = text.match(/^站点视角：(.+)$/);
  if (match) return templates.siteView(match[1]);
  match = text.match(/^共 (\d+) 个站点$/);
  if (match) return templates.siteCount(match[1]);
  match = text.match(/^站点运营概览（近 (\d+) 天）$/);
  if (match) return templates.siteOverview(match[1]);
  match = text.match(/^过去 (\d+) 天充电量（kWh）(.*)$/);
  if (match) return templates.energyTrend(match[1], scope(match[2]));
  match = text.match(/^过去 (\d+) 天收入（¥）(.*)$/);
  if (match) return templates.revenueTrend(match[1], scope(match[2]));
  match = text.match(/^过去 (\d+) 天订单数量(.*)$/);
  if (match) return templates.ordersTrend(match[1], scope(match[2]));
  match = text.match(/^过去 (\d+) 天收入趋势$/);
  if (match) return templates.revenueTrend(match[1], '');
  match = text.match(/^过去 (\d+) 天充电量趋势$/);
  if (match) return templates.energyTrend(match[1], '');
  match = text.match(/^过去 (\d+) 天订单趋势$/);
  if (match) return templates.ordersTrend(match[1], '');
  match = text.match(/^App 用户 \((\d+)\)$/);
  if (match) return locale === 'en' ? `App Users (${match[1]})` : `Usuarios App (${match[1]})`;
  match = text.match(/^管理员用户 \((\d+)\)$/);
  if (match) return locale === 'en' ? `Administrator users (${match[1]})` : `Usuarios administradores (${match[1]})`;
  match = text.match(/^进行中 \((\d+)\)$/);
  if (match) return locale === 'en' ? `In progress (${match[1]})` : `En curso (${match[1]})`;
  return text;
}

export type MessageKey = keyof typeof messages['zh-CN'];

export function translateMessage(locale: Locale, key: MessageKey | string): string {
  return messages[locale][key as MessageKey]
    || pageText[locale as 'en' | 'es']?.[key as never]
    || legacyText[locale as 'en' | 'es']?.[key as never]
    || moreLegacyText[locale as 'en' | 'es']?.[key as never]
    || translateDynamicText(key, locale);
}

interface I18nContextValue {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: (key: MessageKey | string) => string;
}

const defaultI18n: I18nContextValue = {
  locale: 'zh-CN',
  setLocale: () => undefined,
  t: (key) => messages['zh-CN'][key as MessageKey] || key,
};

const I18nContext = createContext<I18nContextValue>(defaultI18n);

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [locale, setLocale] = useState<Locale>('zh-CN');

  const changeLocale = useCallback((nextLocale: Locale) => {
    if (nextLocale === locale) return;

    // 旧页面仍有历史 JSX 文案，切换时整页刷新可以保证布局、路由边界和动态文本
    // 在同一个语言上下文中重新渲染。
    window.localStorage.setItem('admin_locale', nextLocale);
    document.documentElement.lang = nextLocale;
    setLocale(nextLocale);
    window.location.reload();
  }, [locale]);

  useEffect(() => {
    const saved = window.localStorage.getItem('admin_locale') as Locale | null;
    const browser = window.navigator.language.toLowerCase();
    // Locale is persisted outside React; this one-time synchronization intentionally updates provider state.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLocale(saved || (browser.startsWith('es') ? 'es' : browser.startsWith('en') ? 'en' : 'zh-CN'));
  }, []);

  useEffect(() => {
    window.localStorage.setItem('admin_locale', locale);
    document.documentElement.lang = locale;
  }, [locale]);

  const value = useMemo<I18nContextValue>(() => ({
    locale,
    setLocale: changeLocale,
    t: (key) => translateMessage(locale, key),
  }), [changeLocale, locale]);

  // Next 页面边界不会把布局组件的 React 子树暴露给 Provider 递归处理。
  // 因此对最终展示文本做一次受控翻译，并监听 SWR/路由产生的新节点。
  useEffect(() => {
    const translateDom = () => {
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
      let node: Node | null;
      while ((node = walker.nextNode())) {
        const parent = node.parentElement;
        if (!parent || ['SCRIPT', 'STYLE', 'NOSCRIPT'].includes(parent.tagName)) continue;
        const source = node.nodeValue || '';
        const trimmed = source.trim();
        if (!trimmed) continue;
        const translated = value.t(trimmed);
        if (translated !== trimmed) {
          node.nodeValue = source.replace(trimmed, translated);
        }
      }

      document.querySelectorAll<HTMLElement>('[placeholder], [title], [aria-label]').forEach((element) => {
        for (const attribute of ['placeholder', 'title', 'aria-label']) {
          const source = element.getAttribute(attribute);
          if (source) element.setAttribute(attribute, value.t(source));
        }
      });
    };

    translateDom();
    const observer = new MutationObserver(translateDom);
    observer.observe(document.body, { childList: true, subtree: true, characterData: true });
    return () => observer.disconnect();
  }, [value]);

  const localize = (node: ReactNode): ReactNode => {
    if (typeof node === 'string') return value.t(node);
    if (!isValidElement(node)) return node;
    const props = node.props as Record<string, unknown>;
    const nextProps: Record<string, unknown> = { ...props };
    for (const prop of ['title', 'placeholder', 'aria-label', 'description']) {
      if (typeof props[prop] === 'string') nextProps[prop] = value.t(props[prop]);
    }
    nextProps.children = Children.map(props.children as ReactNode, localize);
    return cloneElement(node, nextProps);
  };

  return <I18nContext.Provider value={value}>{Children.map(children, localize)}</I18nContext.Provider>;
}

export function useI18n() {
  return useContext(I18nContext);
}
