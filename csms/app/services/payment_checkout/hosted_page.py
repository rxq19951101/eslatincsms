"""Render the Mercado Pago hosted checkout without exposing raw card data."""

from __future__ import annotations

import html
import json

from app.services.payment_checkout.service import HostedCheckoutPage


_MERCADO_PAGO_SDK = "https://sdk.mercadopago.com/js/v2"
_SUPPORTED_PAYMENT_TYPES = ("credit_card", "debit_card", "prepaid_card")
_PAYMENT_TYPE_LABELS = {
    "credit_card": "Tarjeta de crédito",
    "debit_card": "Tarjeta débito",
    "prepaid_card": "Tarjeta prepago",
}
_PURPOSE_COPY = {
    "save_card": (
        "Agregar una tarjeta",
        "La tarjeta quedará disponible para tus próximas cargas.",
        "Guardar tarjeta",
    ),
    "charging_direct": (
        "Configura tu método de pago",
        "La tarjeta se cobrará al finalizar la carga por el importe calculado, con un mínimo de 1.011 COP.",
        "Validar tarjeta y continuar",
    ),
    "wallet_top_up": (
        "Recargar tu billetera",
        "Revisa los datos antes de confirmar la recarga.",
        "Pagar recarga",
    ),
    "unpaid_charge": (
        "Pagar saldo pendiente",
        "Revisa los datos antes de confirmar el pago.",
        "Pagar saldo pendiente",
    ),
}


def _javascript_json(value: object) -> str:
    """Serialize a value safely for a nonce-protected inline script."""

    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _escaped(value: object) -> str:
    return html.escape(str(value), quote=True)


def render_hosted_checkout_state_page(
    *,
    title: str,
    message: str,
    return_url: str | None,
) -> str:
    """Render an inert Spanish state page without Mercado Pago fields or tokens."""

    action = ""
    if return_url:
        action = (
            '<a class="primary-action" href="'
            + _escaped(return_url)
            + '">Volver a EsLatin</a>'
        )
    return (
        """<!doctype html>
<html lang="es-CO">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>EsLatin | Pago seguro</title>
    <style>
      :root { color-scheme: light; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
      * { box-sizing: border-box; }
      body { margin: 0; min-height: 100vh; background: linear-gradient(160deg, #f4f8ff 0%, #eef6f6 100%); color: #102a43; }
      main { min-height: 100vh; display: grid; place-items: center; padding: 1.25rem; }
      .state-card { width: min(100%, 30rem); border: 1px solid #d6e3ee; border-radius: 1.25rem; background: #fff; padding: 2rem; box-shadow: 0 1.25rem 3rem rgba(16, 42, 67, .09); text-align: center; }
      .brand { margin: 0 0 1.5rem; color: #087f8c; font-size: 1rem; font-weight: 800; letter-spacing: .04em; }
      .state-icon { width: 3.5rem; height: 3.5rem; margin: 0 auto 1.1rem; border-radius: 999px; display: grid; place-items: center; background: #e9f7f7; color: #087f8c; font-size: 1.5rem; font-weight: 800; }
      h1 { margin: 0; font-size: clamp(1.45rem, 5vw, 1.8rem); line-height: 1.2; }
      p { margin: .85rem 0 0; color: #52667a; line-height: 1.55; }
      .primary-action { display: flex; min-height: 3.15rem; margin-top: 1.5rem; align-items: center; justify-content: center; border-radius: .8rem; background: #087f8c; color: #fff; font-weight: 750; text-decoration: none; }
    </style>
  </head>
  <body>
    <main>
      <section class="state-card" aria-labelledby="state-title">
        <p class="brand">ESLATIN</p>
        <div class="state-icon" aria-hidden="true">!</div>
        <h1 id="state-title">__TITLE__</h1>
        <p>__MESSAGE__</p>
        __ACTION__
      </section>
    </main>
  </body>
</html>"""
        .replace("__TITLE__", _escaped(title))
        .replace("__MESSAGE__", _escaped(message))
        .replace("__ACTION__", action)
    )


