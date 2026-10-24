/**
 * Configuración global de producción.
 * Las claves de PayPal y CardNET viven en el entorno del servidor, nunca aquí.
 */
const APP_CONFIG = {
  currency: 'USD',
  locale: 'es',

  /** Cobro simulado retirado: el checkout solo usa pasarelas reales del servidor. */
  sandbox: {
    enabled: false,
    allowMockCheckout: false,
    label: '',
    ordersStorageKey: 'cazador_sueno_orders',
  },

  bankTransfer: {
    currency: 'USD',
    referencePrefix: 'CS-',
    email: 'cazadordesueno1@gmail.com',
    proofDeadlineHours: 48,
    instructions:
      'Realiza la transferencia e incluye la referencia exacta del pedido en el concepto/descripción. Envía el comprobante al correo indicado dentro de 48 horas para activar el envío. El pedido se procesa al registrar la transferencia.',
    beneficiary: {
      name: 'Cazador de Sueño Cigars SRL',
      address: 'Calle El Conde No. 102, Zona Colonial, Santo Domingo 10210, República Dominicana',
      taxId: 'RNC 1-31-98765-4',
    },
    accounts: [
      {
        currency: 'DOP',
        bankName: 'Banco de Reservas',
        accountHolder: 'Sandy Dejesús Rodríguez Abreu',
        accountType: 'Cuenta de Ahorros',
        accountNumber: '9605921112',
        note: 'Transferencia a cuenta de ahorros Banreservas.',
      },
      {
        currency: 'DOP',
        bankName: 'Banco BHD',
        accountHolder: 'Sandy Rodríguez',
        accountType: 'Cuenta de Ahorros',
        accountNumber: '15705310035',
        note: 'Transferencia a cuenta de ahorros BHD.',
      },
    ],
  },

  contact: {
    email: 'cazadordesueno1@gmail.com',
    phone: '+1 (809) 464-5016',
  },

  whatsapp: {
    enabled: true,
    phone: '18094645016',
    label: 'Finalizar pedido por WhatsApp',
    floatLabel: 'WhatsApp',
  },

  trust: {
    authenticity: 'Productos 100% auténticos — tabaco premium de origen certificado.',
    delivery: 'Despacho internacional DHL con seguimiento y tiempos estimados por zona.',
    policy: 'Venta final con transparencia total antes de confirmar el pago.',
  },
};

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { APP_CONFIG };
}

