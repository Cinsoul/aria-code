# Replenishment Policy — Northgate DC

*Owner: Inventory Planning · Version 3.2 · Applies to weekly ordering runs*

## 1. Scope

This policy sets the order quantity for every stocked SKU in the weekly ordering run. Orders are
placed with each SKU's supplier as listed in `suppliers.csv`.

## 2. Demand

2.1 Use the **most recent 28 days** of daily demand only. Older history reflects a range and
pricing we no longer run and must not be used.

2.2 d̄ is the mean daily demand over those 28 days; σd is their **sample** standard deviation.

2.3 A SKU with fewer than **14 days** of demand history is not ordered by this policy. Report it as
`insufficient_history`; the category manager orders it by hand.

## 3. Service level

Safety stock is held to a service level set by the SKU's ABC class:

| Class | Service level | z |
|---|---|---:|
| A | 98% | 2.054 |
| B | 95% | 1.645 |
| C | 90% | 1.282 |

## 4. Order quantity

4.1 Lead time L is the supplier's quoted lead time in days, taken as fixed.

4.2 **Safety stock** = z × σd × √L, rounded **up** to a whole unit.

4.3 **Reorder point** = d̄ × L + safety stock, rounded **up** to a whole unit.

4.4 **Inventory position** = on hand + on order − backorders.

4.5 If the inventory position is **at or below** the reorder point, order up to the reorder
point plus one review period (7 days) of mean demand:

    quantity needed = reorder point + d̄ × 7 − inventory position

then round the quantity needed **up** to a whole number of the supplier's case packs, and order
at least the supplier's minimum order quantity (MOQ). Otherwise order nothing.

## 5. Exclusions

5.1 SKUs with status `discontinued` are never reordered, whatever their stock position.
