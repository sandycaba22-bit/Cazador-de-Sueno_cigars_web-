/**
 * Políticas comerciales — venta final sin devoluciones y descargo aduanero.
 */

const SALES_POLICY = {
  id: 'final_sale_no_refunds',
  title: 'Política de venta final',
  shortLabel: 'Acepto que esta es una venta final sin devoluciones ni reembolsos.',
  summary:
    'Todos los pedidos de Cazador Sueño son venta final. Una vez confirmado y pagado el pedido, no se admiten devoluciones, cambios ni reembolsos bajo ninguna circunstancia.',
  checkoutText:
    'Entiendo y acepto que, una vez realizado y pagado mi pedido, no se admiten devoluciones ni reembolsos bajo ninguna circunstancia. Esta es una venta final.',
  legalNotice:
    'Al confirmar su compra, usted renuncia expresamente a cualquier derecho de desistimiento, devolución o contracargo una vez procesado el pago, salvo lo que exija de forma imperativa la legislación local aplicable al consumidor.',
  filterBlockedReason:
    'No es posible completar la compra sin aceptar la política de venta final (sin devoluciones ni reembolsos).',
};

const CUSTOMS_DISCLAIMER = {
  id: 'customs_import_responsibility',
  title: 'Responsabilidad aduanera',
  checkoutText:
    'Entiendo y acepto que soy el único responsable de cumplir con las normativas de importación, aranceles, impuestos o retenciones aduaneras de mi país de destino (Estados Unidos, Suiza, etc.). Cazador de Sueños Sigar SRL no se hace responsable por retenciones o impuestos aplicados en la aduana de destino',
  filterBlockedReason:
    'Debes aceptar el descargo de responsabilidad aduanera para finalizar el pedido.',
};

/** @returns {{ valid: boolean, error?: string }} */
function validateFinalSaleAcceptance(accepted) {
  if (accepted === true || accepted === 'true' || accepted === 'on') {
    return { valid: true };
  }
  return { valid: false, error: SALES_POLICY.filterBlockedReason };
}

/** @returns {{ valid: boolean, error?: string }} */
function validateCustomsDisclaimer(accepted) {
  if (accepted === true || accepted === 'true' || accepted === 'on') {
    return { valid: true };
  }
  return { valid: false, error: CUSTOMS_DISCLAIMER.filterBlockedReason };
}

function isOrderEligibleForRefund(_order) {
  return false;
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    SALES_POLICY,
    CUSTOMS_DISCLAIMER,
    validateFinalSaleAcceptance,
    validateCustomsDisclaimer,
    isOrderEligibleForRefund,
  };
}
