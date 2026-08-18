'use client';

import { useParams } from 'next/navigation';
import { PayMp002ResourceShell } from '@/components/payMp002/PayMp002ResourceShell';
import { PayMp002ReconciliationShell } from '@/components/payMp002/PayMp002ReconciliationShell';
import { PayMp002ChargebackShell } from '@/components/payMp002/PayMp002ChargebackShell';
import { PayMp002RailShell } from '@/components/payMp002/PayMp002RailShell';
import type { PayMp002Resource } from '@/lib/payMp002Foundation';

const RESOURCES: readonly PayMp002Resource[] = ['refunds', 'chargebacks', 'reconciliation', 'support', 'rails', 'audit'];

export default function PaymentsOperationsResourcePage() {
  const params = useParams<{ resource: string }>();
  const resource = params?.resource as PayMp002Resource;
  if (!RESOURCES.includes(resource)) return null;
  if (resource === 'reconciliation') return <PayMp002ReconciliationShell />;
  if (resource === 'chargebacks') return <PayMp002ChargebackShell />;
  if (resource === 'rails') return <PayMp002RailShell />;
  return <PayMp002ResourceShell resource={resource} />;
}
