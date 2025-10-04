# تلخيص النصوص والمقتطفات – Bassam Brain
from sumy.parsers.plaintext import PlaintextParser
from sumy.nlp.tokenizers import Tokenizer
from sumy.summarizers.lex_rank import LexRankSummarizer

def summarize_snippets(results, max_sentences=5):
    """تلخيص النصوص المستخرجة من نتائج البحث"""
    all_text = ""
    for r in results:
        snippet = (r.get("snippet") or "").strip()
        all_text += snippet + "\n"
    if not all_text.strip():
        return "لم أجد محتوى كافٍ للتلخيص."

    parser = PlaintextParser.from_string(all_text, Tokenizer("arabic"))
    summarizer = LexRankSummarizer()
    summary = summarizer(parser.document, max_sentences)
    return " ".join([str(s) for s in summary])
