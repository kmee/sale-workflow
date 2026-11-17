# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html)

{
    "name": "Sales CRM Invoice Plan",
    "summary": "Payers of the invoicing on the opportunity, copied to the quotation",
    "version": "18.0.1.0.0",
    "author": "KMEE,Odoo Community Association (OCA)",
    "license": "AGPL-3",
    "website": "https://github.com/OCA/sale-workflow",
    "category": "Sales",
    "depends": ["sale_crm", "sale_invoice_plan_template"],
    "data": [
        "security/ir.model.access.csv",
        "views/crm_lead_views.xml",
    ],
    "installable": True,
    "development_status": "Alpha",
}
