from datetime import datetime


def generate_ubl_xml(order: dict, lines: list, invoice_number: str, invoice_type: str) -> str:
    """
    GİB UBL-TR 1.2 şemasına uygun (imzasız) e-Arşiv / e-Fatura XML üretir.
    Hackathon demo için yapısal doğruluk önceliklendirilmiştir.
    """
    now = datetime.now()
    issue_date = now.strftime("%Y-%m-%d")
    issue_time = now.strftime("%H:%M:%S")

    doc_type = "EARSIVFATURA" if invoice_type == "earsiv" else "EFATURA"
    total_gross = abs(order.get("gross_amount", 0))

    # KDV hesabı (Gemini'nin önerdiği oranları kullan, yoksa %20 varsay)
    line_xml_parts = []
    total_kdv = 0.0
    total_net_before_tax = 0.0

    for i, line in enumerate(lines, 1):
        qty = line.get("quantity", 1)
        unit_price = abs(line.get("unit_price", 0))
        kdv_rate = line.get("gemini_kdv_rate") or 20
        line_total = qty * unit_price
        kdv_amount = line_total * (kdv_rate / 100)
        total_kdv += kdv_amount
        total_net_before_tax += line_total

        line_xml_parts.append(f"""    <cac:InvoiceLine>
      <cbc:ID>{i}</cbc:ID>
      <cbc:InvoicedQuantity unitCode="C62">{qty}</cbc:InvoicedQuantity>
      <cbc:LineExtensionAmount currencyID="TRY">{line_total:.2f}</cbc:LineExtensionAmount>
      <cac:Item>
        <cbc:Name>{_escape(line.get('product_name', 'Ürün'))}</cbc:Name>
        <cac:SellersItemIdentification>
          <cbc:ID>{line.get('barcode', 'N/A')}</cbc:ID>
        </cac:SellersItemIdentification>
      </cac:Item>
      <cac:Price>
        <cbc:PriceAmount currencyID="TRY">{unit_price:.2f}</cbc:PriceAmount>
      </cac:Price>
      <cac:TaxTotal>
        <cbc:TaxAmount currencyID="TRY">{kdv_amount:.2f}</cbc:TaxAmount>
        <cac:TaxSubtotal>
          <cbc:TaxableAmount currencyID="TRY">{line_total:.2f}</cbc:TaxableAmount>
          <cbc:TaxAmount currencyID="TRY">{kdv_amount:.2f}</cbc:TaxAmount>
          <cbc:Percent>{kdv_rate}</cbc:Percent>
          <cac:TaxCategory>
            <cac:TaxScheme>
              <cbc:Name>KDV</cbc:Name>
            </cac:TaxScheme>
          </cac:TaxCategory>
        </cac:TaxSubtotal>
      </cac:TaxTotal>
    </cac:InvoiceLine>""")

    lines_xml = "\n".join(line_xml_parts)
    grand_total = total_net_before_tax + total_kdv

    customer_name = _escape(order.get("customer_name", "Bireysel Müşteri"))
    customer_tax = order.get("customer_tax_id") or "11111111111"
    customer_city = _escape(order.get("customer_city", "İstanbul"))
    marketplace = _escape(order.get("marketplace", "Pazaryeri"))
    order_id = _escape(order.get("marketplace_order_id", ""))

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
         xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
         xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">

  <!-- UBL-TR 1.2 — {doc_type} — DEMO (İmzasız) -->

  <cbc:UBLVersionID>2.1</cbc:UBLVersionID>
  <cbc:CustomizationID>TR1.2</cbc:CustomizationID>
  <cbc:ProfileID>{doc_type}</cbc:ProfileID>
  <cbc:ID>{invoice_number}</cbc:ID>
  <cbc:CopyIndicator>false</cbc:CopyIndicator>
  <cbc:IssueDate>{issue_date}</cbc:IssueDate>
  <cbc:IssueTime>{issue_time}</cbc:IssueTime>
  <cbc:InvoiceTypeCode>SATIS</cbc:InvoiceTypeCode>
  <cbc:Note>Pazaryeri: {marketplace} | Sipariş No: {order_id}</cbc:Note>
  <cbc:DocumentCurrencyCode>TRY</cbc:DocumentCurrencyCode>

  <cac:Signature>
    <cbc:ID schemeID="VKN">DEMO</cbc:ID>
    <!-- Mali mühür üretim ortamında eklenir -->
  </cac:Signature>

  <cac:AccountingSupplierParty>
    <cac:Party>
      <cac:PartyIdentification>
        <cbc:ID schemeID="VKN">1234567890</cbc:ID>
      </cac:PartyIdentification>
      <cac:PartyName>
        <cbc:Name>PazarMuhasebe Demo Satıcı</cbc:Name>
      </cac:PartyName>
      <cac:PostalAddress>
        <cbc:CityName>İstanbul</cbc:CityName>
        <cac:Country><cbc:Name>Türkiye</cbc:Name></cac:Country>
      </cac:PostalAddress>
    </cac:Party>
  </cac:AccountingSupplierParty>

  <cac:AccountingCustomerParty>
    <cac:Party>
      <cac:PartyIdentification>
        <cbc:ID schemeID="{'VKN' if order.get('is_company') else 'TCKN'}">{customer_tax}</cbc:ID>
      </cac:PartyIdentification>
      <cac:PartyName>
        <cbc:Name>{customer_name}</cbc:Name>
      </cac:PartyName>
      <cac:PostalAddress>
        <cbc:CityName>{customer_city}</cbc:CityName>
        <cac:Country><cbc:Name>Türkiye</cbc:Name></cac:Country>
      </cac:PostalAddress>
    </cac:Party>
  </cac:AccountingCustomerParty>

  <cac:TaxTotal>
    <cbc:TaxAmount currencyID="TRY">{total_kdv:.2f}</cbc:TaxAmount>
  </cac:TaxTotal>

  <cac:LegalMonetaryTotal>
    <cbc:LineExtensionAmount currencyID="TRY">{total_net_before_tax:.2f}</cbc:LineExtensionAmount>
    <cbc:TaxExclusiveAmount currencyID="TRY">{total_net_before_tax:.2f}</cbc:TaxExclusiveAmount>
    <cbc:TaxInclusiveAmount currencyID="TRY">{grand_total:.2f}</cbc:TaxInclusiveAmount>
    <cbc:PayableAmount currencyID="TRY">{grand_total:.2f}</cbc:PayableAmount>
  </cac:LegalMonetaryTotal>

{lines_xml}

</Invoice>"""

    return xml


def _escape(text: str) -> str:
    """XML özel karakterlerini escape eder."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )
