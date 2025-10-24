# brain/planner.py
from __future__ import annotations
from typing import List, Dict
from .analyzer import analyze_query

def plan_pipeline(query: str) -> List[Dict]:
    a = analyze_query(query)
    steps: List[Dict] = [{"name":"analyze","meta":a}]
    # قرار بسيط: متى نبحث؟ متى نلخص؟ متى نولّد؟
    if a["intent"] in ["search","summarize","qa"]:
        steps.append({"name":"web_search"})
        steps.append({"name":"summarize"})
    if a["intent"] in ["qa","code","math"]:
        steps.append({"name":"generate"})
    steps.append({"name":"learn"})  # التعلم من التجربة
    return steps
