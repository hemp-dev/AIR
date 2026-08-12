import json

from air.bench.__main__ import main


def test_smoke_cli_writes_raw_and_aggregate_json(tmp_path) -> None:
    output_path = tmp_path / "smoke.json"

    assert (
        main(
            [
                "--suite",
                "smoke",
                "--variants",
                "NL,JSON,SJSON,AIR",
                "--scenario",
                "information-relay",
                "--output",
                str(output_path),
            ]
        )
        == 0
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["benchmark_version"] == "0.1"
    assert len(payload["results"]) == 4
    assert len(payload["aggregate"]["deltas"]) > 0
    assert all(item["success"] for item in payload["results"])
