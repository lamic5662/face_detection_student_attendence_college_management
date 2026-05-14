from __future__ import annotations

from flask import current_app

try:
    from groq import Groq
except ModuleNotFoundError:  # pragma: no cover - depends on optional extra
    Groq = None  # type: ignore[assignment]

_SYSTEM_PROMPT = """You are SmartAttend AI — a smart assistant inside SmartAttend, a college management system. You have access to real live data from the database for the current user.

CRITICAL RULE — ALWAYS SHOW THE ACTUAL DATA:
When the system context (above) contains real data (attendance %, marks, student list, notes, fees, assignments, timetable, etc.), you MUST display that data directly in your response — do NOT just say "your attendance is available" or "you have some marks". Show the actual numbers, names, and values.

How to display data:
- Attendance → show each subject with present/total and percentage. Flag subjects below 75%.
- Marks → show each exam with score/total and percentage. Mention highest/lowest.
- Students list → show names, roll numbers, attendance %.
- Notes list → show titles clearly numbered.
- Assignments → show title, due date, submitted/pending status.
- Fee → show each fee item with amount and paid/unpaid status.
- Timetable → show day-wise schedule neatly.
- Notices → show title and category.

Formatting:
- Use markdown: **bold** for labels, bullet lists for rows of data.
- After showing data, add a short helpful comment (e.g. which subject needs attention, who is most absent).
- For summaries/explanations, be clear and educational.
- Keep responses focused — don't add unnecessary filler text.

Note summarization:
- If context has "BEST MATCHING NOTE TO SUMMARIZE" with content → summarize it thoroughly: main topic, key points, definitions, examples.
- If student is vague → list available [TEXT] notes and ask which one to summarize.
- If note is [FILE] → tell them: "This note is an uploaded file — I can only summarize notes the teacher typed as text."

Be friendly, professional, and always answer based on the real data provided."""


def _client() -> Groq:
    if Groq is None:
        raise RuntimeError(
            'The optional Groq dependency is not installed. Install requirements.txt '
            'or disable the AI assistant feature.'
        )
    key = current_app.config.get('GROQ_API_KEY', '')
    if not key:
        raise RuntimeError('GROQ_API_KEY is not configured.')
    return Groq(api_key=key)


def chat(messages: list[dict], user_role: str = '', context: str = '') -> str:
    system = _SYSTEM_PROMPT
    if context:
        system = context + '\n\n---\n\n' + system
    if user_role:
        system += f'\n\nThe current user role is: {user_role}'

    response = _client().chat.completions.create(
        model='llama-3.3-70b-versatile',
        messages=[{'role': 'system', 'content': system}] + messages,
        max_tokens=2048,
        temperature=0.5,
    )
    return response.choices[0].message.content.strip()


def generate_notice(topic: str, college_name: str) -> str:
    prompt = (
        f"Write a formal college notice for {college_name} about: {topic}\n\n"
        "Requirements:\n"
        "- Professional and formal tone\n"
        "- Include a clear subject line at the top\n"
        "- Concise body (3-5 sentences)\n"
        "- End with 'For further information, contact the college office.'\n"
        "- Output only the notice text, nothing else"
    )
    response = _client().chat.completions.create(
        model='llama-3.3-70b-versatile',
        messages=[
            {'role': 'system', 'content': 'You are a professional academic content writer.'},
            {'role': 'user', 'content': prompt},
        ],
        max_tokens=400,
        temperature=0.4,
    )
    return response.choices[0].message.content.strip()
