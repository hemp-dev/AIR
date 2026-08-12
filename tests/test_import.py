from air import AIR_VERSION, Program


def test_package_import_smoke() -> None:
    assert AIR_VERSION == "0.1"
    assert Program.__name__ == "Program"
