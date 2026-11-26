from services.adapters import sms_real
from services.adapters.sms_real import (
    Sim800SmsService,
    _encode_submit_pdu,
    _ucs2_parts,
)


def test_ucs2_message_is_split_on_character_boundaries():
    parts = _ucs2_parts(("A" * 65) + "😀" + ("B" * 5))

    assert len(parts) == 2
    assert parts[0].decode("utf-16-be") == ("A" * 65) + "😀"
    assert parts[1].decode("utf-16-be") == "B" * 5


def test_multipart_pdu_contains_concatenation_header_and_correct_tpdu_length():
    pdu, tpdu_length = _encode_submit_pdu(
        "+639171234567",
        "A".encode("utf-16-be") * 67,
        part_number=1,
        part_count=2,
        reference=0x42,
    )
    encoded = bytes.fromhex(pdu)

    assert encoded[:14] == bytes.fromhex("0041000C9136191732547600088C")
    assert encoded[14:20] == bytes.fromhex("050003420201")
    assert len(encoded) - 1 == tpdu_length


def test_send_sms_submits_every_pdu_part(monkeypatch):
    class FakeSerial:
        is_open = True

        def __init__(self):
            self.writes = []
            self.responses = []

        def write(self, data):
            self.writes.append(data)
            if data.startswith(b"AT+CMGS="):
                self.responses.append(b"\r\n> ")
            elif data.endswith(b"\x1a"):
                self.responses.append(b"\r\n+CMGS: 1\r\nOK\r\n")

        def readline(self):
            if self.responses:
                return self.responses.pop(0)
            return b""

    connection = FakeSerial()
    service = Sim800SmsService("COM4")
    service._serial = connection
    monkeypatch.setattr(sms_real.time, "sleep", lambda _seconds: None)

    result = service.send_sms("+639171234567", "A" * 71)

    commands = [write for write in connection.writes if write.startswith(b"AT+CMGS=")]
    payloads = [write for write in connection.writes if write.endswith(b"\x1a")]
    assert result.success is True
    assert len(commands) == 2
    assert len(payloads) == 2
    assert all(payload.startswith(b"0041") for payload in payloads)
