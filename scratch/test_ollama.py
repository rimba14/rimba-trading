
import openai
client = openai.OpenAI(base_url="http://127.0.0.1:11434/v1", api_key="EMPTY")
try:
    resp = client.chat.completions.create(
        model="qwen2.5-coder:3b",
        messages=[{"role": "user", "content": "Return a JSON object with decision: BUY, confidence: 0.9, reasoning: test"}],
        temperature=0.1
    )
    print(resp.choices[0].message.content)
except Exception as e:
    print(f"Error: {e}")
