// Минимальный вычислитель условий для мастера настроек: A || B, A && B, !A, x == y, x != y, 'a' in list.
function term(t, ctx) {
  let m;
  t = t.trim();
  if ((m = t.match(/^'([^']*)'\s+in\s+(\w+)$/))) {
    const v = ctx[m[2]];
    return Array.isArray(v) && v.includes(m[1]);
  }
  if ((m = t.match(/^(\w+)\s*(==|!=)\s*(\w+)$/))) {
    const eq = String(ctx[m[1]]) === m[3];
    return m[2] === "==" ? eq : !eq;
  }
  if (t.startsWith("!")) return !term(t.slice(1), ctx);
  return Boolean(ctx[t]);
}

export function evalIf(expr, ctx) {
  if (!expr) return true;
  return expr.split("||").some((or) => or.split("&&").every((t) => term(t, ctx)));
}
