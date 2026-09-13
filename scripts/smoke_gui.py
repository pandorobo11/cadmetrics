from __future__ import annotations

import importlib.metadata
from importlib import resources
from typing import Any

from PySide6 import QtCore, QtWidgets

import cadmetrics.gui.pyside_app as pyside_app


class SmokeViewer(QtWidgets.QWidget):
    """Minimal viewer used to verify packaged GUI composition without starting VTK."""

    error = QtCore.Signal(str)
    message = QtCore.Signal(str)
    base_face_available = QtCore.Signal(bool)
    newly_exposed_surface_available = QtCore.Signal(bool)

    def set_options(self, options: Any) -> None:
        pass

    def set_request(self, request: Any) -> None:
        pass

    def set_model(self, model: Any) -> None:
        pass

    def set_result(
        self,
        row: Any,
        request: Any,
        *,
        align_camera: bool = False,
    ) -> None:
        pass

    def choose_and_save_image(self) -> None:
        pass


def main() -> None:
    versions = {
        name: importlib.metadata.version(name)
        for name in ("cadmetrics", "PySide6", "pyvista", "pyvistaqt")
    }
    entry_points = [
        entry
        for entry in importlib.metadata.distribution("cadmetrics").entry_points
        if entry.name == "cadmetrics-gui"
    ]
    if (
        len(entry_points) != 1
        or entry_points[0].group != "gui_scripts"
        or entry_points[0].load() is not pyside_app.main
    ):
        raise RuntimeError("Packaged GUI entry point is missing or incorrectly registered")
    docs = resources.files("cadmetrics").joinpath("_docs_site")
    for relative_path in ("index.html", "docs/gui.html", "docs/assets/gui-main.png"):
        if not docs.joinpath(relative_path).is_file():
            raise RuntimeError(f"Packaged documentation is missing: {relative_path}")

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    pyside_app.ModelViewer = SmokeViewer
    window = pyside_app.MainWindow()
    window.resize(800, 600)
    window.show()
    app.processEvents()

    if window.windowTitle() != "cadmetrics":
        raise RuntimeError("Packaged GUI window did not initialize correctly")

    window.close()
    app.processEvents()
    print(
        "GUI window smoke passed: "
        + ", ".join(f"{name}={version}" for name, version in versions.items())
    )


if __name__ == "__main__":
    main()
