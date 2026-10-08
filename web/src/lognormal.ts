export const lognormal = (t: number, m: number, s: number, cn: number) => {
  const z = (Math.log(t) - m) / s
  return (cn * Math.exp((-z * z) / 2)) / (t * s * Math.sqrt(2 * Math.PI))
}
