# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html)
from odoo import models


class SaleMakePlannedInvoice(models.TransientModel):
    _inherit = "sale.make.planned.invoice"

    def create_invoices_by_plan(self):
        sale = self.env["sale.order"].browse(self._context.get("active_id"))
        if sale.invoice_plan_mode == "payer":
            # One invoice per payer, all at once.
            sale._check_invoice_plan_payer_lines()
            self = self.with_context(all_remain_invoices=True)
        return super().create_invoices_by_plan()
