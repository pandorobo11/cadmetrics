from __future__ import annotations

import csv
from pathlib import Path

import pytest
from rich.text import Text

from typer.testing import CliRunner

from cadmetrics.cli import app


DATA_DIR = Path(__file__).parent / "data"


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _csv_rows(output: str) -> list[dict[str, str]]:
    return list(csv.DictReader(output.splitlines()))


def test_measure_cli_stdout_uses_rich_table(runner: CliRunner) -> None:
    result = runner.invoke(app, ["measure", str(DATA_DIR / "unit_cube.stl")])

    assert result.exit_code == 0, result.output
    assert "surface_area" in result.output
    assert "volume" in result.output
    assert "stl-mesh" in result.output
    assert "projected_area" not in result.output


def test_measure_cli_out_still_writes_csv(runner: CliRunner, tmp_path: Path) -> None:
    output = tmp_path / "measure.csv"
    result = runner.invoke(
        app,
        ["measure", str(DATA_DIR / "unit_cube.stl"), "--out", str(output)],
    )

    assert result.exit_code == 0, result.output
    row = _csv_rows(output.read_text(encoding="utf-8"))[0]
    assert float(row["surface_area"]) == pytest.approx(6.0)
    assert float(row["base_area"]) == pytest.approx(1.0)
    assert float(row["base_tolerance"]) == pytest.approx(1.0e-6)
    assert float(row["volume"]) == pytest.approx(1.0)
    assert row["method"] == "stl-mesh"
    assert row["cadmetrics_version"]
    assert row["cadmetrics_hash"]


@pytest.mark.parametrize("command", ["measure", "project", "sweep"])
def test_cli_out_rejects_input_path_without_modifying_cad(
    runner: CliRunner,
    tmp_path: Path,
    command: str,
) -> None:
    source = tmp_path / "unit_cube.stl"
    original = (DATA_DIR / "unit_cube.stl").read_bytes()
    source.write_bytes(original)

    result = runner.invoke(app, [command, str(source), "--out", str(source)])

    assert result.exit_code == 1
    assert "must not overwrite an input CAD file" in result.output
    assert source.read_bytes() == original


def test_measure_cli_accepts_multiple_files_as_assembly(
    runner: CliRunner,
    tmp_path: Path,
) -> None:
    output = tmp_path / "assembly.csv"
    path = DATA_DIR / "unit_cube.stl"
    result = runner.invoke(
        app,
        ["measure", str(path), str(path), "--out", str(output)],
    )

    assert result.exit_code == 0, result.output
    row = _csv_rows(output.read_text(encoding="utf-8"))[0]
    assert row["volume"] == ""
    assert float(row["surface_area"]) == pytest.approx(12.0)
    assert row["method"] == "stl-mesh-assembly"


def test_project_cli_stdout_uses_rich_table(runner: CliRunner) -> None:
    result = runner.invoke(
        app,
        [
            "project",
            str(DATA_DIR / "unit_cube.stl"),
            "--attitude",
            "alpha-beta",
            "--alpha",
            "60",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "projected_area" in result.output
    assert "direction_x" in result.output
    assert "centroid_x" in result.output
    assert "stl-mesh-projection" in result.output


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (
            ["--attitude", "alpha-beta", "--alpha", "60", "--beta", "0"],
            {"alpha_deg": 60.0, "beta_deg": 0.0, "direction_x": 0.5},
        ),
        (
            ["--attitude", "roll-pitch", "--roll", "90", "--pitch", "90"],
            {"roll_deg": 90.0, "pitch_deg": 90.0, "direction_y": -1.0},
        ),
        (
            ["--attitude", "vector", "--direction", "0,1,0"],
            {"direction_y": 1.0, "beta_deg": -90.0},
        ),
    ],
)
def test_project_cli_attitude_modes_reach_the_result(
    runner: CliRunner, tmp_path: Path, args: list[str], expected: dict[str, float]
) -> None:
    output = tmp_path / "attitude.csv"
    result = runner.invoke(
        app, ["project", str(DATA_DIR / "unit_cube.stl"), *args, "--out", str(output)]
    )

    assert result.exit_code == 0, result.output
    row = _csv_rows(output.read_text(encoding="utf-8"))[0]
    for column, value in expected.items():
        assert float(row[column]) == pytest.approx(value)


