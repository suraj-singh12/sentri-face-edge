from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout

from sentriface.api_server import SentriFaceApiServer


class ProductionLoggingTest(unittest.TestCase):
    def test_structured_events_never_retain_or_print_arrays(self) -> None:
        server = object.__new__(SentriFaceApiServer)
        server.events = []
        server.debug = True
        output = io.StringIO()

        with redirect_stdout(output):
            server.log_event(
                "inference",
                vector=[0.123456789, 0.987654321],
                nested={"landmarks": ((10.25, 11.75), (20.5, 21.5))},
                tensor=b"raw-tensor-data",
                faces=2,
            )

        event = server.events[0]
        self.assertEqual(event["vector"], "<sequence omitted; 2 items>")
        self.assertEqual(
            event["nested"]["landmarks"],
            "<sequence omitted; 2 items>",
        )
        self.assertEqual(event["tensor"], "<binary omitted; 15 bytes>")
        self.assertEqual(event["faces"], 2)
        serialized = output.getvalue()
        for sensitive_value in (
            "0.123456789",
            "0.987654321",
            "10.25",
            "11.75",
            "raw-tensor-data",
        ):
            self.assertNotIn(sensitive_value, serialized)


if __name__ == "__main__":
    unittest.main()
