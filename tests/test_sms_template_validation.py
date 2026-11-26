import pytest

from services.alert_service import validate_sms_template


def test_sms_template_accepts_supported_fields():
    validate_sms_template(
        "Alert at {room_name} in {wing}, {floor}, at {timestamp}. "
        "Contact {school_name} at {school_hotline}."
    )


@pytest.mark.parametrize(
    "template",
    [
        "",
        "Alert at {unknown_field}.",
        "Alert at {room_name",
    ],
)
def test_sms_template_rejects_empty_unknown_or_malformed_fields(template):
    with pytest.raises(ValueError):
        validate_sms_template(template)
