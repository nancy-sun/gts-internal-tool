# TODO

This file tracks follow-up work after the current implementation.

## Manual Verification

- Test Customs batch upload with a real office HS Code workbook.
- Test Customs export report with a real GTS list workbook.
- Test Product Customs Mapping with real products and common customs item categories.
- Test Purchase Contract module with a real supplier purchase contract.
- Review Missing Customs Data after importing a real quotation workbook with `G.W.` and `Packages`.
- Confirm product search shows mapped Customs HS Code first and legacy `products.hs_code` only as fallback.
- Confirm quotation upload and quotation generation do not show Customs/HS fields.

## Customs Roadmap

- Done: Phase 1 Customs Center / Customs Items.
- Done: Phase 2 Product Customs Mapping / Missing Customs Data Check.
- Done: Phase 3 Purchase Contract module.
- Next: Phase 4 Declaration Batch.
- Then: Phase 5 Declaration Detail Preview + Blocking Issues.
- Then: Phase 6 Export 报关明细 + 要素.
- Later: full customs workbook generation.
- Later: purchase contract Excel templates.

## Deployment And Infrastructure

- Alibaba Cloud staging deployment.
- ICP filing and `internal.gtsmotor.cn` domain setup.
- Final deployment checklist review before staging.
- Test Docker Compose PostgreSQL smoke flow before ECS deployment when deployment files change.
- Add real migration tooling before production schema changes after launch.
- OSS file storage implementation for durable uploaded/generated files.

## Later Product Improvements

- Role permission refinement.
- Sales portal later, after deployment/auth/storage decisions are stable.
- Payment approval later.
- Long-term customs TODO: promote stable product-level weight and packaging master data if quotation fallback becomes insufficient.
- Decide whether browser sessions should expire automatically after a workday.
- Add browser automation for main UI flows if visual checks become repetitive.
- Revisit backup/restore testing after the first office test cycle.
- Add a post-upload audit summary for changed price, changed factory, changed OEM, confirmed duplicates, and failed rows.
- Group product search results by product, with quotation history expandable below each product.
