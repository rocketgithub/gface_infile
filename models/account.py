# -*- encoding: utf-8 -*-

from openerp import models, fields, api, _
from openerp.exceptions import UserError, ValidationError

from datetime import datetime
import base64
import zeep
import logging

class AccountInvoice(models.Model):
    _inherit = "account.invoice"

    firma_gface = fields.Char('Firma GFACE', copy=False)
    pdf_gface = fields.Char('PDF GFACE', copy=False)

    def invoice_validate(self):
        detalles = []
        subtotal = 0
        for factura in self:
            if factura.journal_id.usuario_gface and not factura.firma_gface:

                tipo_cambio = 1
                if factura.currency_id.id != factura.company_id.currency_id.id:
                    total = 0
                    for l in factura.move_id.line_ids:
                        if l.account_id.id == factura.account_id.id:
                            total += l.debit - l.credit
                    tipo_cambio = abs(total / factura.amount_total)

                descuento_total = 0
                for linea in factura.invoice_line_ids:
                    det = {}

                    det["unidadMedida"] = "UND"
                    det["cantidad"] = linea.quantity
                    det["codigoProducto"] = linea.product_id.default_code
                    det["descripcionProducto"] = linea.name
                    det["precioUnitario"] = linea.price_unit * ( 1 - linea.discount / 100 ) * tipo_cambio
                    det["montoBruto"] = linea.price_subtotal * det["cantidad"]
                    # det["montoDescuento"] = (linea.price_unit * linea.quantity) * (linea.discount / 100)
                    det["montoDescuento"] = 0
                    det["importeNetoGravado"] = det["cantidad"] * det["precioUnitario"]
                    det["importeExento"] = 0
                    det["importeOtrosImpuestos"] = 0
                    det["importeTotalOperacion"] = det["cantidad"] * det["precioUnitario"]
                    det["detalleImpuestosIva"] = 0
                    r = linea.invoice_line_tax_ids.compute_all(det["precioUnitario"], currency=factura.currency_id, quantity=det["cantidad"], product=linea.product_id, partner=factura.partner_id)
                    for impuestos in r['taxes']:
                        det["detalleImpuestosIva"] = impuestos['amount']

                    if linea.product_id.type == "service":
                        det["tipoProducto"] = "S"
                    else:
                        det["tipoProducto"] = "B"

                    descuento_total += det["montoDescuento"]
                    subtotal += linea.price_unit * linea.quantity
                    detalles.append(det)

                dte = {}
                dte["usuario"] = factura.journal_id.usuario_gface
                dte["clave"] = factura.journal_id.clave_gface
                dte["validador"] = False
                dte["dte"] = {}
                dte["dte"]["tipoDocumento"] = factura.journal_id.tipo_documento_gface
                dte["dte"]["estadoDocumento"] = "Activo"
                dte["dte"]["numeroDocumento"] = "odoo_aquih_"+str(factura.id)
                dte["dte"]["serieAutorizada"] = factura.journal_id.serie_gface
                dte["dte"]["codigoMoneda"] = "GTQ"
                if factura.currency_id.id != factura.company_id.currency_id.id:
                    dte["dte"]["codigoMoneda"] = "USD"
                dte["dte"]["tipoCambio"] = tipo_cambio
                dte["dte"]["regimen2989"] = False
                dte["dte"]["regimenISR"] = "RET_DEFINITIVA"
                dte["dte"]["correoComprador"] = "N/A"
                dte["dte"]["serieDocumento"] = factura.journal_id.serie_documento_gface
                dte["dte"]["telefonoComprador"] = "N/A"
                dte["dte"]["fechaDocumento"] = datetime.strptime(factura.date_invoice, '%Y-%m-%d')
                dte["dte"]["fechaResolucion"] = datetime.strptime(factura.journal_id.fecha_resolucion_gface, '%Y-%m-%d')
                dte["dte"]["numeroResolucion"] = factura.journal_id.numero_resolucion_gface
                dte["dte"]["nitComprador"] = factura.partner_id.vat
                dte["dte"]["direccionComercialComprador"] = factura.partner_id.street
                dte["dte"]["departamentoComprador"] = "N/A"
                dte["dte"]["municipioComprador"] = "N/A"
                dte["dte"]["nombreComercialComprador"] = factura.partner_id.name
                dte["dte"]["nitVendedor"] = factura.company_id.vat
                dte["dte"]["codigoEstablecimiento"] = factura.journal_id.numero_establecimiento_gface
                dte["dte"]["departamentoVendedor"] = "N/A"
                dte["dte"]["municipioVendedor"] = "N/A"
                dte["dte"]["direccionComercialVendedor"] = factura.company_id.street
                dte["dte"]["nombreComercialRazonSocialVendedor"] = factura.company_id.name
                dte["dte"]["nombreCompletoVendedor"] = factura.company_id.name
                dte["dte"]["idDispositivo"] = factura.journal_id.dispositivo_gface
                dte["dte"]["importeBruto"] = factura.amount_untaxed * tipo_cambio
                dte["dte"]["importeDescuento"] = descuento_total
                dte["dte"]["importeTotalExento"] = 0
                dte["dte"]["importeOtrosImpuestos"] = 0
                dte["dte"]["importeNetoGravado"] = factura.amount_total * tipo_cambio
                dte["dte"]["detalleImpuestosIva"] = factura.amount_tax * tipo_cambio
                dte["dte"]["montoTotalOperacion"] = factura.amount_total * tipo_cambio
                dte["dte"]["descripcionOtroImpuesto"] = "N/A"
                dte["dte"]["observaciones"] = "N/A"
                dte["dte"]["detalleDte"] = detalles

                wsdl = 'https://www.ingface.net/listener/ingface?wsdl'
                client = zeep.Client(wsdl=wsdl)

                resultado = client.service.registrarDte(dte=dte)
                logging.warn(resultado)

                if resultado["estado"] == "1":
                    factura.firma_gface = resultado['cae']
                    factura.pdf_gface = 'https://www.ingface.net/Ingfacereport/dtefactura.jsp?cae='+resultado['cae']
                    factura.name = resultado['numeroDte']
                else:
                    raise UserError(resultado["descripcion"])

        return super(AccountInvoice,self).invoice_validate()

class AccountJournal(models.Model):
    _inherit = "account.journal"

    usuario_gface = fields.Char('Usuario GFACE', copy=False)
    clave_gface = fields.Char('Clave GFACE', copy=False)
    nombre_establecimiento_gface = fields.Char('Nombre Establecimiento GFACE', copy=False)
    tipo_documento_gface = fields.Selection([('FACE', 'FACE')], 'Tipo de Documento GFACE', copy=False)
    serie_documento_gface = fields.Selection([('63', '63'),('66', '66')], 'Serie de Documento GFACE', copy=False)
    serie_gface = fields.Char('Serie GFACE', copy=False)
    numero_resolucion_gface = fields.Char('Numero Resolucion GFACE', copy=False)
    fecha_resolucion_gface = fields.Date('Fecha Resolución GFACE', copy=False)
    rango_inicial_gface = fields.Integer('Rango Inicial GFACE', copy=False)
    rango_final_gface = fields.Integer('Rango Final GFACE', copy=False)
    numero_establecimiento_gface = fields.Char('Numero Establecimiento GFACE', copy=False)
    dispositivo_gface = fields.Char('Dispositivo GFACE', copy=False)
