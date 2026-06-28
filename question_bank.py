from __future__ import annotations

from typing import Any


QUESTION_BANK: dict[str, list[dict[str, Any]]] = {
    "programming": [
        {
            "question": "Which data structure uses Last In First Out order?",
            "options": ["Queue", "Stack", "Tree", "Graph"],
            "answer": "Stack",
        },
        {
            "question": "Which keyword is used to create a function in Python?",
            "options": ["func", "def", "function", "lambda"],
            "answer": "def",
        },
        {
            "question": "What does SQL stand for?",
            "options": [
                "Structured Query Language",
                "Simple Query Language",
                "Sequential Question Logic",
                "System Query Layout",
            ],
            "answer": "Structured Query Language",
        },
    ],
    "ai-ml": [
        {
            "question": "Which library is widely used for machine learning in Python?",
            "options": ["NumPy", "Flask", "Scikit-learn", "Tkinter"],
            "answer": "Scikit-learn",
        },
        {
            "question": "What is overfitting?",
            "options": [
                "A model performs well only on training data",
                "A model has too little data",
                "A dataset is missing values",
                "A model uses no labels",
            ],
            "answer": "A model performs well only on training data",
        },
        {
            "question": "Which task is supervised learning?",
            "options": ["Clustering", "Classification", "Dimensionality reduction", "Association"],
            "answer": "Classification",
        },
    ],
    "datascience": [
        {
            "question": "Which library is commonly used for tabular data analysis?",
            "options": ["Pandas", "Flask", "FastAPI", "Pillow"],
            "answer": "Pandas",
        },
        {
            "question": "A bar chart is best suited for comparing:",
            "options": ["Categories", "Paragraphs", "APIs", "Passwords"],
            "answer": "Categories",
        },
        {
            "question": "What does CSV stand for?",
            "options": [
                "Comma Separated Values",
                "Column Safe Variable",
                "Code Structured View",
                "Common Source Vector",
            ],
            "answer": "Comma Separated Values",
        },
    ],
    "webdevelopment": [
        {
            "question": "Which language runs in the browser?",
            "options": ["Python", "Java", "JavaScript", "SQL"],
            "answer": "JavaScript",
        },
        {
            "question": "Which HTML tag creates a hyperlink?",
            "options": ["<link>", "<a>", "<href>", "<p>"],
            "answer": "<a>",
        },
        {
            "question": "CSS is used for:",
            "options": ["Database queries", "Styling", "Authentication only", "File upload"],
            "answer": "Styling",
        },
    ],
}