def test_project_cli_accepts_axis_map(runner: CliRunner, tmp_path: Path) -> None:
    output = tmp_path / "axis_map.csv"
    result = runner.invoke(
        app,
        [
            "project",
            str(DATA_DIR / "unit_cube.stl"),
            "--axis-map=-x,y,z",
            "--out",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    row = _csv_rows(output.read_text(encoding="utf-8"))[0]
    assert float(row["centroid_x"]) == pytest.approx(-0.5)
    assert float(row["centroid_y"]) == pytest.approx(0.5)
    assert float(row["centroid_z"]) == pytest.approx(0.5)
    assert float(row["x_min"]) == pytest.approx(-1.0)
    assert float(row["x_max"]) == pytest.approx(0.0)
    assert float(row["base_area"]) == pytest.approx(1.0)


def test_sweep_cli_accepts_roll_pitch_ranges(runner: CliRunner, tmp_path: Path) -> None:
    output = tmp_path / "roll_pitch.csv"
    result = runner.invoke(
        app,
        [
            "sweep",
            str(DATA_DIR / "unit_cube.stl"),
            "--attitude",
            "roll-pitch",
            "--roll",
            "0:90:90",
            "--pitch",
            "90",
            "--out",
            str(output),
            "--no-summary",
        ],
    )

    assert result.exit_code == 0, result.output
    rows = list(csv.DictReader(output.read_text(encoding="utf-8").splitlines()))
    assert len(rows) == 2
    assert [float(row["roll_deg"]) for row in rows] == pytest.approx([0.0, 90.0])
    assert [float(row["pitch_deg"]) for row in rows] == pytest.approx([90.0, 90.0])


def test_sweep_cli_vector_mode_returns_one_row(runner: CliRunner) -> None:
    result = runner.invoke(
        app,
        [
            "sweep",
            str(DATA_DIR / "unit_cube.stl"),
            "--attitude",
            "vector",
            "--direction",
            "1,0,0",
            "--alpha",
            "0e0",
            "--no-summary",
        ],
    )

    assert result.exit_code == 0, result.output
    rows = _csv_rows(result.output)
    assert len(rows) == 1
    assert float(rows[0]["direction_x"]) == pytest.approx(1.0)


@pytest.mark.parametrize(
    ("command", "arguments", "message"),
    [
        ("project", ["--alpha", "nan"], "alpha_deg must be finite"),
        ("sweep", ["--alpha", "bad"], "could not convert"),
    ],
)
def test_cli_reports_preflight_attitude_validation_errors(
    runner: CliRunner,
    command: str,
    arguments: list[str],
    message: str,
) -> None:
    result = runner.invoke(
        app,
        [command, str(DATA_DIR / "unit_cube.stl"), *arguments],
    )

    assert result.exit_code != 0
    assert message in result.output


def test_cli_error_preserves_optional_extra_markup(
    runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_measure(*args, **kwargs):
        raise RuntimeError("STEP support requires cadmetrics[step].")

    monkeypatch.setattr("cadmetrics.cli.measure_api", fail_measure)
    result = runner.invoke(app, ["measure", str(DATA_DIR / "unit_cube.stl")])

    assert result.exit_code == 1
    assert "cadmetrics[step]" in result.output


@pytest.mark.parametrize(
    ("attitude_args", "message"),
    [
        (["--attitude", "roll-pitch", "--alpha", "10", "--pitch", "5"], "--alpha cannot be used"),
        (["--attitude", "alpha-beta", "--alpha", "10", "--roll", "5"], "--roll cannot be used"),
    ],
)
def test_cli_rejects_mixed_attitude_inputs(
    runner: CliRunner, attitude_args: list[str], message: str
) -> None:
    result = runner.invoke(app, ["project", str(DATA_DIR / "unit_cube.stl"), *attitude_args])

    assert result.exit_code != 0
    assert message in Text.from_ansi(result.output).plain


@pytest.mark.parametrize(
    ("options", "expected_factor", "expected_angle"),
    [
        (["--mesh-deflection", "auto-precise"], 1.0e-4, 0.1),
    ],
)
def test_project_cli_mesh_presets(
    runner: CliRunner,
    tmp_path: Path,
    options: list[str],
    expected_factor: float,
    expected_angle: float,
) -> None:
    pytest.importorskip("OCP")
    output = tmp_path / "preset.csv"
    sample = Path(__file__).parents[1] / "samples" / "box_1x2x3" / "box_1x2x3.step"
    result = runner.invoke(app, ["project", str(sample), *options, "--out", str(output)])

    assert result.exit_code == 0, result.output
    row = _csv_rows(output.read_text(encoding="utf-8"))[0]
    assert float(row["mesh_deflection"]) == pytest.approx(14.0**0.5 * expected_factor)
    assert float(row["angular_deflection"]) == pytest.approx(expected_angle)


def test_samples_cli_path_prints_sample_directory(runner: CliRunner) -> None:
    result = runner.invoke(app, ["samples", "--path"])

    assert result.exit_code == 0
    directory = Path(result.output.strip())
    assert (directory / "metadata.json").is_file()
    assert (directory / "unit_cube" / "unit_cube.step").is_file()


def test_samples_cli_lists_sample_files(runner: CliRunner) -> None:
    result = runner.invoke(app, ["samples"])

    assert result.exit_code == 0
    assert "satellite/satellite.step" in result.output
    assert "unit_cube/unit_cube_binary.stl" in result.output
