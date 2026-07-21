from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import numpy as np
from PySide6 import QtCore, QtWidgets

from cadmetrics.gui.gui_formatters import overlay_text
from cadmetrics.gui.gui_types import ViewerOptions
from cadmetrics.gui.jobs import CalculationRequest
from cadmetrics.gui.viewer_geometry import (
    base_face_polydata,
    camera_geometry,
    newly_exposed_surface_polydata,
    projection_arrow_geometry,
    projection_camera_geometry,
    row_centroid_point,
)
from cadmetrics.orientation import Orientation, parse_vector, projection_direction_for_orientation
from cadmetrics.types import MeasurementRow, ModelData

PlotterFactory = Callable[[QtWidgets.QWidget], Any]


class ModelViewer(QtWidgets.QWidget):
    error = QtCore.Signal(str)
    message = QtCore.Signal(str)
    base_face_available = QtCore.Signal(bool)
    newly_exposed_surface_available = QtCore.Signal(bool)

    def __init__(
        self,
        parent: QtWidgets.QWidget | None = None,
        *,
        plotter_factory: PlotterFactory | None = None,
    ) -> None:
        super().__init__(parent)
        self._model: ModelData | None = None
        self._request: CalculationRequest | None = None
        self._row: MeasurementRow | None = None
        self._options = ViewerOptions()
        self._plotter: Any | None = None
        self._mesh_actor: Any | None = None
        self._mesh_polydata: Any | None = None
        self._feature_edges_actor: Any | None = None
        self._base_face_actor: Any | None = None
        self._base_face_polydata: Any | None = None
        self._newly_exposed_surface_actor: Any | None = None
        self._newly_exposed_surface_polydata: Any | None = None
        self._vector_actor: Any | None = None
        self._centroid_actor: Any | None = None
        self._overlay_actor: Any | None = None
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        widget = self._create_plotter(plotter_factory)
        layout.addWidget(widget)

    @property
    def available(self) -> bool:
        return self._plotter is not None

    def set_model(self, model: ModelData) -> None:
        self._model = model
        self._row = None
        if self._plotter is None:
            return
        import pyvista as pv

        faces = np.column_stack(
            [np.full(model.faces.shape[0], 3, dtype=np.int64), model.faces]
        ).ravel()
        self._mesh_polydata = pv.PolyData(model.vertices, faces)
        self._plotter.clear()
        self._reset_actors()
        self._base_face_polydata = base_face_polydata(model, pv)
        self.base_face_available.emit(self._base_face_polydata is not None)
        self._newly_exposed_surface_polydata = newly_exposed_surface_polydata(model, pv)
        self.newly_exposed_surface_available.emit(self._newly_exposed_surface_polydata is not None)
        self._configure_lighting()
        self._plotter.add_axes()
        self._plotter.show_grid()
        self._mesh_actor = self._plotter.add_mesh(
            self._mesh_polydata,
            color="#9fc8ef",
            show_edges=self._options.mesh_edges,
            edge_color="#111111",
            opacity=self._shape_opacity(),
            smooth_shading=True,
            split_sharp_edges=True,
            ambient=0.35,
            diffuse=0.72,
            specular=0.18,
            specular_power=24,
        )
        self._apply_mesh_shading()
        self._update_feature_edges(render=False)
        self._update_base_face(render=False)
        self._update_newly_exposed_surface(render=False)
        self.set_camera(self._options.camera_direction)
        self._update_projection()

    def set_request(self, request: CalculationRequest | None) -> None:
        self._request = request
        if self._model is not None:
            self._update_projection()

    def set_result(
        self,
        row: MeasurementRow | None,
        request: CalculationRequest | None,
        *,
        align_camera: bool = False,
    ) -> None:
        self._row = row
        self._request = request
        self._update_projection(align_camera=align_camera)

    def set_options(self, options: ViewerOptions) -> None:
        camera_changed = options.camera_direction != self._options.camera_direction
        self._options = options
        self._apply_display_options()
        self._update_base_face(render=False)
        self._update_newly_exposed_surface(render=False)
        self._update_projection()
        if camera_changed:
            self.set_camera(options.camera_direction)

    def set_camera(self, direction: tuple[float, float, float]) -> None:
        if self._plotter is None or self._model is None or self._model.vertex_count == 0:
            return
        position, focal_point, view_up = camera_geometry(
            self._model.vertices, np.asarray(direction, dtype=float)
        )
        self._set_camera(position, focal_point, view_up)
        self._plotter.render()

    def save_image(self, path: str | Path) -> Path:
        if self._plotter is None:
            raise RuntimeError("3D viewer is not available.")
        output = Path(path)
        if not output.suffix:
            output = output.with_suffix(".png")
        self._plotter.screenshot(str(output))
        return output

    def choose_and_save_image(self) -> None:
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save View Image", "cadmetrics_view.png", "PNG Images (*.png);;All Files (*)"
        )
        if not path:
            return
        try:
            output = self.save_image(path)
        except Exception as exc:
            self.error.emit(str(exc))
            return
        self.message.emit(f"Saved image: {output}")

    def _create_plotter(self, factory: PlotterFactory | None) -> QtWidgets.QWidget:
        if factory is None:
            try:
                from pyvistaqt import QtInteractor
            except ImportError:
                placeholder = QtWidgets.QTextEdit()
                placeholder.setReadOnly(True)
                placeholder.setText(
                    "3D viewer dependencies are not installed.\nRun: uv sync --extra gui"
                )
                return placeholder
            factory = QtInteractor
        self._plotter = factory(self)
        self._plotter.set_background("white")
        self._configure_lighting()
        self._plotter.add_axes()
        self._plotter.show_grid()
        self._plotter.enable_parallel_projection()
        return self._plotter

    def _reset_actors(self) -> None:
        self._mesh_actor = None
        self._feature_edges_actor = None
        self._base_face_actor = None
        self._newly_exposed_surface_actor = None
        self._vector_actor = None
        self._centroid_actor = None
        self._overlay_actor = None

    def _configure_lighting(self) -> None:
        if self._plotter is None:
            return
        try:
            self._plotter.remove_all_lights()
            import pyvista as pv

            for light in (
                pv.Light(
                    position=(2.5, -3.0, 4.0),
                    focal_point=(0.0, 0.0, 0.0),
                    intensity=1.1,
                    positional=False,
                ),
                pv.Light(
                    position=(-3.0, 2.5, 2.0),
                    focal_point=(0.0, 0.0, 0.0),
                    intensity=0.65,
                    positional=False,
                ),
                pv.Light(light_type="headlight", intensity=0.35),
            ):
                self._plotter.add_light(light)
        except Exception:
            try:
                self._plotter.enable_lightkit()
            except Exception:
                pass

    def _shape_opacity(self) -> float:
        return 0.45 if self._options.transparent_shape else 1.0

    def _apply_display_options(self) -> None:
        if self._plotter is None or self._mesh_actor is None:
            return
        try:
            prop = self._mesh_actor.GetProperty()
        except AttributeError:
            prop = self._mesh_actor.prop
        prop.SetOpacity(self._shape_opacity())
        prop.SetEdgeVisibility(1 if self._options.mesh_edges else 0)
        prop.SetEdgeColor(0.07, 0.07, 0.07)
        self._apply_mesh_shading(prop)
        self._update_feature_edges(render=False)

    def _apply_mesh_shading(self, prop: Any | None = None) -> None:
        if self._mesh_actor is None:
            return
        if prop is None:
            try:
                prop = self._mesh_actor.GetProperty()
            except AttributeError:
                prop = self._mesh_actor.prop
        try:
            prop.SetInterpolationToPhong()
            prop.SetAmbient(0.35)
            prop.SetDiffuse(0.72)
            prop.SetSpecular(0.18)
            prop.SetSpecularPower(24)
        except AttributeError:
            pass

    def _update_feature_edges(self, *, render: bool) -> None:
        if self._plotter is None:
            return
        self._remove_actor("_feature_edges_actor")
        if self._mesh_polydata is None or not self._options.feature_edges:
            if render:
                self._plotter.render()
            return
        try:
            edges = self._mesh_polydata.extract_feature_edges(
                feature_angle=35.0,
                boundary_edges=True,
                feature_edges=True,
                manifold_edges=False,
                non_manifold_edges=True,
            )
        except Exception:
            return
        if edges.n_cells > 0:
            self._feature_edges_actor = self._plotter.add_mesh(
                edges,
                color="#1d2730",
                line_width=2.5,
                render_lines_as_tubes=True,
                opacity=0.9,
                pickable=False,
            )
        if render:
            self._plotter.render()

    def _update_base_face(self, *, render: bool) -> None:
        if self._plotter is None:
            return
        self._remove_actor("_base_face_actor")
        if self._base_face_polydata is not None and self._options.show_base_face:
            self._base_face_actor = self._plotter.add_mesh(
                self._base_face_polydata,
                color="#ffd400",
                opacity=1.0,
                smooth_shading=False,
                ambient=0.75,
                diffuse=0.25,
            )
        if render:
            self._plotter.render()

    def _update_newly_exposed_surface(self, *, render: bool) -> None:
        if self._plotter is None:
            return
        self._remove_actor("_newly_exposed_surface_actor")
        if (
            self._newly_exposed_surface_polydata is not None
            and self._options.show_newly_exposed_surface
        ):
            self._newly_exposed_surface_actor = self._plotter.add_mesh(
                self._newly_exposed_surface_polydata,
                color="#ff7a00",
                opacity=1.0,
                smooth_shading=False,
                ambient=0.75,
                diffuse=0.25,
                pickable=False,
            )
        if render:
            self._plotter.render()

    def _update_projection(self, *, align_camera: bool = False) -> None:
        if self._plotter is None or self._model is None or self._model.vertex_count == 0:
            return
        direction = self._projection_direction()
        self._remove_actor("_vector_actor")
        if self._options.show_projection_arrow:
            start, vector = projection_arrow_geometry(
                self._model.vertices,
                direction,
                through_point=row_centroid_point(self._row),
            )
            self._vector_actor = self._plotter.add_arrows(
                start.reshape(1, 3), vector.reshape(1, 3), color="#d04a02"
            )
        self._update_centroid()
        if align_camera:
            position, focal_point, view_up = projection_camera_geometry(
                self._model.vertices, direction
            )
            self._set_camera(position, focal_point, view_up)
        self._update_overlay()
        self._plotter.render()

    def _projection_direction(self) -> np.ndarray:
        if self._row is not None and self._row.direction_x is not None:
            return np.array(
                [self._row.direction_x, self._row.direction_y, self._row.direction_z], dtype=float
            )
        request = self._request
        if request is None:
            return np.array([1.0, 0.0, 0.0], dtype=float)
        if request.attitude_mode == "vector":
            return parse_vector(f"{request.vector_x},{request.vector_y},{request.vector_z}")
        if request.attitude_mode == "roll_pitch":
            orientation = Orientation(
                roll_deg=request.roll_start,
                alpha_deg=request.pitch_start,
                beta_deg=0.0,
            )
        else:
            orientation = Orientation(
                roll_deg=0.0,
                alpha_deg=request.alpha_start,
                beta_deg=request.beta_start,
            )
        return projection_direction_for_orientation(orientation)

    def _update_centroid(self) -> None:
        if self._plotter is None:
            return
        self._remove_actor("_centroid_actor")
        point = row_centroid_point(self._row)
        if point is None or self._model is None:
            return
        import pyvista as pv

        radius = max(float(np.ptp(self._model.vertices, axis=0).max()) * 0.025, 1.0e-6)
        marker = pv.Sphere(
            radius=radius, center=tuple(point), theta_resolution=24, phi_resolution=12
        )
        self._centroid_actor = self._plotter.add_mesh(
            marker, color="#ffd400", edge_color="#111111", show_edges=True
        )

    def _update_overlay(self) -> None:
        if self._plotter is None:
            return
        self._remove_actor("_overlay_actor")
        if not self._options.show_overlay:
            return
        text = overlay_text(
            self._row,
            model=self._model,
            request=self._request,
            detailed=self._options.detailed_overlay,
        )
        if text:
            self._overlay_actor = self._plotter.add_text(
                text,
                position="upper_left",
                font_size=9,
                color="#1f2933",
                shadow=False,
            )

    def _set_camera(
        self, position: np.ndarray, focal_point: np.ndarray, view_up: np.ndarray
    ) -> None:
        if self._plotter is None:
            return
        self._plotter.reset_camera()
        self._plotter.camera_position = (tuple(position), tuple(focal_point), tuple(view_up))
        self._plotter.enable_parallel_projection()
        try:
            self._plotter.reset_camera_clipping_range()
        except AttributeError:
            pass

    def _remove_actor(self, attribute: str) -> None:
        if self._plotter is None:
            return
        actor = getattr(self, attribute)
        if actor is not None:
            try:
                self._plotter.remove_actor(actor)
            except Exception:
                pass
            setattr(self, attribute, None)
