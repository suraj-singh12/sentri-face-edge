from __future__ import annotations

import unittest
from types import SimpleNamespace

from sentriface.components.onnx_components import validate_onnx_runtime_pair
from sentriface.errors import ModelSetupError


class _Session:
    def __init__(self, outputs, providers=("CPUExecutionProvider",)) -> None:
        self._outputs = [SimpleNamespace(shape=shape) for shape in outputs]
        self._providers = list(providers)

    def get_outputs(self):
        return self._outputs

    def get_providers(self):
        return self._providers


def _component(input_shape, outputs, providers=("CPUExecutionProvider",)):
    return SimpleNamespace(
        runtime=SimpleNamespace(
            input_shape=input_shape,
            session=_Session(outputs, providers),
        )
    )


class OnnxCompatibilityTest(unittest.TestCase):
    def test_supported_detector_and_recognizer_contracts_are_bounded(self) -> None:
        detector = _component([1, 3, 640, 640], [[1, 100, 4]] * 9)
        recognizer = _component([1, 3, 112, 112], [[1, 512]])
        facts = validate_onnx_runtime_pair(
            detector, recognizer, expected_embedding_dimension=512,
        )
        self.assertEqual(facts["embedding_dimension"], 512)
        self.assertEqual(facts["provider"], "CPUExecutionProvider")

    def test_wrong_embedding_detector_or_provider_contract_refuses(self) -> None:
        valid_detector = _component([1, 3, 640, 640], [[1, 100, 4]] * 9)
        with self.assertRaisesRegex(ModelSetupError, "512-dimensional"):
            validate_onnx_runtime_pair(
                valid_detector,
                _component([1, 3, 112, 112], [[1, 256]]),
                expected_embedding_dimension=512,
            )
        with self.assertRaisesRegex(ModelSetupError, "SCRFD"):
            validate_onnx_runtime_pair(
                _component([1, 3, 640, 640], [[1, 2, 4]]),
                _component([1, 3, 112, 112], [[1, 512]]),
                expected_embedding_dimension=512,
            )
        with self.assertRaisesRegex(ModelSetupError, "CPUExecutionProvider"):
            validate_onnx_runtime_pair(
                valid_detector,
                _component([1, 3, 112, 112], [[1, 512]], providers=("Other",)),
                expected_embedding_dimension=512,
            )


if __name__ == "__main__":
    unittest.main()
