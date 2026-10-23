version: intake.v1
Extract contact details from one message sent to a sales assistant. Reply with ONLY a JSON object:
{"name": string or null, "business": string or null, "question": true or false}

- name: the sender's own name, only if they state it.
- business: what the sender's business is called or does (for example "computer parts selling"), only if they state it.
- question: true if the message asks anything.
- Use words that appear in the message. Use null when unsure. Never invent anything.
