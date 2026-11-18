# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html)
from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools.float_utils import float_compare, float_is_zero


class SaleInvoicePlan(models.Model):
    _inherit = "sale.invoice.plan"

    payer_partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Payer",
        index=True,
        help="Partner invoiced for this installment when the plan splits "
        "the order by payer.",
    )
    plan_date = fields.Date(default=fields.Date.context_today)
    currency_id = fields.Many2one(related="sale_id.currency_id")

    @api.model_create_multi
    def create(self, vals_list):
        next_installment = {}
        for vals in vals_list:
            sale = self.env["sale.order"].browse(vals.get("sale_id"))
            if sale.invoice_plan_mode != "payer":
                continue
            if not vals.get("payer_partner_id"):
                vals["payer_partner_id"] = sale.partner_invoice_id.id
            if not vals.get("installment"):
                if sale.id not in next_installment:
                    used = sale.invoice_plan_ids.mapped("installment")
                    next_installment[sale.id] = max(used or [0]) + 1
                vals["installment"] = next_installment[sale.id]
                next_installment[sale.id] += 1
        plans = super().create(vals_list)
        plans._invalidate_payer_amounts()
        return plans

    def write(self, vals):
        if "payer_partner_id" in vals and self.filtered("invoiced"):
            raise UserError(
                self.env._(
                    "The payer of an invoiced installment cannot be changed. "
                    "Cancel its invoices first."
                )
            )
        res = super().write(vals)
        if {"installment", "percent", "payer_partner_id"} & set(vals):
            self._invalidate_payer_amounts()
        return res

    def unlink(self):
        sales = self.sale_id
        res = super().unlink()
        sales.invoice_plan_ids._invalidate_payer_amounts()
        return res

    def _invalidate_payer_amounts(self):
        """The split of an installment moves the amount of the others."""
        self.sale_id.filtered(
            lambda sale: sale.invoice_plan_mode == "payer"
        ).invoice_plan_ids.invalidate_recordset(["amount"])

    # Payers are often set before the order lines: in the payer mode the
    # percent drives the plan and the amount is what the split will invoice,
    # which differs from the percent when goods go by whole unit. Once
    # invoiced, the base rewrites the percent from the invoiced amount: keep
    # the percent.
    # The other installments of the order are no dependency on purpose: the
    # form would recompute them before its onchange snapshot and never show
    # the new amounts. sale.order recomputes them in an onchange, and
    # _invalidate_payer_amounts() outside the form.
    @api.depends(
        "percent",
        "payer_partner_id",
        "sale_id.amount_untaxed",
        "sale_id.partner_invoice_id",
        "sale_id.order_line.product_uom_qty",
        "sale_id.order_line.price_subtotal",
        "sale_id.order_line.invoice_plan_payer_id",
    )
    def _compute_amount(self):
        payer_plans = self.filtered(
            lambda plan: plan.sale_id.invoice_plan_mode == "payer"
        )
        for sale in payer_plans.sale_id:
            quantities = sale._get_invoice_plan_payer_quantities()
            lines = sale.order_line.filtered(lambda line: line.product_uom_qty)
            for plan in payer_plans.filtered(lambda p, sale=sale: p.sale_id == sale):
                if plan.invoiced:
                    plan.amount = plan.amount_invoiced
                    continue
                plan.amount = sale.currency_id.round(
                    sum(
                        quantities.get((plan.id, line.id), 0.0)
                        * line.price_subtotal
                        / line.product_uom_qty
                        for line in lines
                    )
                )
        return super(SaleInvoicePlan, self - payer_plans)._compute_amount()

    @api.onchange("amount", "percent")
    def _inverse_amount(self):
        payer_plans = self.filtered(
            lambda plan: plan.sale_id.invoice_plan_mode == "payer"
        )
        return super(SaleInvoicePlan, self - payer_plans)._inverse_amount()

    @api.constrains("payer_partner_id", "percent", "invoice_type")
    def _check_payer_plan(self):
        self.sale_id._check_invoice_plan_payer()

    def _compute_new_invoice_quantity(self, invoice_move):
        self.ensure_one()
        if self.sale_id.invoice_plan_mode != "payer":
            return super()._compute_new_invoice_quantity(invoice_move)
        quantities = self.sale_id._get_invoice_plan_payer_quantities()
        move = invoice_move.with_context(check_move_validity=False)
        for line in move.invoice_line_ids.filtered(
            lambda line: line.display_type not in ("line_section", "line_note")
        ):
            order_line = fields.first(line.sale_line_ids)
            if order_line.is_downpayment:
                self._update_new_quantity(line, self.percent)
                continue
            qty = quantities.get((self.id, order_line.id), 0.0)
            prec = order_line.product_uom.rounding
            if float_compare(qty, line.quantity, precision_rounding=prec) == 1:
                raise ValidationError(
                    self.env._(
                        "Plan quantity: %(plan_qty)s, exceed invoiceable quantity: "
                        "%(invoiceable_qty)s"
                        "\nProduct should be delivered before invoice"
                    )
                    % {"plan_qty": qty, "invoiceable_qty": line.quantity}
                )
            if float_is_zero(qty, precision_rounding=prec):
                line.unlink()
            else:
                line.write({"quantity": qty})
        move.line_ids.filtered(
            lambda x: x.display_type
            not in ("product", "line_section", "line_note", "payment_term", "tax")
        ).unlink()
