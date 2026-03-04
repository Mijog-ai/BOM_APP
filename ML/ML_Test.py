import os
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig

model_name = "Qwen/Qwen3.5-4B"
cache_dir = "D:/LLMs"
os.makedirs(cache_dir, exist_ok=True)

print(f"PyTorch version : {torch.__version__}")
print(f"CUDA available  : {torch.cuda.is_available()}")
print(f"CUDA version    : {torch.version.cuda}")
print(f"GPUs detected   : {torch.cuda.device_count()}")
for i in range(torch.cuda.device_count()):
    props = torch.cuda.get_device_properties(i)
    print(f"  GPU {i}: {props.name}  |  VRAM: {props.total_memory / 1024**3:.1f} GB")

if not torch.cuda.is_available():
    raise RuntimeError("CUDA not available! Run Step 3 first.")

bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_compute_dtype=torch.float16,
    bnb_4bit_use_double_quant=True,
    bnb_4bit_quant_type="nf4"
)

print("\nLoading tokenizer...")
tokenizer = AutoTokenizer.from_pretrained(model_name, cache_dir=cache_dir)

print("Loading model with 4-bit quantization (first run downloads ~2.5 GB)...")
model = AutoModelForCausalLM.from_pretrained(
    model_name,
    cache_dir=cache_dir,
    quantization_config=bnb_config,
    device_map="auto"
)
print("Model loaded!")
print(f"VRAM used: {torch.cuda.memory_allocated(0) / 1024**3:.2f} GB / "
      f"{torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")

prompt = "Explain how photosynthesis works in simple terms."
inputs = tokenizer(prompt, return_tensors="pt").to("cuda")

with torch.no_grad():
    outputs = model.generate(
        **inputs,
        max_new_tokens=150,
        do_sample=True,
        temperature=0.7,
        top_p=0.9
    )

response = tokenizer.decode(outputs[0], skip_special_tokens=True)
print("\n=== Model Output ===\n")
print(response)
