# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html)

{
    "name": "Sales Invoice Plan Template",
    "summary": "Reusable payer splits, loaded on the sales order from the customer",
    "version": "18.0.1.0.0",
    "author": "KMEE,Odoo Community Association (OCA)",
    "license": "AGPL-3",
    "website": "https://github.com/OCA/sale-workflow",
    "category": "Sales",
    "depends": ["sale_invoice_plan_partner"],
    "data": [
        "security/ir.model.access.csv",
        "views/sale_invoice_plan_template_views.xml",
        "views/res_partner_views.xml",
        "views/sale_order_views.xml",
    ],
    "installable": True,
    "development_status": "Alpha",
}
