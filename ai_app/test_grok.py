from django.conf import settings
from groq import Groq

client = Groq(api_key=settings.GROQ_API_KEY)

response = client.chat.completions.create(
    model="llama-3.1-8b-instant",
    messages=[
        {"role": "user", "content": "Explain artificial intelligence simply"}
    ]
)

print(response.choices[0].message.content)
