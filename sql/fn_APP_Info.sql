/* ============================================================================
   fn_APP_Info  -  the valuation workbook's Info tab as a query, for any report month
   Database : Nutun_Audit_2026_July26
   Reads    : dbo.PBD_info, dbo.ACM_Snap_BookUniverse, dbo.ACM_Payments, dbo.ACM_VB_Alloc
              (the last three are built by ACM_Pipeline_Simplified.sql)
   Creates  : dbo.fn_APP_Info (inline table-valued function). No table is created or changed.

   COLUMNS 1-5 ARE THE INFO TAB, exactly as pasted in the July-26 workbook:
     wClientCode (999-form), VB, Age, CAEIR, Cost (= purchase price)
   The remaining columns let the app run historical report months:
     Age_Rolled          PBD_info.Age rolled back from the extract month to @ReportMonth
     Age_ChargeOff       months from the book's first charge-off month to @ReportMonth, inclusive
     Age_FirstCollection months from the first in-scope collection month to @ReportMonth (01_Ages.sas)
     ObservedMonths      payment months <= @ReportMonth (ACM_Payments rows)
     InScope             1 = the book had an Info row, was charged off and had paid by @ReportMonth

   USAGE
     -- the Info tab, July-26 run (539 rows expected)
     SELECT wClientCode, VB, Age, CAEIR, Cost
     FROM dbo.fn_APP_Info('2026-07-01', NULL)
     WHERE HasInfoRow = 1
     ORDER BY CASE WHEN wClientCode < 999000000 THEN 0 ELSE 1 END, wClientCode;

     -- a historical run: books in scope at 2025-09
     SELECT * FROM dbo.fn_APP_Info('2025-09-01', NULL) WHERE InScope = 1;

   @ExtractMonth = the month PBD_info.Age is measured to. NULL = MAX(ACM_Payments.PaymentMonth)
   (2026-07-01 for the July-26 extract).
   ============================================================================ */
USE [Nutun_Audit_2026_July26];
GO
SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO
CREATE OR ALTER FUNCTION dbo.fn_APP_Info
(
    @ReportMonth  DATE,     -- any day in the report month; normalised to the 1st
    @ExtractMonth DATE      -- NULL = latest payment month in ACM_Payments
)
RETURNS TABLE
AS
RETURN
WITH prm AS (
    SELECT ReportMonth  = DATEFROMPARTS(YEAR(@ReportMonth), MONTH(@ReportMonth), 1),
           ExtractMonth = COALESCE(DATEFROMPARTS(YEAR(@ExtractMonth), MONTH(@ExtractMonth), 1),
                                   (SELECT MAX(PaymentMonth) FROM dbo.ACM_Payments))
),
info AS (                     -- PBD_info is keyed on the 999-form; keep one row per code, count duplicates
    SELECT Code999, VB, Age, CAEIR, Cost, InfoRows
    FROM (
        SELECT Code999  = TRY_CONVERT(BIGINT, i.wClientCode),
               VB       = TRY_CONVERT(INT, i.VB),
               Age      = TRY_CONVERT(INT, i.Age),
               CAEIR    = TRY_CONVERT(FLOAT, i.CAEIR),
               Cost     = TRY_CONVERT(DECIMAL(18,2), i.Cost),
               InfoRows = COUNT(*) OVER (PARTITION BY TRY_CONVERT(BIGINT, i.wClientCode)),
               rn       = ROW_NUMBER() OVER (PARTITION BY TRY_CONVERT(BIGINT, i.wClientCode)
                                             ORDER BY i.VB, i.CAEIR, i.Cost)
        FROM dbo.PBD_info AS i
        WHERE i.wClientCode IS NOT NULL
    ) AS d
    WHERE d.rn = 1
),
pay AS (                      -- ACM_Payments.wClientCode is the BOOK code (= universe BookCode)
    SELECT BookCode          = a.wClientCode,
           FirstPaymentMonth = MIN(a.PaymentMonth),
           LastPaymentMonth  = MAX(a.PaymentMonth),
           ObservedMonths    = COUNT(*),
           CollectedToDate   = SUM(CAST(a.curPayment AS DECIMAL(38,2)))
    FROM dbo.ACM_Payments AS a
    CROSS JOIN prm
    WHERE a.PaymentMonth <= prm.ReportMonth
    GROUP BY a.wClientCode
)
SELECT
    /* ---- the Info tab ---- */
    wClientCode         = u.Code999,
    VB                  = f.VB,
    Age                 = f.Age,
    CAEIR               = f.CAEIR,
    Cost                = f.Cost,
    /* ---- keys and attributes ---- */
    BookCode            = u.BookCode,
    CustomerCode        = u.CustomerCode,
    VB_Computed         = al.VB,
    PP_Alloc            = al.PP,
    Face                = CAST(u.Face AS DECIMAL(18,2)),
    FirstChargeOff      = u.FirstChargeOff,
    ChargeOffMonth      = CASE WHEN u.FirstChargeOff IS NULL THEN NULL
                               ELSE DATEFROMPARTS(YEAR(u.FirstChargeOff), MONTH(u.FirstChargeOff), 1) END,
    FirstPaymentMonth   = p.FirstPaymentMonth,
    LastPaymentMonth    = p.LastPaymentMonth,
    ObservedMonths      = ISNULL(p.ObservedMonths, 0),
    CollectedToDate     = ISNULL(p.CollectedToDate, 0),
    /* ---- ages at the report month ---- */
    Age_Rolled          = f.Age - DATEDIFF(MONTH, prm.ReportMonth, prm.ExtractMonth),
    Age_ChargeOff       = CASE WHEN u.FirstChargeOff IS NULL THEN NULL
                               ELSE DATEDIFF(MONTH, DATEFROMPARTS(YEAR(u.FirstChargeOff), MONTH(u.FirstChargeOff), 1),
                                             prm.ReportMonth) + 1 END,
    Age_FirstCollection = CASE WHEN p.FirstPaymentMonth IS NULL THEN NULL
                               ELSE DATEDIFF(MONTH, p.FirstPaymentMonth, prm.ReportMonth) + 1 END,
    /* ---- flags ---- */
    HasInfoRow          = CASE WHEN f.Code999 IS NULL THEN 0 ELSE 1 END,
    InfoDuplicateRows   = CASE WHEN f.InfoRows IS NULL THEN 0 ELSE f.InfoRows - 1 END,
    InScope             = CASE WHEN f.Code999 IS NOT NULL
                                AND u.FirstChargeOff < DATEADD(MONTH, 1, prm.ReportMonth)
                                AND ISNULL(p.ObservedMonths, 0) > 0
                               THEN 1 ELSE 0 END,
    ReportMonth         = prm.ReportMonth,
    ExtractMonth        = prm.ExtractMonth