def _new_card_markup() -> str:
    return """
          <div class="field-group">
            <span class="field-label">Número de tarjeta</span>
            <div id="card-number" class="secure-field" aria-label="Número de tarjeta"></div>
          </div>
          <section id="card-capability" class="capability" aria-live="polite" hidden>
            <div>
              <span class="capability-label">Tarjeta detectada</span>
              <strong id="card-brand"></strong>
            </div>
            <div class="capability-meta">
              <span id="card-payment-type"></span>
              <span aria-hidden="true">·</span>
              <span id="card-issuer"></span>
            </div>
          </section>
          <p id="card-capability-status" class="field-status" role="status" aria-live="polite">Ingresa el número para identificar la tarjeta.</p>
          <div class="field-row">
            <div class="field-group">
              <span class="field-label">Vencimiento</span>
              <div id="expiration-date" class="secure-field" aria-label="Fecha de vencimiento"></div>
            </div>
            <div class="field-group">
              <span class="field-label">Código de seguridad</span>
              <div id="security-code" class="secure-field" aria-label="Código de seguridad"></div>
            </div>
          </div>
          <label for="cardholder-name">Nombre del titular</label>
          <input id="cardholder-name" autocomplete="cc-name" maxlength="120" required />
          <div class="field-row document-row">
            <div class="field-group">
              <label for="identification-type">Tipo de documento</label>
              <select id="identification-type" required disabled>
                <option value="" selected>Consultando tipos disponibles…</option>
              </select>
            </div>
            <div class="field-group">
              <label for="identification-number">Número de documento</label>
              <input id="identification-number" autocomplete="off" inputmode="text" maxlength="32" required disabled />
            </div>
          </div>
          <p id="identification-status" class="field-status" role="status" aria-live="polite">Consultando los tipos de documento disponibles.</p>
          <p class="privacy-note">Mercado Pago solicita el documento para procesar la tarjeta. EsLatin no almacena este dato.</p>
    """


