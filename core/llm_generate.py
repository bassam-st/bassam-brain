# توليد الإجابات الذكية – Bassam Brain
from transformers import AutoTokenizer, AutoModelForCausalLM

MODEL_NAME = "Qwen/Qwen2.5-1.5B-Instruct"  # مجاني ويعمل بالعربية

tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
model = AutoModelForCausalLM.from_pretrained(MODEL_NAME)

def generate_answer(prompt: str, max_new_tokens=200):
    """توليد إجابة ذكية بالعربية"""
    inputs = tokenizer(prompt, return_tensors="pt")
    output = model.generate(**inputs, max_new_tokens=max_new_tokens, temperature=0.7)
    text = tokenizer.decode(output[0], skip_special_tokens=True)
    return text.split("User:")[-1].strip()
