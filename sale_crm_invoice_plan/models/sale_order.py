# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html)
from odoo import api, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _get_invoice_plan_payer_vals(self):
        self.ensure_one()
        lines = self.opportunity_id.invoice_plan_line_ids
        if not lines:
            return super()._get_invoice_plan_payer_vals()
        return [
            {"payer_partner_id": line.payer_partner_id.id, "percent": line.percent}
            for line in lines
        ]

    @api.onchange("opportunity_id")
    def _onchange_opportunity_id_invoice_plan(self):
        if self.state in ("draft", "sent") and not self.invoice_count:
            self._load_invoice_plan_payers()
