# TODO

This file tracks known follow-up work after the current implementation.

## Manual Verification

- Test the Customs batch upload flow with a real office HS Code workbook.
- Test the Customs export report flow with a real GTS list workbook.
- Test Product Customs Mapping with real GTS products and common customs item categories.
- Review Missing Customs Data results after importing a real quotation workbook with G.W. and Packages.
- Confirm product search shows HS Code and quotation upload / quotation generation do not show HS Code.

## Later Improvements

- Final deploy hardening and checklist review.
- Alibaba Cloud staging deployment.
- ICP filing and `internal.gtsmotor.cn` domain setup.
- Test Docker Compose PostgreSQL smoke flow before real ECS deployment when deployment files change.
- Complete `DEPLOYMENT_CHECKLIST.md` before Alibaba Cloud staging.
- File storage / OSS abstraction and implementation plan.
- Add real migration tooling before production schema changes after launch.
- Role permission refinement.
- Sales portal later, after deployment/auth/storage decisions are stable.
- Sales portal v0.
- Payment approval later.
- Customs Phase 1: Customs Center / Customs Items is implemented.
- Customs Phase 2: Product Customs Mapping and Missing Customs Data Check is implemented.
- Customs Phase 3: Purchase Contract.
- Customs Phase 4: Declaration Batch.
- Customs Phase 5: Declaration Detail Preview with blocking issues.
- Customs Phase 6: Export 报关明细 and 报关要素 sheets.
- Long-term customs TODO: promote stable product-level weight and packaging master data if quotation fallback becomes insufficient.
- Decide deployment strategy before building a sales portal.
- Test a Cloudflare Tunnel pilot if leadership wants remote access.
- Refine role permissions before storing sales quotation data.
- Decide whether browser sessions should expire automatically after a workday.
- Add browser automation for the main UI flows if manual visual checks become repetitive.
- Revisit backup/restore testing after the first office test cycle.
- Add a post-upload audit summary for changed price, changed factory, changed OEM, confirmed duplicates, and failed rows.
- Group product search results by product, with quotation history expandable below each product.
- Add a data quality page for missing HS Code, missing OEM, missing description, and products with no quotation history.
- Add a recent activity panel on the dashboard for latest uploads, generated quotation files, HS Code updates, and product edits.
