
from dataclasses import dataclass
from typing import Dict

CRITERIA = {
    "technical_accuracy": 35,
    "problem_solving": 25,
    "presentation": 20,
    "originality": 10,
    "documentation": 10,
}


@dataclass
class Evaluation:
    participant_id: int
    technical_accuracy: int
    problem_solving: int
    presentation: int
    originality: int
    documentation: int

    def calculate_total(self) -> int:
        scores = {
            key: getattr(self, key)
            for key in CRITERIA
        }

        for category, score in scores.items():
            maximum = CRITERIA[category]

            if not isinstance(score, int) or isinstance(score, bool):
                raise ValueError(
                    f"{category} must be an integer"
                )

            if not 0 <= score <= maximum:
                raise ValueError(
                    f"{category} must be between 0 and {maximum}"
                )

        return sum(scores.values())

    def as_dict(self) -> Dict:
        return {
            "participant_id": self.participant_id,
            "total_score": self.calculate_total(),
            "scores": {
                key: getattr(self, key)
                for key in CRITERIA
            }
        }


def rank_submissions(evaluations):
    results = [entry.as_dict() for entry in evaluations]

    return sorted(
        results,
        key=lambda entry: (
            -entry["total_score"],
            entry["participant_id"]
        )
    )


if __name__ == "__main__":
    demo_evaluations = [
        Evaluation(
            participant_id=1,
            technical_accuracy=32,
            problem_solving=23,
            presentation=18,
            originality=9,
            documentation=10
        ),
        Evaluation(
            participant_id=2,
            technical_accuracy=30,
            problem_solving=21,
            presentation=17,
            originality=8,
            documentation=9
        )
    ]

    print("BRIDGELAB EVALUATION ENGINE")
    print("=" * 40)

    for position, result in enumerate(
        rank_submissions(demo_evaluations), start=1
    ):
        print(
            f"Rank {position}: "
            f"Participant {result['participant_id']} - "
            f"{result['total_score']}/100"
        )
