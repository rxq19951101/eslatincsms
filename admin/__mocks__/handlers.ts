import { http, HttpResponse } from 'msw';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';

export const handlers = [
  http.post(`${API_BASE_URL}/api/v1/admin/auth/login`, async ({ request }) => {
    const body = await request.json() as { username: string; password: string };
    
    if (body.username === 'admin' && body.password === 'password') {
      return HttpResponse.json({
        access_token: 'mock-access-token',
        refresh_token: 'mock-refresh-token',
        token_type: 'bearer',
        user: {
          id: '1',
          username: 'admin',
          email: 'admin@example.com',
          full_name: 'Admin User',
          is_super_admin: false,
        },
      });
    }
    
    return HttpResponse.json(
      { detail: 'Invalid username or password' },
      { status: 401 }
    );
  }),

  http.post(`${API_BASE_URL}/api/v1/admin/auth/refresh`, () => {
    return HttpResponse.json({
      access_token: 'new-mock-access-token',
      refresh_token: 'new-mock-refresh-token',
      token_type: 'bearer',
    });
  }),

  http.get(`${API_BASE_URL}/api/v1/admin/auth/me`, () => {
    return HttpResponse.json({
      id: '1',
      username: 'admin',
      email: 'admin@example.com',
      full_name: 'Admin User',
      is_super_admin: false,
      default_tenant_id: 'tenant-1',
      tenant_list: [
        { id: 'tenant-1', name: '租户1', is_primary: true },
      ],
    });
  }),

  http.get(`${API_BASE_URL}/api/v1/dashboard/summary`, () => {
    return HttpResponse.json({
      total_charge_points: 100,
      online_charge_points: 85,
      offline_charge_points: 15,
      faulted_charge_points: 2,
      charging_charge_points: 10,
      available_charge_points: 73,
      total_sites: 5,
      active_sites: 5,
      today_orders: 25,
      today_energy_kwh: 1250.5,
      today_revenue: 3750.75,
      total_users: 150,
      active_users_today: 30,
      critical_alerts: 1,
      warning_alerts: 5,
      info_alerts: 10,
    });
  }),

  http.get(`${API_BASE_URL}/api/v1/dashboard/trends`, () => {
    const days = 7;
    return HttpResponse.json({
      energy_trend: Array.from({ length: days }, (_, i) => ({
        date: new Date(Date.now() - (days - i - 1) * 24 * 60 * 60 * 1000).toISOString().split('T')[0],
        value: Math.random() * 1000 + 500,
      })),
      revenue_trend: Array.from({ length: days }, (_, i) => ({
        date: new Date(Date.now() - (days - i - 1) * 24 * 60 * 60 * 1000).toISOString().split('T')[0],
        value: Math.random() * 5000 + 2000,
      })),
      orders_trend: Array.from({ length: days }, (_, i) => ({
        date: new Date(Date.now() - (days - i -1) * 24 * 60 * 60 * 1000).toISOString().split('T')[0],
        value: Math.floor(Math.random() * 50 + 10),
      })),
    });
  }),

  http.get(`${API_BASE_URL}/api/v1/dashboard/sites`, () => {
    return HttpResponse.json([
      {
        site_id: 'site_mock_1',
        site_name: 'Mock站点A',
        address: 'Bogotá, Colombia',
        charge_points_count: 8,
        online_charge_points_count: 6,
        faulted_charge_points: 1,
        charging_charge_points: 2,
        available_charge_points: 3,
        orders_count: 42,
        energy_kwh: 1234.56,
        revenue: 3456.78,
      },
      {
        site_id: 'site_mock_2',
        site_name: 'Mock站点B',
        address: 'Medellín, Colombia',
        charge_points_count: 4,
        online_charge_points_count: 3,
        faulted_charge_points: 0,
        charging_charge_points: 1,
        available_charge_points: 2,
        orders_count: 15,
        energy_kwh: 456.78,
        revenue: 987.65,
      },
    ]);
  }),

  http.get(`${API_BASE_URL}/api/v1/chargers`, () => {
    return HttpResponse.json([
      {
        id: 'CP001',
        vendor: 'Tesla',
        model: 'Supercharger V3',
        status: 'Available',
        last_seen: new Date().toISOString(),
        location: {
          latitude: 39.9042,
          longitude: 116.4074,
          address: '北京市朝阳区',
        },
        price_per_kwh: 1.5,
        is_configured: true,
        has_location: true,
        has_pricing: true,
      },
    ]);
  }),

  http.get(`${API_BASE_URL}/api/v1/transactions`, () => {
    return HttpResponse.json([
      {
        id: '1',
        transaction_id: 'TXN001',
        charge_point_id: 'CP001',
        id_tag: 'USER001',
        user_id: 'user-1',
        start_time: new Date(Date.now() - 3600000).toISOString(),
        end_time: new Date().toISOString(),
        energy_kwh: 25.5,
        duration_minutes: 60,
        status: 'Completed',
      },
    ]);
  }),

  http.get(`${API_BASE_URL}/api/v1/admin/alerts`, () => {
    return HttpResponse.json([
      {
        id: '1',
        type: 'Charger Offline',
        severity: 'critical',
        charge_point_id: 'CP001',
        description: '充电桩 CP001 已离线超过 30 分钟',
        status: 'pending',
        created_at: new Date().toISOString(),
      },
    ]);
  }),
];
