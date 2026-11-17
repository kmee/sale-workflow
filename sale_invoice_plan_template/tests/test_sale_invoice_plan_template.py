# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html)
from odoo import Command
from odoo.exceptions import ValidationError
from odoo.tests import Form, tagged

from odoo.addons.sale.tests.common import TestSaleCommon


@tagged("post_install", "-at_install")
class TestSaleInvoicePlanTemplate(TestSaleCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Partner = cls.env["res.partner"]
        cls.owner_b = Partner.create({"name": "Owner B"})
        cls.template = cls.env["sale.invoice.plan.template"].create(
            {
                "name": "Half and half",
                "line_ids": [
                    Command.create({"percent": 50.0}),
                    Command.create({"partner_id": cls.owner_b.id, "percent": 50.0}),
                ],
            }
        )
        cls.customer = Partner.create(
            {"name": "Owner A", "invoice_plan_template_id": cls.template.id}
        )
        cls.product = cls.env["product.product"].create(
            {"name": "Labour", "type": "service", "list_price": 100.0}
        )

    def test_template_total(self):
        with self.assertRaises(ValidationError):
            self.env["sale.invoice.plan.template"].create(
                {"name": "Wrong", "line_ids": [Command.create({"percent": 60.0})]}
            )

    def test_contact_inherits_template(self):
        contact = self.env["res.partner"].create(
            {"name": "Contact", "parent_id": self.customer.id}
        )
        self.assertEqual(contact.invoice_plan_template_id, self.template)

    def test_create_loads_payers(self):
        order = self.env["sale.order"].create(
            {
                "partner_id": self.customer.id,
                "order_line": [Command.create({"product_id": self.product.id})],
            }
        )
        self.assertTrue(order.use_invoice_plan)
        self.assertEqual(order.invoice_plan_mode, "payer")
        self.assertEqual(
            order.invoice_plan_ids.mapped("payer_partner_id"),
            self.customer | self.owner_b,
        )
        self.assertEqual(order.invoice_plan_ids.mapped("installment"), [1, 2])

    def test_explicit_plan_wins(self):
        order = self.env["sale.order"].create(
            {
                "partner_id": self.customer.id,
                "use_invoice_plan": True,
                "invoice_plan_mode": "payer",
                "invoice_plan_ids": [
                    Command.create(
                        {"payer_partner_id": self.owner_b.id, "percent": 100.0}
                    )
                ],
            }
        )
        self.assertEqual(order.invoice_plan_ids.payer_partner_id, self.owner_b)

    def test_form_onchange(self):
        with Form(self.env["sale.order"]) as order_form:
            order_form.partner_id = self.customer
            self.assertEqual(order_form.invoice_plan_template_id, self.template)
            self.assertEqual(len(order_form.invoice_plan_ids), 2)
            with order_form.order_line.new() as line:
                line.product_id = self.product
        order = order_form.save()
        self.assertEqual(len(order.invoice_plan_ids), 2)
        order.action_confirm()
