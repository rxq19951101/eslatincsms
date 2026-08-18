"""Provider-authoritative refunds and wallet balance protection.

The current schema has no RefundAttempt table.  Until an approved migration is
available, PaymentOrder.metadata stores only a versioned, non-sensitive refund
summary.  The provider's cumulative refund facts are queried before and after
each operation and always win over that summary.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from typing import Any, Mapping
from uuid import UUID

from sqlalchemy.orm import Session

from app.database.models import AppUser, AppWalletTransaction, Invoice, PaymentOrder
from app.domain.payment import transition_status
from app.services.payment_providers.base import (
    PaymentCapabilityCommand,
    ProviderCapabilityError,
    PaymentProviderError,
    RefundCapabilityCommand,
    RefundCapabilityFacts,
    RefundCapabilityResult,
    ProviderRefundResult,
    ProviderRefundFacts,
)
from app.services.payment_providers.merchant_context import PaymentPurpose
from app.services.payment_reconciliation import PaymentReconciliationError, PaymentReconciliationService


class RefundError(RuntimeError):
    status_code = 400


class RefundRequestInvalid(RefundError):
    pass


class RefundManualReviewRequired(RefundError):
    status_code = 409


class RefundRetryable(RefundError):
    status_code = 503


@dataclass(frozen=True)
class RefundResult:
    refund_id: str | None
    status: str
    refunded_amount: Decimal
    remaining_amount: Decimal
    manual_review: bool = False


def _money(value: Any) -> Decimal:
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError, ArithmeticError) as exc:
        raise RefundManualReviewRequired("Refund monetary state is invalid") from exc
    if not amount.is_finite() or amount < 0:
        raise RefundManualReviewRequired("Refund monetary state is invalid")
    return amount


class PaymentRefundService:
    """Serialize refunds per PaymentOrder and keep local state fail-closed."""

    def __init__(self, *, reconciliation: PaymentReconciliationService | None = None) -> None:
        self._reconciliation = reconciliation or PaymentReconciliationService()

    @staticmethod
    def _summary(order: PaymentOrder) -> dict[str, Any]:
        metadata = order.order_metadata if isinstance(order.order_metadata, Mapping) else {}
        raw = metadata.get("refund_summary")
        if not isinstance(raw, Mapping):
            return {
                "schema_version": 1,
                "provider_refunded_amount": "0.00",
                "operations": {},
            }
        operations = raw.get("operations")
        return {
            "schema_version": 1,
            "provider_refunded_amount": str(raw.get("provider_refunded_amount", "0.00")),
            "operations": dict(operations) if isinstance(operations, Mapping) else {},
        }

    @staticmethod
    def _operation_key(idempotency_key: str) -> str:
        if not isinstance(idempotency_key, str) or not idempotency_key.strip():
            raise RefundRequestInvalid("Idempotency-Key is required")
        key = idempotency_key.strip()
        if len(key) > 255:
            raise RefundRequestInvalid("Idempotency-Key is too long")
        return sha256(key.encode("utf-8")).hexdigest()

    @staticmethod
    def _provider_method(provider: Any, name: str):
        method = getattr(provider, name, None)
        if not callable(method):
            raise RefundManualReviewRequired("Refund provider capability is unavailable")
        return method

    @staticmethod
    def _save(order: PaymentOrder, summary: dict[str, Any]) -> None:
        metadata = dict(order.order_metadata or {})
        metadata["refund_summary"] = summary
        order.order_metadata = metadata

    @staticmethod
    def _tenant_id_for_refund(db: Session, order: PaymentOrder) -> UUID | None:
        """Resolve refund ownership from persisted payment facts.

        Charging refunds are owned by their Invoice; wallet refunds are owned
        by the original wallet ledger.  The metadata tenant is only the
        compatibility fallback for legacy orders without either relation.
        """
        metadata = order.order_metadata or {}
        invoice_id = metadata.get("invoice_id")
        if invoice_id:
            try:
                invoice_uuid = UUID(str(invoice_id))
            except (TypeError, ValueError, AttributeError):
                invoice_uuid = None
            if invoice_uuid is not None:
                invoice = db.query(Invoice).filter(Invoice.id == invoice_uuid).first()
                if invoice is not None:
                    return invoice.tenant_id

        ledger = (
            db.query(AppWalletTransaction)
            .filter(
                AppWalletTransaction.payment_order_id == order.id,
                AppWalletTransaction.type == "top_up",
            )
            .first()
        )
        if ledger is not None:
            return ledger.operator_tenant_id

        tenant_value = metadata.get("operator_tenant_id")
        try:
            return UUID(str(tenant_value)) if tenant_value else None
        except (TypeError, ValueError, AttributeError):
            return None

    def _manual(
        self,
        db: Session,
        order: PaymentOrder,
        *,
        operation_key: str,
        reason: str,
        amount: Decimal | None = None,
    ) -> None:
        summary = self._summary(order)
        operations = dict(summary["operations"])
        operation = dict(operations.get(operation_key) or {})
        operation.update(
            {
                "status": "manual_review",
                "reason": reason,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        if amount is not None:
            operation["requested_amount"] = format(amount, ".2f")
        operations[operation_key] = operation
        summary["operations"] = operations
        self._save(order, summary)
        db.commit()

    def _facts(self, provider: Any, payment_id: str, context) -> ProviderRefundFacts:
        try:
            capability = getattr(provider, "query_refund_facts", None)
            if not callable(capability):
                capability = getattr(provider, "query_refund_capability", None)
            if callable(capability):
                canonical: RefundCapabilityFacts = capability(
                    payment_id,
                    merchant_context=context,
                )
                facts = ProviderRefundFacts(
                    refunded_amount=canonical.refunded_amount,
                    refund_ids=canonical.refund_refs,
                )
            else:
                facts = self._provider_method(provider, "get_refund_facts")(
                    payment_id,
                    merchant_context=context,
                )
        except (PaymentProviderError, ProviderCapabilityError):
            raise
        except Exception as exc:
            raise RefundRetryable("Unable to query provider refund facts") from exc
        if not isinstance(facts, ProviderRefundFacts):
            raise RefundManualReviewRequired("Provider refund facts are invalid")
        if _money(facts.refunded_amount) < 0:
            raise RefundManualReviewRequired("Provider refund facts are invalid")
        return facts

    def refund_payment_order(
        self,
        db: Session,
        *,
        payment_order_id: UUID | str,
        amount: Decimal | None,
        idempotency_key: str,
    ) -> RefundResult:
        operation_key = self._operation_key(idempotency_key)
        order = (
            db.query(PaymentOrder)
            .filter(PaymentOrder.id == payment_order_id)
            .with_for_update()
            .first()
        )
        if order is None:
            raise RefundRequestInvalid("Payment order not found")
        if order.status not in {"approved", "refunded"}:
            raise RefundRequestInvalid("Only approved payment orders can be refunded")
        payment_ref = (order.order_metadata or {}).get("provider_reference")
        if not payment_ref:
            # Read legacy P001 provider storage only as a compatibility fallback.
            payment_ref = order.mercadopago_payment_id
        if not payment_ref:
            raise RefundManualReviewRequired("Refund provider payment is unavailable")

        summary = self._summary(order)
        existing = summary["operations"].get(operation_key)
        if isinstance(existing, Mapping) and existing.get("status") == "completed":
            return RefundResult(
                refund_id=(str(existing["refund_id"]) if existing.get("refund_id") else None),
                status="approved",
                refunded_amount=_money(summary["provider_refunded_amount"]),
                remaining_amount=max(_money(order.amount) - _money(summary["provider_refunded_amount"]), Decimal("0.00")),
            )

        try:
            refund_purpose = (
                PaymentPurpose.REFUND
                if (order.order_metadata or {}).get("operator_tenant_id")
                else PaymentPurpose.WALLET_TOP_UP
            )
            context = self._reconciliation.merchant_context_for_order(
                payment_order=order,
                purpose=refund_purpose,
            )
            provider = self._reconciliation._provider_registry.get(order.payment_provider)
        except (PaymentReconciliationError, PaymentProviderError) as exc:
            self._manual(db, order, operation_key=operation_key, reason="merchant_context_unavailable")
            raise RefundManualReviewRequired("Refund merchant context is unavailable") from exc

        try:
            before = self._facts(provider, str(payment_ref), context)
        except (PaymentProviderError, ProviderCapabilityError) as exc:
            if exc.retryable:
                raise RefundRetryable("Unable to query provider refund facts") from exc
            reason = getattr(exc, "code", None) or getattr(exc, "reason", "provider_fact_invalid")
            self._manual(db, order, operation_key=operation_key, reason=reason)
            raise RefundManualReviewRequired("Provider refund facts are unavailable") from exc
        except RefundManualReviewRequired as exc:
            self._manual(db, order, operation_key=operation_key, reason="provider_refund_capability_unavailable")
            raise

        local_total = _money(summary["provider_refunded_amount"])
        provider_total = _money(before.refunded_amount)
        if local_total != provider_total:
            self._manual(db, order, operation_key=operation_key, reason="provider_metadata_mismatch")
            raise RefundManualReviewRequired("Provider refund facts do not match local summary")

        paid_amount = _money(order.amount)
        remaining = paid_amount - provider_total
        if remaining < 0:
            self._manual(db, order, operation_key=operation_key, reason="provider_refund_exceeds_payment")
            raise RefundManualReviewRequired("Provider refunded amount exceeds payment")
        requested = remaining if amount is None else _money(amount)
        if requested <= 0 or requested > remaining:
            raise RefundRequestInvalid("Refund amount exceeds the remaining paid amount")

        user = None
        if order.type == "top_up":
            user = (
                db.query(AppUser)
                .filter(AppUser.id == order.app_user_id)
                .with_for_update()
                .first()
            )
            if user is None:
                self._manual(db, order, operation_key=operation_key, reason="wallet_user_missing", amount=requested)
                raise RefundManualReviewRequired("Wallet user is unavailable")
            if _money(user.balance) < requested:
                self._manual(db, order, operation_key=operation_key, reason="wallet_balance_insufficient", amount=requested)
                raise RefundManualReviewRequired("Wallet balance is insufficient for automatic refund")

        try:
            capability = getattr(provider, "create_refund_capability", None)
            if callable(capability):
                canonical: RefundCapabilityResult = capability(
                    RefundCapabilityCommand(
                        payment_ref=str(payment_ref),
                        amount=requested,
                        currency=order.currency,
                        merchant_account_ref=context.merchant_account_ref,
                        references={"payment_order_id": str(order.id)},
                    ),
                    idempotency_key=f"refund:{order.id}:{operation_key}",
                    merchant_context=context,
                )
                created = ProviderRefundResult(
                    refund_id=canonical.refund_ref,
                    status=canonical.status,
                    amount=canonical.amount or requested,
                )
            else:
                created = self._provider_method(provider, "create_refund")(
                    str(payment_ref),
                    requested,
                    idempotency_key=f"refund:{order.id}:{operation_key}",
                    merchant_context=context,
                )
        except (PaymentProviderError, ProviderCapabilityError) as exc:
            summary = self._summary(order)
            operations = dict(summary["operations"])
            operations[operation_key] = {
                "status": "provider_timeout" if exc.retryable else "provider_error",
                "reason": getattr(exc, "code", None) or getattr(exc, "reason", "provider_error"),
                "requested_amount": format(requested, ".2f"),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            summary["operations"] = operations
            self._save(order, summary)
            db.commit()
            if exc.retryable:
                raise RefundRetryable("Refund provider timed out") from exc
            raise RefundManualReviewRequired("Refund provider rejected the request") from exc
        except Exception as exc:
            summary = self._summary(order)
            operations = dict(summary["operations"])
            operations[operation_key] = {
                "status": "provider_timeout",
                "reason": "provider_exception",
                "requested_amount": format(requested, ".2f"),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            summary["operations"] = operations
            self._save(order, summary)
            db.commit()
            raise RefundRetryable("Refund provider timed out") from exc

        try:
            after = self._facts(provider, str(payment_ref), context)
        except (PaymentProviderError, ProviderCapabilityError) as exc:
            summary = self._summary(order)
            operations = dict(summary["operations"])
            operations[operation_key] = {
                "status": "provider_timeout" if exc.retryable else "manual_review",
                "reason": getattr(exc, "code", None) or getattr(exc, "reason", "provider_error"),
                "requested_amount": format(requested, ".2f"),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            summary["operations"] = operations
            self._save(order, summary)
            db.commit()
            if exc.retryable:
                raise RefundRetryable("Unable to confirm provider refund") from exc
            raise RefundManualReviewRequired("Unable to confirm provider refund") from exc
        except RefundManualReviewRequired as exc:
            self._manual(db, order, operation_key=operation_key, reason="provider_refund_facts_invalid", amount=requested)
            raise
        after_total = _money(after.refunded_amount)
        if after_total != provider_total + requested or after_total > paid_amount:
            self._manual(db, order, operation_key=operation_key, reason="provider_refund_amount_mismatch", amount=requested)
            raise RefundManualReviewRequired("Provider refund amount does not match the request")

        if order.type == "top_up" and user is not None:
            cumulative = after_total
            current_balance = _money(user.balance)
            if current_balance < requested:
                self._manual(db, order, operation_key=operation_key, reason="wallet_balance_changed", amount=requested)
                raise RefundManualReviewRequired("Wallet balance changed before refund completion")
            tenant_value = (order.order_metadata or {}).get("operator_tenant_id")
            if not tenant_value:
                original_ledger = db.query(AppWalletTransaction).filter(
                    AppWalletTransaction.payment_order_id == order.id,
                    AppWalletTransaction.type == "top_up",
                ).with_for_update().first()
                tenant_value = (
                    str(original_ledger.operator_tenant_id)
                    if original_ledger is not None
                    else None
                )
            try:
                tenant_id = UUID(str(tenant_value))
            except (TypeError, ValueError, AttributeError) as exc:
                self._manual(db, order, operation_key=operation_key, reason="refund_tenant_missing", amount=requested)
                raise RefundManualReviewRequired("Refund tenant context is unavailable") from exc
            user.balance = current_balance - requested
            ledger = db.query(AppWalletTransaction).filter(
                AppWalletTransaction.payment_order_id == order.id,
                AppWalletTransaction.type == "charge",
            ).with_for_update().first()
            if ledger is None:
                db.add(AppWalletTransaction(
                    transaction_number=f"payment_refund_{order.id}",
                    app_user_id=user.id,
                    payment_order_id=order.id,
                    operator_tenant_id=tenant_id,
                    type="charge",
                    amount=-cumulative,
                    description="Wallet top-up refund",
                    idempotency_key=f"refund:{order.id}",
                ))
            else:
                ledger.amount = -cumulative

        summary["provider_refunded_amount"] = format(after_total, ".2f")
        operations = dict(summary["operations"])
        operations[operation_key] = {
            "status": "completed",
            "requested_amount": format(requested, ".2f"),
            "provider_amount": format(after_total, ".2f"),
            "refund_id": str(created.refund_id) if created.refund_id else None,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        summary["operations"] = operations
        self._save(order, summary)
        if after_total == paid_amount:
            order.status = transition_status(order.status, "refunded")
            invoice_id = (order.order_metadata or {}).get("invoice_id")
            if invoice_id:
                try:
                    invoice_uuid = UUID(str(invoice_id))
                except (TypeError, ValueError, AttributeError):
                    invoice_uuid = None
                invoice = (
                    db.query(Invoice)
                    .filter(Invoice.id == invoice_uuid)
                    .with_for_update()
                    .first()
                    if invoice_uuid is not None
                    else None
                )
                if invoice is not None and invoice.status == "paid":
                    invoice.status = "refunded"
        from app.services.financial_eligibility import enqueue_financial_eligibility_recheck

        enqueue_financial_eligibility_recheck(
            db,
            app_user_id=order.app_user_id,
            tenant_id=self._tenant_id_for_refund(db, order),
            source_type="payment_refund",
            source_id=order.id,
            source_version=f"{operation_key}:{format(after_total, '.2f')}",
            reason_code="refund_fact_changed",
        )
        db.commit()
        return RefundResult(
            refund_id=str(created.refund_id) if created.refund_id else None,
            status=created.status,
            refunded_amount=after_total,
            remaining_amount=paid_amount - after_total,
        )
