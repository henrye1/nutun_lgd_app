const dash = '—'
const bad = (x: number | null | undefined): x is null | undefined => x === null || x === undefined || Number.isNaN(x)

export const fmtRate = (x: number | null | undefined) => (bad(x) ? dash : x.toFixed(4))
export const fmtPct = (x: number | null | undefined) => (bad(x) ? dash : `${(x * 100).toFixed(2)}%`)
export const fmtYield = (x: number | null | undefined) => (bad(x) ? dash : Number(x.toPrecision(6)).toString())
export const fmtInt = (x: number | null | undefined) => (bad(x) ? dash : Math.round(x).toLocaleString('en-GB'))
export const fmtNum = (x: number | null | undefined, dp = 2) => (bad(x) ? dash : x.toFixed(dp))
