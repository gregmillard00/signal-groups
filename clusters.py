"""The five clusters the game groups clips into.

inter1 returns 10 social signals (plus engagement/disengagement, which we ignore -
they describe attention, not the affective read the game is about). Those 10 signals
partition exactly onto the five groups named in the ticket, which is what makes this
work as a Connections board: every signal belongs to one and only one group.
"""

CLUSTERS = [
    {
        "id": "agreement_interest",
        "name": "Agreement & Interest",
        "signals": ["agreement", "interest"],
        "blurb": "Leaning in. Alignment with the other person, or genuine curiosity about what they are saying.",
        "color": "#28c840",
        "tint": "#dff7e3",
    },
    {
        "id": "confidence",
        "name": "Confidence",
        "signals": ["confidence"],
        "blurb": "Saying it straight. Clear conviction, no hedging, no qualifiers.",
        "color": "#ffbb33",
        "tint": "#fff1d6",
    },
    {
        "id": "hesitation_uncertainty",
        "name": "Hesitation & Uncertainty",
        "signals": ["hesitation", "uncertainty"],
        "blurb": "Not committing. Stalling before an answer, or low confidence in one's own judgment.",
        "color": "#2f96e0",
        "tint": "#ddeefb",
    },
    {
        "id": "frustration_disagreement",
        "name": "Frustration & Disagreement",
        "signals": ["frustration", "disagreement"],
        "blurb": "Pushing back. Blocked progress, or active divergence from what was just said.",
        "color": "#ff5f57",
        "tint": "#ffe3e1",
    },
    {
        "id": "skepticism_stress_confusion",
        "name": "Skepticism, Stress & Confusion",
        "signals": ["skepticism", "stress", "confusion"],
        "blurb": "Something is not landing. Doubt about a claim, pressure in the moment, or a gap in understanding.",
        "color": "#e84393",
        "tint": "#fce5f1",
    },
]

BY_ID = {c["id"]: c for c in CLUSTERS}

SIGNAL_TO_CLUSTER = {
    sig: c["id"] for c in CLUSTERS for sig in c["signals"]
}

# Reported by inter1 but deliberately not part of the game: these describe how much
# attention someone is paying, which cuts across all five affective groups.
IGNORED_SIGNALS = {"engagement", "disengagement"}

PROBABILITY_WEIGHT = {"high": 3.0, "medium": 1.8, "low": 0.8, None: 1.0}
