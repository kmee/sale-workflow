Splits the invoicing of one sales order among several payers, for
instance the co-owners of an asset, each one with its own invoice and
receivable.

It adds a *Payers* mode to the invoice plan of `sale_invoice_plan`: each
installment has a payer and a percentage, and the plan creates one
invoice per payer, all at once.

How each order line is split:

- a line can have a fixed payer, and then goes whole to it;
- services and goods in other units of measure are split in proportion;
- goods sold by unit are split in whole units (no 1.5 engine): each
  payer first gets the whole units of its share of each line, then the
  units left over, from the most expensive, go one by one to the payer
  furthest below its share of the order;
- the main installment, the one of the invoice address of the order (or
  else the one with the largest share), wins the ties and takes the
  rounding differences.
