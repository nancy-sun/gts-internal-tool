# Customs Business Rules

This document records the customs data rules that later purchase contract, declaration batch, declaration detail preview, and customs export modules must follow.

## Product Customs Mapping

- One product / one GTS No. maps to exactly one customs item.
- One customs item can be used by many products / many GTS numbers.
- `product_customs_mappings.product_id` is unique in the current phase.
- If staff maps the same product again, the system updates the existing mapping instead of creating a second active mapping.

## HS Code Source Of Truth

- Future source of truth: `product_customs_mappings -> customs_items.hs_code`.
- `products.hs_code` remains as a legacy fallback for old HS Code upload/report compatibility.
- Do not remove `products.hs_code` until the customs mapping workflow fully replaces the old compatibility flow.

## Generic Unit Sources

Do not hardcode declaration units.

- Do not assume `unit_1` is `个`.
- Do not assume `unit_2` is `千克`.
- Do not assume single-unit items are quantity-based.
- Do not assume second-unit items are weight-based.

Supported unit sources:

- `quantity`
- `gross_weight`
- `net_weight`
- `volume`
- `package_count`
- `manual`

`customs_items` stores the rules only. Declaration quantity calculation belongs to later declaration detail work.

## Gross Weight And Packages Sources

- Gross weight currently comes from uploaded quotation-type files, usually the `G.W.` / `gross_weight` field.
- Packages comes from uploaded quotation-type files, specifically the `packages` field.
- Do not use `item/package` as package count.
- Phase 2 uses the latest related `quotation_items` row by `updated_at`, then `created_at`, then highest `id` as fallback.
- A stable product-level weight/packaging master data model is a future improvement.

## Net Weight Company Rule

Company rule:

```text
net_weight = gross_weight - packages
```

For any customs item using `net_weight` as a unit source:

- Gross weight is required.
- Packages is required.
- If `gross_weight - packages <= 0`, this is a blocking issue.
- Error text must clearly say: `净重计算错误：毛重 - 件数 必须大于 0。`

Do not ask users to maintain a separate net weight field in the current phase.

## Missing Data Check

The missing customs data page is a readiness check only. It does not create declaration batches or export customs workbooks.

It should flag:

- Products without customs mapping.
- Mapped customs items missing HS Code.
- Products requiring gross weight but missing usable gross weight.
- Products requiring package count but missing usable packages.
- Products requiring net weight with missing gross weight, missing packages, or invalid net weight calculation.
- Mapped customs items missing declaration element template.
- Manual unit sources as warnings for later declaration detail entry.