FROM dbo.ACM_Snap_BookUniverse AS u
CROSS JOIN prm
LEFT JOIN info              AS f  ON f.Code999      = u.Code999
LEFT JOIN pay               AS p  ON p.BookCode     = u.BookCode
LEFT JOIN dbo.ACM_VB_Alloc  AS al ON al.wClientCode = u.Code999;
GO

/* ---- CHECKS - run after creating the function; compare with the July-26 workbook Info tab ---- */
SELECT Check_          = 'Info rows (expect 539)',
       Value_          = COUNT(*)
FROM dbo.fn_APP_Info('2026-07-01', NULL) WHERE HasInfoRow = 1
UNION ALL
SELECT 'Sum Cost (compare with the Info tab total)', CAST(SUM(Cost) AS DECIMAL(20,2))
FROM dbo.fn_APP_Info('2026-07-01', NULL) WHERE HasInfoRow = 1
UNION ALL
SELECT 'Books with duplicate PBD_info rows (expect 0)', SUM(CASE WHEN InfoDuplicateRows > 0 THEN 1 ELSE 0 END)
FROM dbo.fn_APP_Info('2026-07-01', NULL)
UNION ALL
SELECT 'Info VB <> ACM_VB (expect 0)', COUNT(*)
FROM dbo.fn_APP_Info('2026-07-01', NULL) AS x
JOIN dbo.ACM_VB AS v ON v.wClientCode = x.wClientCode
WHERE v.VB <> x.VB
UNION ALL
SELECT 'Info CAEIR <> ACM_CAEIR (expect 0)', COUNT(*)
FROM dbo.fn_APP_Info('2026-07-01', NULL) AS x
JOIN dbo.ACM_CAEIR AS c ON c.wClientCode = x.wClientCode
WHERE ABS(c.CAEIR - x.CAEIR) > 1e-12 OR ABS(c.PP - x.Cost) > 0.005
UNION ALL
SELECT 'Computed VB <> Info VB (informational)', COUNT(*)
FROM dbo.fn_APP_Info('2026-07-01', NULL)
WHERE HasInfoRow = 1 AND VB_Computed IS NOT NULL AND VB_Computed <> VB
UNION ALL
SELECT 'Age (Info) <> Age_ChargeOff (informational)', COUNT(*)
FROM dbo.fn_APP_Info('2026-07-01', NULL)
WHERE HasInfoRow = 1 AND ISNULL(Age, -1) <> ISNULL(Age_ChargeOff, -1);
GO
