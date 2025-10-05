from __future__ import annotations
from sympy import symbols, Eq, simplify, factor, expand, diff, integrate, solve, sympify
from sympy.parsing.sympy_parser import parse_expr

def _fmt(step: str) -> str:
    return f"• {step}"

def explain_math_ar(expr_text: str) -> str:
    """
    يكتشف نوع المسألة تلقائياً (تبسيط/تفكيك/توسيع/مشتقة/تكامل/حل معادلة)
    ويعرض خطوات موجزة بالعربية.
    الأمثلة:
      تبسيط:  simplify: (x^2 + 2*x + 1)/(x+1)
      تفكيك:  factor: x^2-1
      توسيع:  expand: (x+1)^3
      مشتقة:  diff: x^3 + 2*x
      تكامل:  integrate: x^2
      حل معادلة: solve: x^2-5*x+6=0
    """
    expr_text = expr_text.strip()

    # نمط الأوامر
    modes = ("simplify:", "factor:", "expand:", "diff:", "integrate:", "solve:")
    mode = None
    for m in modes:
        if expr_text.lower().startswith(m):
            mode = m[:-1]
            expr_text = expr_text[len(m):].strip()
            break

    x, y, z = symbols("x y z")  # متغيرات شائعة
    steps = []

    try:
        if mode in (None, "simplify", "factor", "expand"):
            expr = parse_expr(expr_text, evaluate=False)
            steps.append(_fmt(f"التعبير الأصلي: {expr}"))

            if mode == "simplify" or mode is None:
                s = simplify(expr)
                steps.append(_fmt(f"التبسيط: {s}"))
            if mode == "factor" or mode is None:
                f = factor(expr)
                steps.append(_fmt(f"التفكيك لعوامل: {f}"))
            if mode == "expand" or mode is None:
                e = expand(expr)
                steps.append(_fmt(f"التوسيع: {e}"))

        elif mode == "diff":
            expr = parse_expr(expr_text, evaluate=False)
            steps.append(_fmt(f"التعبير: {expr}"))
            d = diff(expr, x)
            steps.append(_fmt(f"المشتقة بالنسبة لـ x: {d}"))

        elif mode == "integrate":
            expr = parse_expr(expr_text, evaluate=False)
            steps.append(_fmt(f"التعبير: {expr}"))
            I = integrate(expr, x)
            steps.append(_fmt(f"التكامل (غير المحدد): {I} + C"))

        elif mode == "solve":
            # صيغة: left=right أو كثير حدود = 0
            if "=" in expr_text:
                left, right = expr_text.split("=", 1)
                left, right = parse_expr(left, evaluate=False), parse_expr(right, evaluate=False)
                eq = Eq(left, right)
            else:
                eq = Eq(parse_expr(expr_text, evaluate=False), 0)
            steps.append(_fmt(f"المعادلة: {eq}"))
            sol = solve(eq)
            steps.append(_fmt(f"الحلول: {sol}"))

        else:
            return "لم أتعرف على نوع المسألة. استعمل: simplify:/factor:/expand:/diff:/integrate:/solve:"

        return "\n".join(steps)

    except Exception as e:
        return f"تعذّر التحليل الرياضي: {e}"
