# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html)
from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    invoice_plan_template_id = fields.Many2one(
        comodel_name="sale.invoice.plan.template",
        string="Invoice Plan Template",
        help="Payers loaded on new sales orders of this customer.",
    )

    @api.model
    def _commercial_fields(self):
        return super()._commercial_fields() + ["invoice_plan_template_id"]