def _new_card_script() -> str:
    supported_types = _javascript_json(list(_SUPPORTED_PAYMENT_TYPES))
    type_labels = _javascript_json(_PAYMENT_TYPE_LABELS)
    return """
      const supportedPaymentTypes = new Set(__SUPPORTED_TYPES__);
      const paymentTypeLabels = __TYPE_LABELS__;
      const providerIdPattern = /^[A-Za-z0-9_-]{1,128}$/;
      const cardNumber = mp.fields.create("cardNumber", { placeholder: "Número de tarjeta" });
      const expirationDate = mp.fields.create("expirationDate", { placeholder: "MM/AA" });
      const securityCode = mp.fields.create("securityCode", { placeholder: "CVV" });
      cardNumber.mount("card-number");
      expirationDate.mount("expiration-date");
      securityCode.mount("security-code");

      const cardCapability = document.getElementById("card-capability");
      const cardCapabilityStatus = document.getElementById("card-capability-status");
      const cardBrand = document.getElementById("card-brand");
      const cardPaymentType = document.getElementById("card-payment-type");
      const cardIssuer = document.getElementById("card-issuer");
      const cardholderName = document.getElementById("cardholder-name");
      const identificationType = document.getElementById("identification-type");
      const identificationNumber = document.getElementById("identification-number");
      const identificationStatus = document.getElementById("identification-status");
      let providerPaymentMethodId = null;
      let providerPaymentTypeId = null;
      let providerIssuerId = null;
      let identificationTypesReady = false;
      let identificationTypeCapabilities = new Map();
      let cardCapabilityReady = false;
      let binRequestSequence = 0;

      function refreshSubmitState() {
        const identityReady = identificationTypesReady &&
          identificationType.value.trim() !== "" &&
          identificationNumber.value.trim() !== "" &&
          cardholderName.value.trim() !== "";
        submitButton.disabled = isSubmitting || !cardCapabilityReady || !identityReady;
      }

      function resetCardCapability(statusText) {
        providerPaymentMethodId = null;
        providerPaymentTypeId = null;
        providerIssuerId = null;
        cardCapabilityReady = false;
        cardCapability.hidden = true;
        cardBrand.textContent = "";
        cardPaymentType.textContent = "";
        cardIssuer.textContent = "";
        cardCapabilityStatus.textContent = statusText || "Ingresa el número para identificar la tarjeta.";
        cardCapabilityStatus.dataset.tone = "neutral";
        refreshSubmitState();
      }

      function providerItems(response) {
        if (Array.isArray(response)) return response;
        if (response && Array.isArray(response.results)) return response.results;
        return [];
      }

      function normalizePaymentMethod(response) {
        const rawCandidates = providerItems(response);
        if (!rawCandidates.length) throw new Error("card_capability_invalid");
        const candidates = rawCandidates.map((candidate) => {
          if (!candidate || typeof candidate.id !== "string" ||
              !providerIdPattern.test(candidate.id) ||
              !supportedPaymentTypes.has(candidate.payment_type_id)) {
            throw new Error("card_capability_invalid");
          }
          const issuerId = candidate.issuer && candidate.issuer.id != null
            ? String(candidate.issuer.id)
            : null;
          if (issuerId !== null && !providerIdPattern.test(issuerId)) {
            throw new Error("card_capability_invalid");
          }
          return {
            id: String(candidate.id),
            paymentType: String(candidate.payment_type_id),
            issuerId,
            brandName: typeof candidate.name === "string" && candidate.name.trim()
              ? candidate.name.trim()
              : String(candidate.id).toUpperCase(),
            issuerName: candidate.issuer && typeof candidate.issuer.name === "string" && candidate.issuer.name.trim()
              ? candidate.issuer.name.trim()
              : "Emisor no informado",
          };
        });
        const unique = new Map(candidates.map((candidate) => [
          [candidate.id, candidate.paymentType, candidate.issuerId || ""].join("|"),
          candidate,
        ]));
        if (unique.size !== 1) throw new Error("card_capability_invalid");
        return Array.from(unique.values())[0];
      }

      async function loadIdentificationTypes() {
        identificationTypesReady = false;
        identificationTypeCapabilities = new Map();
        identificationType.disabled = true;
        identificationNumber.disabled = true;
        refreshSubmitState();
        try {
          const response = await mp.getIdentificationTypes();
          const rawItems = providerItems(response);
          const items = rawItems.map((item) => {
            if (!item || typeof item.id !== "string" || !item.id.trim() ||
                typeof item.name !== "string" || !item.name.trim()) return null;
            const minimum = Number(item.min_length ?? item.minLength);
            const maximum = Number(item.max_length ?? item.maxLength);
            const dataType = typeof item.type === "string" ? item.type.toLowerCase() : "";
            if (!Number.isInteger(minimum) || !Number.isInteger(maximum) ||
                minimum < 1 || maximum < minimum || maximum > 64 ||
                !["number", "text", "string"].includes(dataType)) return null;
            return {
              id: item.id.trim(),
              name: item.name.trim(),
              minimum,
              maximum,
              dataType,
            };
          }).filter(Boolean);
          if (!rawItems.length || items.length !== rawItems.length) {
            throw new Error("identification_types_unavailable");
          }
          identificationType.replaceChildren();
          const placeholder = document.createElement("option");
          placeholder.value = "";
          placeholder.textContent = "Selecciona un tipo";
          placeholder.disabled = true;
          placeholder.selected = true;
          identificationType.appendChild(placeholder);
          items.forEach((item) => {
            const option = document.createElement("option");
            option.value = item.id;
            option.textContent = item.name;
            identificationType.appendChild(option);
            identificationTypeCapabilities.set(item.id, item);
          });
          identificationTypesReady = true;
          identificationType.disabled = false;
          identificationNumber.disabled = true;
          identificationStatus.textContent = "Selecciona el documento solicitado por Mercado Pago.";
          identificationStatus.dataset.tone = "neutral";
        } catch (error) {
          identificationType.replaceChildren();
          const unavailable = document.createElement("option");
          unavailable.value = "";
          unavailable.textContent = "No disponible";
          identificationType.appendChild(unavailable);
          identificationStatus.textContent = "No pudimos consultar los tipos de documento. Inténtalo de nuevo más tarde.";
          identificationStatus.dataset.tone = "error";
        }
        refreshSubmitState();
      }

      async function identifyCard(bin) {
        const requestSequence = ++binRequestSequence;
        resetCardCapability(bin ? "Identificando la tarjeta…" : undefined);
        if (!bin || String(bin).length < 6) return;
        try {
          const response = await mp.getPaymentMethods({ bin: String(bin) });
          if (requestSequence !== binRequestSequence) return;
          const paymentMethod = normalizePaymentMethod(response);
          providerPaymentMethodId = paymentMethod.id;
          providerPaymentTypeId = paymentMethod.paymentType;
          providerIssuerId = paymentMethod.issuerId;
          cardBrand.textContent = paymentMethod.brandName;
          cardPaymentType.textContent = paymentTypeLabels[paymentMethod.paymentType];
          cardIssuer.textContent = paymentMethod.issuerName;
          cardCapability.hidden = false;
          cardCapabilityReady = true;
          cardCapabilityStatus.textContent = "Tarjeta identificada correctamente.";
          cardCapabilityStatus.dataset.tone = "success";
        } catch (error) {
          if (requestSequence !== binRequestSequence) return;
          resetCardCapability("No pudimos identificar una tarjeta compatible. Revisa el número o usa otra tarjeta.");
          cardCapabilityStatus.dataset.tone = "error";
        }
        refreshSubmitState();
      }

      cardNumber.on("binChange", (event) => {
        const bin = event && typeof event.bin === "string" ? event.bin : "";
        void identifyCard(bin);
      });
      cardholderName.addEventListener("input", refreshSubmitState);
      identificationType.addEventListener("change", () => {
        const capability = identificationTypeCapabilities.get(identificationType.value);
        identificationNumber.value = "";
        if (!capability) {
          identificationNumber.disabled = true;
          refreshSubmitState();
          return;
        }
        identificationNumber.minLength = capability.minimum;
        identificationNumber.maxLength = capability.maximum;
        identificationNumber.inputMode = capability.dataType === "number" ? "numeric" : "text";
        identificationNumber.pattern = capability.dataType === "number" ? "[0-9]*" : "";
        identificationNumber.disabled = false;
        refreshSubmitState();
      });
      identificationNumber.addEventListener("input", refreshSubmitState);

      createCardData = async function createNewCardData() {
        if (!cardCapabilityReady || !identificationTypesReady) {
          throw new Error("checkout_capability_not_ready");
        }
        const result = await mp.fields.createCardToken({
          cardholderName: cardholderName.value.trim(),
          identificationType: identificationType.value,
          identificationNumber: identificationNumber.value.trim(),
        });
        return {
          cardToken: result.id || result.token,
          paymentMethodId: providerPaymentMethodId,
          paymentTypeId: providerPaymentTypeId,
          issuerId: providerIssuerId,
          installments: 1,
        };
      };
      void loadIdentificationTypes();
    """.replace("__SUPPORTED_TYPES__", supported_types).replace(
        "__TYPE_LABELS__", type_labels
    )


