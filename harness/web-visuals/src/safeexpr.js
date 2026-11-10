/* Safe arithmetic expression compiler for Luminest visual specs.
 *
 * A spec may contain mathematical expressions (e.g. "sin(x)*x^2"). Those strings arrive
 * from the backend / the tutor model and are untrusted input. We therefore NEVER use
 * eval, new Function, or property access. This module tokenises a deliberately tiny
 * grammar and evaluates an AST with a closed function table.
 *
 * Grammar (right-associative ^, standard unary minus):
 *   expr   := term  (('+' | '-') term)*
 *   term   := unary (('*' | '/') unary)*
 *   unary  := ('+' | '-') unary | power
 *   power  := primary ('^' unary)?
 *   primary:= number | ident | ident '(' args ')' | '(' expr ')'
 *
 * Identifiers resolve ONLY to: the caller-declared variables, the constants pi/e, or an
 * entry in FUNCS. Anything else is a compile error. This is the same policy the backend
 * enforces structurally: no unknown keys, no code, no ambient globals.
 */

const FUNCS = Object.freeze({
  sin: Math.sin, cos: Math.cos, tan: Math.tan,
  asin: Math.asin, acos: Math.acos, atan: Math.atan,
  sqrt: Math.sqrt, abs: Math.abs, exp: Math.exp,
  ln: Math.log, log10: Math.log10, log2: Math.log2,
  floor: Math.floor, ceil: Math.ceil, round: Math.round, sign: Math.sign,
  sinh: Math.sinh, cosh: Math.cosh, tanh: Math.tanh,
  min: Math.min, max: Math.max, pow: Math.pow, atan2: Math.atan2,
});

const ARITY = Object.freeze({
  sin: 1, cos: 1, tan: 1, asin: 1, acos: 1, atan: 1,
  sqrt: 1, abs: 1, exp: 1, ln: 1, log10: 1, log2: 1,
  floor: 1, ceil: 1, round: 1, sign: 1,
  sinh: 1, cosh: 1, tanh: 1,
  min: 2, max: 2, pow: 2, atan2: 2,
});

class ParseError extends Error { }

