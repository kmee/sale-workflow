# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html)
import heapq

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools.float_utils import float_compare, float_round


class SaleOrder(models.Model):
    _inherit = "sale.order"

    invoice_plan_mode = fields.Selection(
        [("installment", "Installments"), ("payer", "Payers")],
        default="installment",
        required=True,
        copy=False,
        help="Installments: the base plan, every invoice to the customer, one "
        "installment at a time.\n"
        "Payers: one invoice per payer of the plan, all created at once.",
    )

    @api.constrains("invoice_plan_mode", "invoice_plan_ids", "state")
    def _check_invoice_plan_payer(self):
        prec = self.env["decimal.precision"].precision_get("Sales Invoice Plan Percent")
        for order in self.filtered(lambda o: o.invoice_plan_mode == "payer"):
            plans = order.invoice_plan_ids
            if plans.filtered(lambda plan: plan.invoice_type == "advance"):
                raise ValidationError(
                    self.env._(
                        "An invoice plan split by payer cannot have advance "
                        "installments."
                    )
                )
            if plans.filtered(lambda plan: not plan.payer_partner_id):
                raise ValidationError(
                    self.env._("Every installment of the plan needs a payer.")
                )
            if len(plans.payer_partner_id) < len(plans):
                raise ValidationError(
                    self.env._("Each payer can appear only once in the plan.")
                )
            if (
                order.use_invoice_plan
                and order.state == "sale"
                and float_compare(
                    sum(plans.mapped("percent")), 100.0, precision_digits=prec
                )
            ):
                raise ValidationError(
                    self.env._(
                        "The payers of the invoice plan must add up to 100%%, "
                        "not %(total)s%%."
                    )
                    % {"total": sum(plans.mapped("percent"))}
                )

    def _check_invoice_plan_payer_lines(self):
        """Lines with a fixed payer must point to a payer of the plan."""
        for order in self:
            payers = order.invoice_plan_ids.payer_partner_id
            lines = order.order_line.filtered(
                lambda line, payers=payers: line.invoice_plan_payer_id
                and line.invoice_plan_payer_id not in payers
            )
            if lines:
                raise UserError(
                    self.env._(
                        "The fixed payer of these lines is not in the invoice "
                        "plan: %(lines)s"
                    )
                    % {"lines": ", ".join(lines.mapped("name"))}
                )

    @api.onchange("invoice_plan_ids", "order_line", "partner_invoice_id")
    def _onchange_invoice_plan_payer_amount(self):
        # A change on one installment moves the split of the others too, but
        # the form only recomputes the line being edited
        if self.invoice_plan_mode == "payer":
            self.invoice_plan_ids._compute_amount()

    def _get_invoice_plan_payer(self):
        """Payer of the installment being invoiced, if the plan splits by payer."""
        self.ensure_one()
        plan_id = self.env.context.get("invoice_plan_id")
        if not plan_id or self.invoice_plan_mode != "payer":
            return self.env["res.partner"]
        plan = self.env["sale.invoice.plan"].browse(plan_id)
        if plan.sale_id != self:
            return self.env["res.partner"]
        return plan.payer_partner_id

    def _get_invoice_plan_main_plan(self, plans):
        """Installment that takes what is left of each line after the split.

        The installment of the invoice address of the order, or else the one
        with the largest share.
        """
        self.ensure_one()
        customer = self.partner_invoice_id.commercial_partner_id
        # Sorted here: on the form the lines keep their order while edited
        plans = plans.sorted(lambda plan: (plan.installment, plan.id or 0))
        main = plans.filtered(
            lambda plan: plan.payer_partner_id.commercial_partner_id == customer
        )[:1]
        return main or plans.sorted(lambda plan: (-plan.percent, plan.installment))[:1]

    def _get_invoice_plan_payer_quantities(self):
        """Quantity of each order line invoiced to each payer.

        Returns {(plan id, order line id): quantity}. A line with a fixed
        payer goes whole to it. Services and goods in other units are split
        in proportion, the main installment taking the rounding difference.
        Goods sold by unit go in whole units: each payer first gets the whole
        units of its share of each line, then the units left over, from the
        most expensive, go one by one to the payer furthest below its share
        of the order (ties to the main installment).
        """
        self.ensure_one()
        plans = self.invoice_plan_ids.filtered(
            lambda plan: plan.invoice_type == "installment"
        )
        if not plans:
            return {}
        main = self._get_invoice_plan_main_plan(plans)
        quantities = {}
        split_total = 0.0
        allocated = {plan.id: 0.0 for plan in plans}
        leftovers = []
        for line in self.order_line.filtered(
            lambda line: not line.display_type and not line.is_downpayment
        ):
            qty = line.product_uom_qty
            if line.invoice_plan_payer_id:
                for plan in plans:
                    fixed = plan.payer_partner_id == line.invoice_plan_payer_id
                    quantities[(plan.id, line.id)] = qty if fixed else 0.0
                continue
            unit_price = line.price_subtotal / qty if qty else 0.0
            split_total += line.price_subtotal
            by_unit = line._invoice_plan_split_by_unit()
            rest = qty
            # By unit, every payer gets its whole units, the main one too
            for plan in plans if by_unit else plans - main:
                share = float_round(
                    qty * plan.percent / 100,
                    precision_rounding=1.0 if by_unit else line.product_uom.rounding,
                    rounding_method="DOWN" if by_unit else "HALF-UP",
                )
                quantities[(plan.id, line.id)] = share
                allocated[plan.id] += share * unit_price
                rest -= share
            if by_unit:
                units = int(
                    float_round(rest, precision_rounding=1.0, rounding_method="DOWN")
                )
                leftovers += [(unit_price, line)] * units
                rest -= units
            rest = float_round(rest, precision_rounding=line.product_uom.rounding)
            quantities[(main.id, line.id)] = (
                quantities.get((main.id, line.id), 0.0) + rest
            )
            allocated[main.id] += rest * unit_price
        # Most expensive units first, each to the payer most below its target
        rank = {plan.id: index for index, plan in enumerate(main | plans)}
        currency = self.currency_id
        heap = [
            (
                currency.round(allocated[plan.id] - split_total * plan.percent / 100),
                rank[plan.id],
            )
            for plan in plans
        ]
        heapq.heapify(heap)
        plan_ids = {index: plan_id for plan_id, index in rank.items()}
        for unit_price, line in sorted(
            leftovers, key=lambda item: (-item[0], item[1].sequence, item[1].id)
        ):
            balance, index = heapq.heappop(heap)
            quantities[(plan_ids[index], line.id)] += 1
            heapq.heappush(heap, (currency.round(balance + unit_price), index))
        return quantities

    def _prepare_invoice(self):
        vals = super()._prepare_invoice()
        payer = self._get_invoice_plan_payer()
        if payer and payer != self.partner_invoice_id:
            delivery = self.env["res.partner"].browse(
                payer.address_get(["delivery"])["delivery"]
            )
            fiscal_position = (
                self.env["account.fiscal.position"]
                .with_company(self.company_id)
                ._get_fiscal_position(payer, delivery=delivery)
            )
            vals.update(
                {
                    "partner_id": payer.id,
                    "partner_shipping_id": delivery.id,
                    "fiscal_position_id": fiscal_position.id,
                }
            )
        return vals

    def _create_invoices(self, grouped=False, final=False, date=None):
        moves = super()._create_invoices(grouped=grouped, final=final, date=date)
        payer = self._get_invoice_plan_payer() if len(self) == 1 else False
        if payer:
            # A payer may have no share of some documents (e.g. no whole unit
            # of a part): drop the invoices left without lines.
            empty = moves.filtered(
                lambda move: not move.invoice_line_ids.filtered(
                    lambda line: line.display_type == "product"
                )
            )
            if empty == moves:
                raise UserError(
                    self.env._(
                        "Nothing to invoice to %(payer)s: its share is less than "
                        "one unit of every line. Change the percentages or set "
                        "a fixed payer on the lines."
                    )
                    % {"payer": payer.display_name}
                )
            empty.unlink()
            moves -= empty
        return moves
