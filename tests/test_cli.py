from __future__ import annotations

import csv
from pathlib import Path

import pytest
import typer

from cadmetrics.cli import _resolve_project_attitude
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
    assert float(row["volume"]) == pytest.approx(1.0)
    assert row["method"] == "stl-mesh"


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
    assert float(row["volume"]) == pytest.approx(2.0)
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


def test_project_cli_accepts_alpha_beta_mode(runner: CliRunner, tmp_path: Path) -> None:
    output = tmp_path / "alpha_beta.csv"
    result = runner.invoke(
        app,
        [
            "project",
            str(DATA_DIR / "unit_cube.stl"),
            "--attitude",
            "alpha-beta",
            "--alpha",
            "60",
            "--beta",
            "0",
            "--out",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    row = _csv_rows(output.read_text(encoding="utf-8"))[0]
    assert float(row["alpha_deg"]) == pytest.approx(60.0)
    assert float(row["beta_deg"]) == pytest.approx(0.0)
    assert float(row["direction_x"]) == pytest.approx(0.5)
    assert float(row["direction_z"]) == pytest.approx(0.8660254037844386)


def test_project_cli_accepts_roll_pitch_mode(runner: CliRunner, tmp_path: Path) -> None:
    output = tmp_path / "roll_pitch.csv"
    result = runner.invoke(
        app,
        [
            "project",
            str(DATA_DIR / "unit_cube.stl"),
            "--attitude",
            "roll-pitch",
            "--roll",
            "90",
            "--pitch",
            "90",
            "--out",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    row = _csv_rows(output.read_text(encoding="utf-8"))[0]
    assert float(row["roll_deg"]) == pytest.approx(90.0)
    assert float(row["pitch_deg"]) == pytest.approx(90.0)
    assert float(row["direction_y"]) == pytest.approx(-1.0)


def test_project_cli_accepts_vector_mode(runner: CliRunner, tmp_path: Path) -> None:
    output = tmp_path / "vector.csv"
    result = runner.invoke(
        app,
        [
            "project",
            str(DATA_DIR / "unit_cube.stl"),
            "--attitude",
            "vector",
            "--direction",
            "0,1,0",
            "--out",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    row = _csv_rows(output.read_text(encoding="utf-8"))[0]
    assert float(row["direction_x"]) == pytest.approx(0.0)
    assert float(row["direction_y"]) == pytest.approx(1.0)
    assert float(row["direction_z"]) == pytest.approx(0.0)
    assert float(row["beta_deg"]) == pytest.approx(-90.0)


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
            "--no-summary",
        ],
    )

    assert result.exit_code == 0, result.output
    rows = _csv_rows(result.output)
    assert len(rows) == 1
    assert float(rows[0]["direction_x"]) == pytest.approx(1.0)


def test_cli_rejects_mixed_attitude_inputs(runner: CliRunner) -> None:
    result = runner.invoke(
        app,
        [
            "project",
            str(DATA_DIR / "unit_cube.stl"),
            "--attitude",
            "roll-pitch",
            "--alpha",
            "10",
            "--pitch",
            "5",
        ],
    )

    assert result.exit_code != 0
    with pytest.raises(typer.BadParameter, match="--alpha cannot be used"):
        _resolve_project_attitude(
            attitude="roll-pitch",
            alpha=10.0,
            beta=0.0,
            roll=0.0,
            pitch=5.0,
            direction=None,
        )


def test_cli_rejects_roll_in_alpha_beta_mode(runner: CliRunner) -> None:
    result = runner.invoke(
        app,
        [
            "project",
            str(DATA_DIR / "unit_cube.stl"),
            "--attitude",
            "alpha-beta",
            "--alpha",
            "10",
            "--roll",
            "5",
        ],
    )

    assert result.exit_code != 0
    with pytest.raises(typer.BadParameter, match="--roll cannot be used"):
        _resolve_project_attitude(
            attitude="alpha-beta",
            alpha=10.0,
            beta=0.0,
            roll=5.0,
            pitch=None,
            direction=None,
        )
