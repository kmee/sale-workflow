# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html)
from odoo import Command, api, fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    invoice_plan_template_id = fields.Many2one(
        comodel_name="sale.invoice.plan.template",
        string="Invoice Plan Template",
        compute="_compute_invoice_plan_template_id",
        store=True,
        readonly=False,
        precompute=True,
    )

    @api.depends("partner_id")
    def _compute_invoice_plan_template_id(self):
        for order in self:
            order.invoice_plan_template_id = (
                order.partner_id.commercial_partner_id.invoice_plan_template_id
            )

    def _get_invoice_plan_payer_vals(self):
        """Payers to load on the order, as sale.invoice.plan values."""
        self.ensure_one()
        if not self.invoice_plan_template_id:
            return []
        return self.invoice_plan_template_id._prepare_invoice_plan_vals(self)

    def _load_invoice_plan_payers(self):
        for order in self:
            vals_list = order._get_invoice_plan_payer_vals()
            if not vals_list:
                continue
            order.update(
                {
                    "use_invoice_plan": True,
                    "invoice_plan_mode": "payer",
                    "invoice_plan_ids": [Command.clear()]
                    + [
                        Command.create(dict(vals, installment=installment))
                        for installment, vals in enumerate(vals_list, start=1)
                    ],
                }
            )

    @api.onchange("invoice_plan_template_id", "partner_invoice_id")
    def _onchange_invoice_plan_template_id(self):
        if self.state in ("draft", "sent") and not self.invoice_count:
            self._load_invoice_plan_payers()

    @api.model_create_multi
    def create(self, vals_list):
        orders = super().create(vals_list)
        for order, vals in zip(orders, vals_list, strict=True):
            if not vals.get("invoice_plan_ids"):
                order._load_invoice_plan_payers()
        return orders

    def action_load_invoice_plan_payers(self):
        self._load_invoice_plan_payers()
