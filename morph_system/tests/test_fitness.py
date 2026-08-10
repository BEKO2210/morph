import unittest

from morph.core.fitness import FitnessInputs, compute


class Fitness(unittest.TestCase):
    def test_quality_weights_are_not_silently_dropped(self):
        weights = {
            "tests": 0.32,
            "predator": 0.14,
            "guardian": 0.15,
            "minimality": 0.14,
            "dependency_stability": 0.10,
            "blast_radius": 0.08,
            "task_signal": 0.07,
        }
        bad = compute(FitnessInputs(
            tests_ratio=0.0, predator_score=0.0, guardian_score=0.0,
            minimality=1.0, dependency_stability=1.0, blast_radius=1.0, task_signal=1.0,
        ), weights)
        good = compute(FitnessInputs(
            tests_ratio=1.0, predator_score=1.0, guardian_score=1.0,
            minimality=1.0, dependency_stability=1.0, blast_radius=1.0, task_signal=1.0,
        ), weights)
        self.assertAlmostEqual(bad.score, 0.39, places=6)
        self.assertAlmostEqual(good.score, 1.0, places=6)
        self.assertAlmostEqual(bad.components["tests_ratio"], 0.0, places=6)
        self.assertAlmostEqual(good.components["tests_ratio"], 0.32, places=6)


if __name__ == "__main__":
    unittest.main()
