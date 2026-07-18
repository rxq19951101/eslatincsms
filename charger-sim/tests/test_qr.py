from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from simulator.qr import QROptions, build_qr_payload, generate_connector_qr_png


class QRPayloadTests(unittest.TestCase):
    def test_server_token_uses_app_token_payload(self) -> None:
        self.assertEqual(build_qr_payload(qr_token="server_token_123"), "qr:server_token_123")

    def test_server_scan_url_is_rendered_verbatim(self) -> None:
        scan_url = "https://charge.example/scan/server-token"
        self.assertEqual(build_qr_payload(scan_url=scan_url), scan_url)

    def test_missing_server_input_explains_admin_preregistration(self) -> None:
        with self.assertRaisesRegex(ValueError, "Pre-register the charger in Admin"):
            build_qr_payload()

    def test_identity_cannot_be_used_as_a_qr_source(self) -> None:
        with self.assertRaisesRegex(ValueError, "server-assigned QR input"):
            generate_connector_qr_png(
                "CP-IDENTITY-ONLY",
                1,
                QROptions(out_dir=Path("unused")),
            )

    def test_generator_renders_only_server_token(self) -> None:
        image = Mock()
        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "simulator.qr.qrcode.make", return_value=image
        ) as make_qr:
            out = generate_connector_qr_png(
                "CP-OUTPUT-NAME",
                2,
                QROptions(out_dir=Path(temp_dir)),
                qr_token="assigned_by_server",
            )

        make_qr.assert_called_once_with("qr:assigned_by_server")
        image.save.assert_called_once_with(str(out))
        self.assertEqual(out.name, "CP-OUTPUT-NAME_connector_2.png")


if __name__ == "__main__":
    unittest.main()
