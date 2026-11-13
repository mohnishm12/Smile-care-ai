import pytest

from src.ai import EMERGENCY_PATTERNS, detect_emergency, detect_language
from src.models import EscalationSeverity

CRITICAL = EscalationSeverity.CRITICAL
HIGH = EscalationSeverity.HIGH


@pytest.mark.parametrize(
    ("message", "reason", "severity"),
    [
        # possible cardiac event
        ("I have chest pain since morning", "possible cardiac event", CRITICAL),
        ("I think my father is having a heart attack", "possible cardiac event", CRITICAL),
        # breathing difficulty
        ("I can't breathe properly", "breathing difficulty", CRITICAL),
        ("I cannot breathe", "breathing difficulty", CRITICAL),
        ("She has difficulty breathing after the extraction", "breathing difficulty", CRITICAL),
        ("I feel short of breath", "breathing difficulty", CRITICAL),
        ("Shortness of breath since the injection", "breathing difficulty", CRITICAL),
        # possible stroke
        ("I think he is having a stroke", "possible stroke", CRITICAL),
        ("Her face droop started an hour ago", "possible stroke", CRITICAL),
        ("He has slurred speech", "possible stroke", CRITICAL),
        ("One side of my face feels numb", "possible stroke", CRITICAL),
        # heavy bleeding
        ("There is heavy bleeding from the socket", "heavy bleeding", CRITICAL),
        ("It is bleeding a lot after the extraction", "heavy bleeding", CRITICAL),
        ("My gum is bleeding heavily", "heavy bleeding", CRITICAL),
        ("The bleeding won't stop", "heavy bleeding", CRITICAL),
        ("There is blood everywhere", "heavy bleeding", CRITICAL),
        # self-harm risk
        ("I feel suicidal", "self-harm risk", CRITICAL),
        ("I want to kill myself", "self-harm risk", CRITICAL),
        ("I want to end my life", "self-harm risk", CRITICAL),
        ("I don't want to live anymore", "self-harm risk", CRITICAL),
        # severe allergic reaction
        (
            "I'm having a severe allergic reaction to the medicine",
            "severe allergic reaction",
            CRITICAL,
        ),
        ("I think this is anaphylaxis", "severe allergic reaction", CRITICAL),
        ("I feel my throat closing", "severe allergic reaction", CRITICAL),
        ("My throat swelling is getting worse", "severe allergic reaction", CRITICAL),
        # high fever
        ("My son has a high fever", "high fever", HIGH),
        ("I have a fever above 103", "high fever", HIGH),
        ("Fever over 104 since last night", "high fever", HIGH),
        ("Temperature is 104 degree", "high fever", HIGH),
        # fever reported
        ("I have a fever", "fever reported", HIGH),
        # bleeding reported
        ("My gums bleed when I brush", "bleeding reported", HIGH),
        ("There is some bleeding after the cleaning", "bleeding reported", HIGH),
    ],
)
def test_detect_emergency_patterns(message, reason, severity):
    result = detect_emergency(message)
    assert result.detected is True
    assert result.reason == reason
    assert result.severity == severity


def test_every_emergency_pattern_is_covered():
    covered = {
        "possible cardiac event",
        "breathing difficulty",
        "possible stroke",
        "heavy bleeding",
        "self-harm risk",
        "severe allergic reaction",
        "high fever",
        "fever reported",
        "bleeding reported",
    }
    assert {reason for _, reason, _ in EMERGENCY_PATTERNS} == covered


def test_detect_emergency_is_case_insensitive():
    result = detect_emergency("CHEST PAIN")
    assert result.detected is True
    assert result.reason == "possible cardiac event"


@pytest.mark.parametrize(
    "message",
    [
        "Can I book a cleaning on Friday?",
        "What time does the clinic open?",
        "How much is a consultation?",
        "Please reschedule my appointment to next week",
        "",
    ],
)
def test_detect_emergency_ordinary_messages(message):
    result = detect_emergency(message)
    assert result.detected is False
    assert result.severity is None
    assert result.reason == ""


@pytest.mark.parametrize(
    ("message", "reason", "severity"),
    [
        # "heavy bleeding" must hit the CRITICAL rule, not the later HIGH bleeding rule
        ("I have heavy bleeding", "heavy bleeding", CRITICAL),
        # "high fever" must hit its own rule, not the generic fever rule
        ("I have a high fever", "high fever", HIGH),
        # a CRITICAL rule wins over a HIGH rule in the same message
        ("I have a fever and chest pain", "possible cardiac event", CRITICAL),
    ],
)
def test_detect_emergency_rule_order(message, reason, severity):
    result = detect_emergency(message)
    assert result.reason == reason
    assert result.severity == severity


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("मेरे दांत में दर्द है", "hi"),
        ("ನನಗೆ ಹಲ್ಲು ನೋವು ಇದೆ", "kn"),
        ("எனக்கு பல் வலி இருக்கிறது", "ta"),
        ("నాకు పంటి నొప్పి ఉంది", "te"),
        ("എനിക്ക് പല്ലുവേദനയുണ്ട്", "ml"),
    ],
)
def test_detect_language_scripts(message, expected):
    assert detect_language(message) == expected


@pytest.mark.parametrize(
    ("message", "default", "expected"),
    [
        ("Can I book a cleaning on Friday?", "en", "en"),
        ("Can I book a cleaning on Friday?", "kn", "kn"),
        # two Devanagari characters is below the three-character threshold
        ("ok नम", "en", "en"),
        ("ok नम", "ta", "ta"),
        ("", "hi", "hi"),
    ],
)
def test_detect_language_falls_back_to_default(message, default, expected):
    assert detect_language(message, default=default) == expected


def test_detect_language_three_characters_is_enough():
    assert detect_language("ok नमस", default="en") == "hi"
