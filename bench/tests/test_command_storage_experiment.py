"""An accepted proposal requires physical evaluation and separate confirmation."""
from __future__ import annotations

import copy
import unittest
from pathlib import Path
from unittest.mock import patch

from bench.gates.command_storage_experiment_gate import validate_experiment
from bench.lib.compute_program_uncertainty import candidate_verdict


class ExperimentAdmissionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.reference = {'path': '/retained', 'hash': '0' * 64}
        self.tail = {'developmentApplication': 'heat_diffusion',
                     'transferApplications': ['image_edges', 'holoscript_lif'],
                     'minimumWallMedianReduction': .05}
        rows = [{'application': app, 'metric': 'wallMs', 'summary': 'p50Ms',
                 'lowerRatio': .8, 'upperRatio': .9, 'maximumRegression': .05}
                for app in ['heat_diffusion', 'image_edges', 'holoscript_lif']
                for _ in ('baseline', 'candidate')]
        self.uncertainty = {'rows': rows, 'allIntervalsFinite': True}
        self.raw = [{'acceptancePassed': True}]
        self.decision = candidate_verdict(self.uncertainty, self.raw, self.tail,
                                          calibration_resolved=True)
        self.report = {'status': 'accepted-proposal', 'error': None,
                       'candidate': self.reference, 'calibration': self.reference,
                       'frozenInputs': self.reference, 'artifacts': [],
                       'series': [{'name': name, 'uncertainty': self.reference,
                                   'rawAcceptance': self.reference,
                                   'decision': copy.deepcopy(self.decision)}
                                  for name in ('evaluation', 'confirmation')]}

    def load(self, path: Path, schema: str) -> dict:
        values = {'command-storage-experiment.schema.json': self.report,
                  'compute-program-calibration.schema.json':
                  {'startupPolicy': 'startup', 'decisionPolicy': 'decision'},
                  'compute-program-startup-experiment.schema.json': {'tailExperimentPolicy': 'tail'},
                  'compute-program-tail-experiment.schema.json': self.tail,
                  'compute-program-decision.schema.json': {'cohorts': 4},
                  'compute-program-uncertainty.schema.json': self.uncertainty}
        return values[schema]

    def verify(self) -> dict:
        module = 'bench.gates.command_storage_experiment_gate'
        with (patch(f'{module}.load_policy', side_effect=self.load),
              patch(f'{module}.verify_references'),
              patch('pathlib.Path.read_text', return_value='[]'),
              patch(f'{module}.validate_calibration', return_value={
                  'policy': self.reference, 'promotionResolutionPassed': True}),
              patch(f'{module}.validate_candidate', return_value={
                  'baselineQualification': self.reference, 'candidateQualification': self.reference}),
              patch(f'{module}.load_qualification', return_value={'packages': [self.reference]}),
              patch(f'{module}.assess_series', return_value=(self.uncertainty, self.raw))):
            return validate_experiment(Path('/experiment/report.json'))

    def test_complete_evaluation_and_confirmation_can_produce_a_proposal(self) -> None:
        self.assertEqual(self.verify()['status'], 'accepted-proposal')

    def test_passing_evaluation_alone_cannot_be_accepted(self) -> None:
        self.report['series'].pop()
        with self.assertRaisesRegex(ValueError, 'confirmation'):
            self.verify()

    def test_relabelled_same_series_cannot_supply_confirmation(self) -> None:
        self.report['series'][1]['name'] = 'evaluation'
        with self.assertRaisesRegex(ValueError, 'series identity'):
            self.verify()

    def test_raw_regression_cannot_be_overruled_by_a_positive_interval(self) -> None:
        self.raw[0]['acceptancePassed'] = False
        with self.assertRaisesRegex(ValueError, 'physical evidence'):
            self.verify()


if __name__ == '__main__':
    unittest.main()