def _saved_card_markup(page: HostedCheckoutPage) -> str:
    brand = (page.saved_card_brand or "Tarjeta").upper()
    payment_type = _PAYMENT_TYPE_LABELS.get(
        page.saved_card_payment_type or "", "Tarjeta guardada"
    )
    last_four = page.saved_card_last_four or "••••"
    return """
          <section class="saved-card" aria-label="Tarjeta seleccionada">
            <div class="card-mark" aria-hidden="true">▰</div>
            <div>
              <strong>__BRAND__ ···· __LAST_FOUR__</strong>
              <span>__PAYMENT_TYPE__</span>
            </div>
          </section>
          <div class="field-group">
            <span class="field-label">Código de seguridad</span>
            <div id="security-code" class="secure-field" aria-label="Código de seguridad"></div>
          </div>
          <p class="privacy-note">Mercado Pago solicita el código de seguridad para autorizar este uso de la tarjeta.</p>
    """.replace("__BRAND__", _escaped(brand)).replace(
        "__LAST_FOUR__", _escaped(last_four)
    ).replace("__PAYMENT_TYPE__", _escaped(payment_type))


def _saved_card_script() -> str:
    return """
      const securityCode = mp.fields.create("securityCode", { placeholder: "CVV" });
      securityCode.mount("security-code");
      createCardData = async function createSavedCardData() {
        const result = await mp.fields.createCardToken({
          cardId: checkout.savedProviderCardId,
        });
        return {
          cardToken: result.id || result.token,
          paymentMethodId: null,
          paymentTypeId: null,
          issuerId: null,
          installments: 1,
        };
      };
      submitButton.disabled = false;
    """


