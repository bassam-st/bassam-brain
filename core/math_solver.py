# -*- coding: utf-8 -*-
# core/math_solver.py
from sympy import symbols, Eq, simplify, factor, expand, diff, integrate, solve, sympify

def explain_math_answer(expr_text: str) -> str:
    """
    يحاول فهم المسألة (تبسيط/تحليل/حل/تفاضل/تكامل) حسب الكلمات المفتاحية داخل النص.
    أمثلة:
      "بسط (x^2 - 1)/(x-1)"
      "حل المعادلة x^2 - 5x + 6 = 0"
      "حل للمتغير x: 2*x + 3 = 7"
      "حل جهاز المعادلات: x + y = 3, x - y = 1"
      "فرّق x^3"
      "كامل x"
    """
    x, y, z = symbols("x y z")
    t = expr_text.strip()

    def _fmt(value):
        try:
            return str(value)
        except Exception:
            return repr(value)

    # حالة جهاز معادلات بسيط
    if "جهاز" in t or "نظام" in t or ("=" in t and "," in t and ":" not in t):
        try:
            parts = [p for p in t.split(",") if "=" in p]
            eqs = []
            for p in parts:
                left, right = p.split("=")
                eqs.append(Eq(sympify(left), sympify(right)))
            sol = solve(eqs, dict=True)
            return f"حل جهاز المعادلات:\n{_fmt(sol)}"
        except Exception as e:
            return f"تعذّر تحليل جهاز المعادلات: {e}"

    # تفاضل
    if any(k in t for k in ["فرق", "تفاضل", "مشتقة"]) or t.startswith("فرّق"):
        try:
            expr = sympify(t.split(":", 1)[-1] if ":" in t else t.replace("فرّق", "").strip())
            return f"المشتقة: d/dx {expr} = {diff(expr)}"
        except Exception as e:
            return f"تعذّر التفاضل: {e}"

    # تكامل
    if any(k in t for k in ["كامل", "تكامل"]):
        try:
            expr = sympify(t.split(":", 1)[-1] if ":" in t else t.replace("كامل", "").strip())
            return f"التكامل: ∫ {expr} dx = {integrate(expr)} + C"
        except Exception as e:
            return f"تعذّر التكامل: {e}"

    # حل معادلة
    if "حل" in t and "=" in t:
        try:
            left, right = t.split("=", 1)
            eq = Eq(sympify(left.replace("حل", "").strip()), sympify(right.strip()))
            sol = solve(eq)
            return f"حل المعادلة {eq}:\n{_fmt(sol)}"
        except Exception as e:
            return f"تعذّر حل المعادلة: {e}"

    # تبسيط/تحليل/توسيع بحسب كلمات
    try:
        expr = sympify(t)
        steps = []
        steps.append(f"التعبير الأصلي: {expr}")
        steps.append(f"تبسيط: {simplify(expr)}")
        steps.append(f"تحليل: {factor(expr)}")
        steps.append(f"توسيع: {expand(expr)}")
        return "\n".join(steps)
    except Exception as e:
        return f"تعذّر فهم المسألة: {e}"
