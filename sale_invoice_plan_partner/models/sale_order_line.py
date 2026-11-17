# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html)
from odoo import fields, models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    invoice_plan_payer_id = fields.Many2one(
        comodel_name="res.partner",
        string="Fixed Payer",
        copy=False,
        help="When the invoice plan splits by payer, the whole line is "
        "invoiced to this payer instead of being split.",
    )

    def _invoice_plan_split_by_unit(self):
        """Goods sold by unit are split among payers in whole units."""
        self.ensure_one()
        return (
            self.product_id.type != "service"
            and self.product_uom.category_id
            == self.env.ref("uom.product_uom_categ_unit")
        )