def render_hosted_checkout_page(
    page: HostedCheckoutPage,
    *,
    signed_token: str,
    script_nonce: str,
) -> str:
    """Return a compact, no-store checkout document for the frozen purpose."""

    title, description, cta = _PURPOSE_COPY[page.purpose.value]
    checkout_data = _javascript_json(
        {
            "checkoutSessionId": page.checkout_session_id,
            "publicKey": page.public_key,
            "savedProviderCardId": page.saved_provider_card_id,
            "confirmPath": f"/api/v1/app/payments/checkout/{signed_token}/confirm",
            "returnUrl": page.return_url,
        }
    )
    if page.payment_method_mode.value == "saved_card":
        fields = _saved_card_markup(page)
        card_script = _saved_card_script()
    else:
        fields = _new_card_markup()
        card_script = _new_card_script()

    amount_markup = ""
    if page.amount is not None:
        amount_markup = (
            '<section class="amount-summary"><span>Total</span><strong>'
            + _escaped(page.amount)
            + " COP</strong></section>"
        )

    document = """<!doctype html>
<html lang="es-CO">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>EsLatin | Pago seguro</title>
    <style>
      :root { color-scheme: light; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
      * { box-sizing: border-box; }
      body { margin: 0; min-height: 100vh; background: linear-gradient(160deg, #f4f8ff 0%, #eef6f6 100%); color: #102a43; }
      main { width: min(100%, 33rem); margin: 0 auto; padding: 1.25rem; }
      .checkout-card { border: 1px solid #d6e3ee; border-radius: 1.25rem; background: #fff; padding: clamp(1.2rem, 4vw, 1.8rem); box-shadow: 0 1.25rem 3rem rgba(16, 42, 67, .09); }
      .brand-row { display: flex; align-items: center; justify-content: space-between; gap: 1rem; margin-bottom: 1.4rem; }
      .brand { color: #087f8c; font-weight: 850; letter-spacing: .04em; }
      .secure-badge { display: inline-flex; align-items: center; gap: .35rem; color: #52667a; font-size: .78rem; }
      h1 { margin: 0; font-size: clamp(1.45rem, 5vw, 1.9rem); line-height: 1.2; }
      .lead { margin: .65rem 0 1.3rem; color: #52667a; line-height: 1.5; }
      .amount-summary { display: flex; align-items: center; justify-content: space-between; margin-bottom: 1.2rem; padding: .85rem 1rem; border-radius: .75rem; background: #f2f8fa; color: #29465b; }
      .amount-summary strong { color: #102a43; }
      .field-group { min-width: 0; }
      .field-label, label { display: block; margin: .95rem 0 .4rem; color: #29465b; font-size: .88rem; font-weight: 720; }
      input, select, .secure-field { width: 100%; height: 3.25rem; border: 1px solid #b9cad8; border-radius: .75rem; background: #fff; color: #102a43; font: inherit; }
      input, select { padding: 0 .9rem; }
      select:disabled, input:disabled { background: #f3f6f8; color: #74879a; }
      .secure-field { min-height: 3.25rem; padding: 0 .9rem; overflow: hidden; display: flex; align-items: center; }
      .secure-field iframe { width: 100% !important; height: 100% !important; min-height: 0 !important; }
      input:focus, select:focus, .secure-field:focus-within { outline: 3px solid rgba(8, 127, 140, .16); border-color: #087f8c; }
      .field-row { display: grid; grid-template-columns: 1fr 1fr; gap: .8rem; }
      .capability { margin-top: .7rem; padding: .8rem .9rem; border: 1px solid #b9dfdc; border-radius: .75rem; background: #f1fbfa; }
      .capability-label { display: block; color: #52667a; font-size: .75rem; }
      .capability strong { display: block; margin-top: .15rem; color: #0c6f78; }
      .capability-meta { display: flex; flex-wrap: wrap; gap: .35rem; margin-top: .25rem; color: #52667a; font-size: .82rem; }
      .field-status { min-height: 1.2rem; margin: .45rem 0 0; color: #63788b; font-size: .78rem; line-height: 1.45; }
      .field-status[data-tone="error"] { color: #b42318; }
      .field-status[data-tone="success"] { color: #087f5b; }
      .privacy-note { margin: .8rem 0 0; color: #63788b; font-size: .78rem; line-height: 1.45; }
      .saved-card { display: flex; align-items: center; gap: .8rem; margin: .35rem 0 1rem; padding: 1rem; border-radius: .85rem; background: linear-gradient(135deg, #0d4e68, #087f8c); color: #fff; }
      .saved-card strong, .saved-card span { display: block; }
      .saved-card span { margin-top: .2rem; color: #dff7f5; font-size: .82rem; }
      .card-mark { font-size: 1.5rem; }
      .message { min-height: 1.4rem; margin: 1rem 0 0; color: #b42318; font-size: .88rem; line-height: 1.45; }
      button { width: 100%; min-height: 3.2rem; margin-top: 1rem; border: 0; border-radius: .8rem; background: #087f8c; color: #fff; font: inherit; font-weight: 780; cursor: pointer; }
      button:hover:not(:disabled) { background: #066d78; }
      button:disabled { cursor: not-allowed; opacity: .52; }
      .trust { display: flex; align-items: flex-start; gap: .5rem; margin: 1rem 0 0; color: #63788b; font-size: .78rem; line-height: 1.45; }
      @media (max-width: 32rem) {
        main { padding: .75rem; }
        .checkout-card { border-radius: 1rem; }
        .field-row { grid-template-columns: 1fr; gap: 0; }
        .document-row { gap: 0; }
      }
    </style>
  </head>
  <body>
    <main>
      <section class="checkout-card" aria-labelledby="checkout-title">
        <header class="brand-row">
          <span class="brand">ESLATIN</span>
          <span class="secure-badge" aria-label="Conexión segura">● Pago seguro</span>
        </header>
        <h1 id="checkout-title">__TITLE__</h1>
        <p class="lead">__DESCRIPTION__</p>
        __AMOUNT__
        <form id="checkout-form" novalidate>
          __FIELDS__
          <p id="checkout-message" class="message" role="alert" aria-live="assertive"></p>
          <button id="submit-button" type="submit" disabled>__CTA__</button>
        </form>
        <p class="trust"><span aria-hidden="true">🔒</span><span>Los datos de la tarjeta se cifran y se envían directamente a Mercado Pago.</span></p>
      </section>
    </main>
    <script src="__SDK__" nonce="__NONCE__"></script>
    <script nonce="__NONCE__">
      "use strict";
      const checkout = __CHECKOUT_DATA__;
      const form = document.getElementById("checkout-form");
      const submitButton = document.getElementById("submit-button");
      const message = document.getElementById("checkout-message");
      const mp = new MercadoPago(checkout.publicKey, { locale: "es-CO" });
      let createCardData = null;
      let isSubmitting = false;
      __CARD_SCRIPT__

      function safeReturnUrl(status) {
        const separator = checkout.returnUrl.includes("?") ? "&" : "?";
        const query = new URLSearchParams({
          checkout_session_id: checkout.checkoutSessionId,
          status,
        });
        return checkout.returnUrl + separator + query.toString();
      }

      async function submitCheckout() {
        if (typeof createCardData !== "function" || !form.reportValidity()) return;
        isSubmitting = true;
        submitButton.disabled = true;
        submitButton.textContent = "Procesando…";
        message.textContent = "";
        try {
          const card = await createCardData();
          if (!card.cardToken) throw new Error("card_token_unavailable");
          const response = await fetch(checkout.confirmPath, {
            method: "POST",
            credentials: "same-origin",
            redirect: "manual",
            headers: { "Content-Type": "application/json", "Accept": "application/json" },
            body: JSON.stringify({
              card_token: card.cardToken,
              payment_method_id: card.paymentMethodId,
              payment_type_id: card.paymentTypeId,
              issuer_id: card.issuerId,
              installments: card.installments,
            }),
          });
          if (response.status === 303 || response.type === "opaqueredirect") {
            const redirectLocation = response.headers.get("Location");
            window.location.assign(redirectLocation || safeReturnUrl("processing"));
            return;
          }
          if (response.status === 400) {
            message.textContent = "Revisa los datos de la tarjeta e inténtalo de nuevo.";
          } else if (response.status === 404) {
            message.textContent = "La sesión de pago venció. Vuelve a la aplicación para comenzar de nuevo.";
          } else if (response.status === 409) {
            window.location.assign(safeReturnUrl("processing"));
            return;
          } else if (response.status === 503) {
            message.textContent = "El servicio de pago no está disponible temporalmente. Inténtalo de nuevo más tarde.";
          } else {
            message.textContent = "No pudimos confirmar la tarjeta. Inténtalo de nuevo.";
          }
        } catch (error) {
          message.textContent = "No pudimos validar la tarjeta. Revisa los datos e inténtalo de nuevo.";
        }
        isSubmitting = false;
        submitButton.textContent = __CTA_JSON__;
        if (typeof refreshSubmitState === "function") refreshSubmitState();
        else submitButton.disabled = false;
      }

      form.addEventListener("submit", (event) => {
        event.preventDefault();
        void submitCheckout();
      });
    </script>
  </body>
</html>"""
    return (
        document.replace("__TITLE__", _escaped(title))
        .replace("__DESCRIPTION__", _escaped(description))
        .replace("__AMOUNT__", amount_markup)
        .replace("__FIELDS__", fields)
        .replace("__CTA__", _escaped(cta))
        .replace("__SDK__", _escaped(_MERCADO_PAGO_SDK))
        .replace("__NONCE__", _escaped(script_nonce))
        .replace("__CHECKOUT_DATA__", checkout_data)
        .replace("__CARD_SCRIPT__", card_script)
        .replace("__CTA_JSON__", _javascript_json(cta))
    )
