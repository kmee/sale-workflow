# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html)
from odoo import Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests import Form, tagged

from odoo.addons.sale.tests.common import TestSaleCommon


@tagged("post_install", "-at_install")
class TestSaleInvoicePlanPartner(TestSaleCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Partner = cls.env["res.partner"]
        cls.customer = Partner.create({"name": "Owner A"})
        cls.payer_b = Partner.create({"name": "Owner B"})
        cls.payer_c = Partner.create({"name": "Owner C"})
        cls.part = cls.env["product.product"].create(
            {
                "name": "Engine part",
                "type": "consu",
                "invoice_policy": "order",
                "list_price": 100.0,
                "uom_id": cls.env.ref("uom.product_uom_unit").id,
                "uom_po_id": cls.env.ref("uom.product_uom_unit").id,
            }
        )
        cls.labour = cls.env["product.product"].create(
            {
                "name": "Maintenance labour",
                "type": "service",
                "invoice_policy": "order",
                "list_price": 1000.0,
            }
        )

    def _create_order(self, plan, lines=None):
        lines = lines or [(self.part, 3), (self.labour, 1)]
        return self.env["sale.order"].create(
            {
                "partner_id": self.customer.id,
                "use_invoice_plan": True,
                "invoice_plan_mode": "payer",
                "order_line": [
                    Command.create(
                        {
                            "product_id": product.id,
                            "product_uom_qty": qty,
                            "price_unit": product.list_price,
                            "tax_id": False,
                        }
                    )
                    for product, qty in lines
                ],
                "invoice_plan_ids": [
                    Command.create({"payer_partner_id": payer.id, "percent": percent})
                    for payer, percent in plan
                ],
            }
        )

    def _invoice(self, order):
        self.env["sale.make.planned.invoice"].with_context(
            active_id=order.id, active_ids=order.ids
        ).create({}).create_invoices_by_plan()
        return order.invoice_ids

    def _qty(self, invoices, payer, product):
        lines = invoices.filtered(lambda m: m.partner_id == payer).invoice_line_ids
        return sum(
            lines.filtered(lambda line: line.product_id == product).mapped("quantity")
        )

    def test_plan_defaults(self):
        order = self._create_order([(self.payer_b, 50), (self.payer_c, 50)])
        self.assertEqual(order.invoice_plan_ids.mapped("installment"), [1, 2])
        self.assertTrue(all(order.invoice_plan_ids.mapped("plan_date")))
        # A new installment defaults to the invoice address of the order
        order.write({"invoice_plan_ids": [Command.create({"percent": 0.0})]})
        self.assertEqual(order.invoice_plan_ids[-1].payer_partner_id, self.customer)
        self.assertEqual(order.invoice_plan_ids[-1].installment, 3)

    def test_one_invoice_per_payer(self):
        order = self._create_order(
            [(self.customer, 50), (self.payer_b, 30), (self.payer_c, 20)]
        )
        order.action_confirm()
        invoices = self._invoice(order)
        self.assertEqual(len(invoices), 3)
        self.assertEqual(
            invoices.partner_id, self.customer | self.payer_b | self.payer_c
        )
        self.assertTrue(all(order.invoice_plan_ids.mapped("invoiced")))
        # Parts by whole unit: none as a whole share (1.5, 0.9, 0.6 → 1, 0,
        # 0), then the 2 left to the payers most below their share: B, C
        self.assertEqual(self._qty(invoices, self.payer_b, self.part), 1)
        self.assertEqual(self._qty(invoices, self.payer_c, self.part), 1)
        self.assertEqual(self._qty(invoices, self.customer, self.part), 1)
        # Services in proportion
        self.assertAlmostEqual(self._qty(invoices, self.payer_b, self.labour), 0.3)
        self.assertAlmostEqual(self._qty(invoices, self.payer_c, self.labour), 0.2)
        self.assertAlmostEqual(self._qty(invoices, self.customer, self.labour), 0.5)
        self.assertAlmostEqual(sum(invoices.mapped("amount_untaxed")), 1300.0)
        self.assertEqual(order.invoice_status, "invoiced")
        # The invoiced amounts differ from the plan, the percent stays
        order.invalidate_recordset()
        order.invoice_plan_ids.invalidate_recordset()
        plans = order.invoice_plan_ids
        self.assertEqual(plans.mapped("amount"), plans.mapped("amount_invoiced"))
        self.assertEqual(plans.mapped("amount_invoiced"), [600.0, 400.0, 300.0])
        self.assertEqual(order.invoice_plan_ids.mapped("percent"), [50, 30, 20])

    def test_main_payer_without_customer(self):
        order = self._create_order(
            [(self.payer_b, 60), (self.payer_c, 40)], lines=[(self.part, 5)]
        )
        order.action_confirm()
        invoices = self._invoice(order)
        # 5 * 40% = 2 units to C, the other 3 to B, the largest share
        self.assertEqual(self._qty(invoices, self.payer_c, self.part), 2)
        self.assertEqual(self._qty(invoices, self.payer_b, self.part), 3)

    def test_leftover_units_balance_the_order(self):
        cabinet, chair = self.env["product.product"].create(
            [
                {"name": name, "type": "consu", "list_price": price}
                for name, price in (("Cabinet", 140.0), ("Chair", 70.0))
            ]
        )
        order = self._create_order(
            [(self.customer, 50), (self.payer_b, 50)],
            lines=[(chair, 3), (cabinet, 1)],
        )
        # The plan shows the split before invoicing
        self.assertEqual(order.invoice_plan_ids.mapped("amount"), [210.0, 140.0])
        order.order_line.filtered(lambda line: line.product_id == chair).write(
            {"product_uom_qty": 4}
        )
        # 2 chairs each, the cabinet to the main payer
        self.assertEqual(order.invoice_plan_ids.mapped("amount"), [280.0, 140.0])
        order.order_line.filtered(lambda line: line.product_id == chair).write(
            {"product_uom_qty": 3}
        )
        order.action_confirm()
        invoices = self._invoice(order)
        # 1 chair each, then the cabinet to the main payer (a tie) and the
        # last chair to B: 210 / 140, not 280 / 70 line by line
        self.assertEqual(self._qty(invoices, self.customer, cabinet), 1)
        self.assertEqual(self._qty(invoices, self.customer, chair), 1)
        self.assertEqual(self._qty(invoices, self.payer_b, chair), 2)
        self.assertEqual(
            order.invoice_plan_ids.mapped("amount_invoiced"), [210.0, 140.0]
        )

    def test_main_payer_follows_the_plan_order(self):
        contact = self.env["res.partner"].create(
            {"name": "Owner A, contact", "parent_id": self.customer.id}
        )
        cabinet = self.env["product.product"].create(
            {"name": "Cabinet", "type": "consu", "list_price": 140.0}
        )
        order = self._create_order(
            [(self.customer, 50), (contact, 50)], lines=[(cabinet, 1)]
        )
        # Both of the invoice address: the first installment is the main one
        self.assertEqual(order.invoice_plan_ids.mapped("amount"), [140.0, 0.0])
        order.invoice_plan_ids[0].installment = 3
        self.assertEqual(order.invoice_plan_ids.mapped("amount"), [0.0, 140.0])

    def test_form_updates_every_installment(self):
        contact = self.env["res.partner"].create(
            {"name": "Owner A, contact", "parent_id": self.customer.id}
        )
        cabinet = self.env["product.product"].create(
            {"name": "Cabinet", "type": "consu", "list_price": 140.0}
        )
        order = self._create_order(
            [(self.customer, 50), (contact, 50)], lines=[(cabinet, 1)]
        )
        with Form(order) as form:
            with form.invoice_plan_ids.edit(0) as plan:
                plan.installment = 3
            amounts = [plan["amount"] for plan in form.invoice_plan_ids._records]
            self.assertEqual(amounts, [0.0, 140.0])
            with form.order_line.edit(0) as line:
                line.product_uom_qty = 2
            amounts = [plan["amount"] for plan in form.invoice_plan_ids._records]
            self.assertEqual(amounts, [140.0, 140.0])

    def test_fixed_payer_line(self):
        order = self._create_order([(self.customer, 50), (self.payer_b, 50)])
        order.order_line.filtered(
            lambda line: line.product_id == self.part
        ).invoice_plan_payer_id = self.payer_b
        order.action_confirm()
        invoices = self._invoice(order)
        self.assertEqual(self._qty(invoices, self.payer_b, self.part), 3)
        self.assertEqual(self._qty(invoices, self.customer, self.part), 0)
        self.assertAlmostEqual(self._qty(invoices, self.payer_b, self.labour), 0.5)

    def test_fixed_payer_not_in_plan(self):
        order = self._create_order([(self.customer, 100)])
        order.order_line[0].invoice_plan_payer_id = self.payer_c
        order.action_confirm()
        with self.assertRaises(UserError):
            self._invoice(order)

    def test_payer_without_share_is_skipped(self):
        order = self._create_order(
            [(self.customer, 70), (self.payer_b, 30)], lines=[(self.part, 1)]
        )
        order.action_confirm()
        with self.assertRaises(UserError):
            self._invoice(order)

    def test_total_must_be_100_on_confirm(self):
        order = self._create_order([(self.customer, 50), (self.payer_b, 30)])
        with self.assertRaises(ValidationError):
            order.action_confirm()

    def test_payer_once_and_no_advance(self):
        with self.assertRaises(ValidationError):
            self._create_order([(self.customer, 50), (self.customer, 50)])
        order = self._create_order([(self.customer, 100)])
        with self.assertRaises(ValidationError):
            order.write(
                {
                    "invoice_plan_ids": [
                        Command.create({"invoice_type": "advance", "installment": 0})
                    ]
                }
            )

    def test_payer_change_after_confirm(self):
        order = self._create_order([(self.customer, 50), (self.payer_b, 50)])
        order.action_confirm()
        order.invoice_plan_ids[1].payer_partner_id = self.payer_c
        invoices = self._invoice(order)
        self.assertIn(self.payer_c, invoices.partner_id)
        with self.assertRaises(UserError):
            order.invoice_plan_ids[1].payer_partner_id = self.payer_b

    def test_installment_mode_unchanged(self):
        order = self._create_order([(self.payer_b, 100)])
        order.invoice_plan_mode = "installment"
        order.action_confirm()
        invoices = self._invoice(order)
        self.assertEqual(invoices.partner_id, self.customer)
