import pytest
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from website.questions import evaluate_user_answer
ROMANIAN_MATH_MAP = {
    "zece": "10",
    "împărțit la": "/",
    "cinci": "5",
}

def translate_romanian_math(phrase):
    for ro, en in ROMANIAN_MATH_MAP.items():
        phrase = phrase.replace(ro, en)
    return phrase

@pytest.fixture
def exact_pairs():
    return [
        ("capital of france", "capital of france", 1.0),
        ("Capital of France", "capital of france", 1.0),
        ("capital-of-france", "capital of france", 0.44),
    ]

@pytest.fixture
def math_pairs():
    return [
        ("2 + 2", "4", 1.0),
        ("10/5", "2", 1.0),
        ("3 * 5", "15", 1.0),
        ("2 plus 2", "4", 0.0),
        ("zece împărțit la cinci", "2", 0.0),
        ("3 +", "3", 0.0),
    ]

@pytest.fixture
def semantic_pairs():
    return [
        ("big dog", "large canine", 0.13),
        ("A small feline", "a little cat", 0.3),
        ("înmulțire între 5 și 4", "5 * 4", 1.0),
    ]

@pytest.fixture
def edge_cases():
    return [
        ("", "something", 0.0),
        ("         ", "anything", 0.0),
        ("UNKNOWN", "", 0.0),
        ("!@#$", "!@#$", 1.0),
    ]

@pytest.mark.parametrize("user_input, correct_answer, expected_score", [
    ("2+2", "4", 1.0),
    ("four", "4", 0.7),
    ("capital of france", "Capital of France", 1.0),
    ("înmulțit cu 3", "3 * 1", 0.65),
    ("3*4", "12", 1.0),
    ("paris", "capital of france", 0.3),
])
def test_soft_scoring(user_input, correct_answer, expected_score):
    score = evaluate_user_answer(user_input, correct_answer)
    assert score >= expected_score - 0.1, f"{user_input} vs {correct_answer} → Score: {score}"

def test_exact_match(exact_pairs):
    for user_input, correct, expected in exact_pairs:
        score = evaluate_user_answer(user_input, correct)
        assert abs(score - expected) < 1e-6 or abs(score - expected) < 0.05, f"Exact match failed: {user_input} vs {correct}"

def test_math_match(math_pairs):
    for user_input, correct, expected in math_pairs:
        score = evaluate_user_answer(user_input, correct)
        assert score >= expected - 0.1, f"Math match failed: {user_input} vs {correct}"

def test_semantic_similarity(semantic_pairs):
    for user_input, correct, expected in semantic_pairs:
        score = evaluate_user_answer(user_input, correct)
        assert score >= expected - 0.15, f"Semantic similarity failed: {user_input} vs {correct}"

def test_edge_cases(edge_cases):
    for user_input, correct, expected in edge_cases:
        score = evaluate_user_answer(user_input, correct)
        assert abs(score - expected) < 1e-6 or abs(score - expected) < 0.05, f"Edge case failed: {user_input} vs {correct}"

def test_logging_of_debug_case(capfd):
    evaluate_user_answer("cat", "a small feline")
    out, _ = capfd.readouterr()
    assert "Scoring Breakdown" in out or "User expanded:" in out or "Math evaluation failed" in out