function tokenize(source) {
  const items = [];
  let p = 0;
  while (p < source.length) {
    const ch = source[p];
    if (/\s/.test(ch)) { p += 1; continue; }
    if (/[0-9.]/.test(ch)) {
      const m = /^(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?/.exec(source.slice(p));
      if (!m) throw new ParseError('BAD_NUMBER');
      items.push({ t: 'num', v: Number(m[0]) });
      p += m[0].length;
      continue;
    }
    if (/[A-Za-z_]/.test(ch)) {
      const m = /^[A-Za-z_][A-Za-z0-9_]*/.exec(source.slice(p));
      items.push({ t: 'ident', v: m[0] });
      p += m[0].length;
      continue;
    }
    if ('+-*/^(),'.includes(ch)) { items.push({ t: ch }); p += 1; continue; }
    throw new ParseError('ILLEGAL_CHARACTER');
  }
  if (items.length > 512) throw new ParseError('TOO_MANY_TOKENS');
  items.push({ t: 'eof' });
  return items;
}

/** Compile `source` into a pure numeric function. Returns {ok, error} on rejection. */
export function compileExpression(source, variables = ['x']) {
  if (typeof source !== 'string' || !source.trim() || source.length > 2048) {
    return { ok: false, error: 'EXPRESSION_INVALID' };
  }
  const vars = new Set(variables);
  let tokens;
  try { tokens = tokenize(source); } catch (e) { return { ok: false, error: e.message }; }

  let i = 0;
  let nodes = 0;
  let depth = 0;
  const MAX_NODES = 256;
  const MAX_DEPTH = 48;
  const peek = () => tokens[i];
  const take = () => tokens[i++];
  const node = (value) => {
    nodes += 1;
    if (nodes > MAX_NODES) throw new ParseError('EXPRESSION_TOO_COMPLEX');
    return value;
  };
  const expect = (t) => { if (peek().t !== t) throw new ParseError('UNEXPECTED_TOKEN'); take(); };
  const enter = () => { depth += 1; if (depth > MAX_DEPTH) throw new ParseError('EXPRESSION_TOO_DEEP'); };
  const leave = () => { depth -= 1; };

  function primary() {
    enter();
    try {
      const t = peek();
      if (t.t === 'num') { take(); return node({ k: 'num', v: t.v }); }
      if (t.t === 'ident') {
        take();
        const name = t.v;
        if (peek().t === '(') {
          take();
          const args = [];
          if (peek().t !== ')') {
            for (;;) {
              args.push(expr());
              if (peek().t === ',') { take(); continue; }
              break;
            }
          }
          expect(')');
          if (!Object.prototype.hasOwnProperty.call(FUNCS, name)) throw new ParseError('UNKNOWN_FUNCTION');
          if (args.length !== ARITY[name]) throw new ParseError('BAD_ARITY');
          return node({ k: 'call', name, args });
        }
        if (name === 'pi') return node({ k: 'num', v: Math.PI });
        if (name === 'e') return node({ k: 'num', v: Math.E });
        if (vars.has(name)) return node({ k: 'var', name });
        throw new ParseError('UNKNOWN_IDENTIFIER');
      }
      if (t.t === '(') { take(); const inner = expr(); expect(')'); return inner; }
      throw new ParseError('UNEXPECTED_TOKEN');
    } finally { leave(); }
  }

  function power() {
    const base = primary();
    if (peek().t === '^') { take(); return node({ k: 'bin', op: '^', a: base, b: unary() }); }
    return base;
  }
  function unary() {
    if (peek().t === '-') { take(); return node({ k: 'neg', a: unary() }); }
    if (peek().t === '+') { take(); return unary(); }
    return power();
  }
  function term() {
    let left = unary();
    while (peek().t === '*' || peek().t === '/') {
      const op = take().t;
      left = node({ k: 'bin', op, a: left, b: unary() });
    }
    return left;
  }
  function expr() {
    let left = term();
    while (peek().t === '+' || peek().t === '-') {
      const op = take().t;
      left = node({ k: 'bin', op, a: left, b: term() });
    }
    return left;
  }

  let ast;
  try {
    ast = expr();
    if (peek().t !== 'eof') throw new ParseError('TRAILING_TOKENS');
  } catch (e) {
    return { ok: false, error: e instanceof ParseError ? e.message : 'EXPRESSION_INVALID' };
  }

  function evaluateNode(n, env) {
    switch (n.k) {
      case 'num': return n.v;
      case 'var': return Number(env[n.name]);
      case 'neg': return -evaluateNode(n.a, env);
      case 'call': {
        const values = n.args.map((a) => evaluateNode(a, env));
        if (values.some((v) => !Number.isFinite(v))) return NaN;
        return FUNCS[n.name](...values);
      }
      case 'bin': {
        const a = evaluateNode(n.a, env);
        const b = evaluateNode(n.b, env);
        switch (n.op) {
          case '+': return a + b;
          case '-': return a - b;
          case '*': return a * b;
          case '/': return a / b;
          case '^': return Math.pow(a, b);
          default: return NaN;
        }
      }
      default: return NaN;
    }
  }

  return {
    ok: true,
    error: '',
    nodeCount: nodes,
    evaluate(env) {
      const value = evaluateNode(ast, env || {});
      return Number.isFinite(value) ? value : NaN;
    },
  };
}

/** Sample a compiled expression over a closed interval; non-finite samples break the run. */
export function sample(compiled, from, to, count, variable = 'x') {
  const points = [];
  const n = Math.max(2, Math.min(2000, Math.floor(count)));
  for (let i = 0; i < n; i += 1) {
    const v = from + ((to - from) * i) / (n - 1);
    const y = compiled.evaluate({ [variable]: v });
    points.push([v, Number.isFinite(y) ? y : null]);
  }
  return points;
}
