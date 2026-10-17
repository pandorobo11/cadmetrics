from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

from cadmetrics.gui.gui_formatters import overlay_text
from cadmetrics.gui.gui_types import ViewerOptions
from cadmetrics.gui.jobs import CalculationRequest
from cadmetrics.gui.viewer_geometry import (
    base_face_polydata,
    camera_geometry,
    fit_overlay_text,
    newly_exposed_surface_polydata,
    overlay_reserved_fraction,
    projection_arrow_geometry,
    projection_camera_geometry,
    row_centroid_point,
)
from cadmetrics.orientation import Orientation, parse_vector, projection_direction_for_orientation
from cadmetrics.types import MeasurementRow, ModelData

PlotterFactory = Callable[[QtWidgets.QWidget], Any]

# (button label, tooltip, direction the camera looks from)
CAMERA_VIEWS: tuple[tuple[str, str, tuple[float, float, float]], ...] = (
    ("+X", "View from +X", (1.0, 0.0, 0.0)),
    ("-X", "View from -X", (-1.0, 0.0, 0.0)),
    ("+Y", "View from +Y", (0.0, 1.0, 0.0)),
    ("-Y", "View from -Y", (0.0, -1.0, 0.0)),
    ("+Z", "View from +Z", (0.0, 0.0, 1.0)),
    ("-Z", "View from -Z", (0.0, 0.0, -1.0)),
    ("ISO", "Isometric view from -X -Y +Z", (-1.0, -1.0, 1.0)),
    ("ISO↓", "Isometric view from below (+X +Y -Z)", (1.0, 1.0, -1.0)),
)
DEFAULT_CAMERA_DIRECTION = (-1.0, -1.0, 1.0)
# Keep the orientation triad in the lower-right corner, away from the upper-left overlay.
AXES_VIEWPORT = (0.82, 0.0, 1.0, 0.18)

EMPTY_STATE_TEXT = (
    "Open an STL or STEP file to begin\nChoose a file on the left or drag and drop it here"
)

# Text sizes are logical pixels so the overlay, grid labels, and empty-state hint keep
# their size relative to the Qt UI on HiDPI screens.
OVERLAY_FONT_SIZE = 12
EMPTY_STATE_FONT_SIZE = 15
GRID_LABEL_FONT_SIZE = 12
OVERLAY_MARGIN = 10
# Approximate advance of a proportional UI font relative to its pixel size.
_CHARACTER_WIDTH_RATIO = 0.56
# The overlay never claims more than this share of the view width.
_OVERLAY_MAX_WIDTH_FRACTION = 0.42
_TEXT_COLOR = "#1f2933"
_MUTED_TEXT_COLOR = "#52606d"
_PANEL_COLOR = "#ffffff"
_PANEL_BORDER_COLOR = "#cfd8e1"
_UI_FONT_CANDIDATES = {
    "darwin": (
        "/System/Library/Fonts/SFNS.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ),
    "win32": ("C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf"),
    "linux": (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
    ),
}


def _ui_font_file() -> str | None:
    """Return a system UI font close to Qt's, or None to use VTK's built-in Arial."""
    for candidate in _UI_FONT_CANDIDATES.get(sys.platform, ()):
        if Path(candidate).is_file():
            return candidate
    return None


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
        self._front_renderer: Any | None = None
        self._overlay_actor: Any | None = None
        self._overlay_reserve = 0.0
        self._empty_state_actor: Any | None = None
        self._grid_actor: Any | None = None
        self._camera_direction: tuple[float, float, float] = DEFAULT_CAMERA_DIRECTION
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_toolbar())
        widget = self._create_plotter(plotter_factory)
        layout.addWidget(widget, 1)
        self._sync_toolbar()
        self._update_empty_state()

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
        self._remove_centroid()
        self._plotter.clear()
        self._reset_actors()
        self._update_empty_state()
        self._base_face_polydata = base_face_polydata(model, pv)
        self.base_face_available.emit(self._base_face_polydata is not None)
        self._newly_exposed_surface_polydata = newly_exposed_surface_polydata(model, pv)
        self.newly_exposed_surface_available.emit(self._newly_exposed_surface_polydata is not None)
        self._configure_lighting()
        self._plotter.add_axes(viewport=AXES_VIEWPORT)
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
        self._update_grid()
        self._apply_mesh_shading()
        self._update_feature_edges(render=False)
        self._update_base_face(render=False)
        self._update_newly_exposed_surface(render=False)
        self.set_camera(self._camera_direction)
        self._update_projection()
        self._sync_toolbar()

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
        grid_changed = options.show_grid != self._options.show_grid
        self._options = options
        if grid_changed:
            self._update_grid()
        self._apply_display_options()
        self._update_base_face(render=False)
        self._update_newly_exposed_surface(render=False)
        self._update_projection()

    def set_view_direction(self, direction: tuple[float, float, float]) -> None:
        """Look from a preset direction and keep it for models loaded later."""
        self._camera_direction = direction
        self.set_camera(direction)

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

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self._plotter is None:
            return
        # Pixel-sized text needs new wrap widths and anchors when the view changes size.
        self._update_empty_state()
        if self._model is not None and self._model.vertex_count > 0:
            self._update_overlay()
        self._plotter.render()

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
        self._plotter.add_axes(viewport=AXES_VIEWPORT)
        self._plotter.enable_parallel_projection()
        return self._plotter

    def _build_toolbar(self) -> QtWidgets.QWidget:
        toolbar = QtWidgets.QWidget()
        toolbar.setObjectName("viewerToolbar")
        row = QtWidgets.QHBoxLayout(toolbar)
        row.setContentsMargins(8, 4, 8, 4)
        row.setSpacing(4)
        label = QtWidgets.QLabel("View")
        label.setObjectName("viewerToolbarLabel")
        row.addWidget(label)
        self.view_buttons: list[QtWidgets.QToolButton] = []
        for text, tooltip, direction in CAMERA_VIEWS:
            button = QtWidgets.QToolButton()
            button.setObjectName("viewButton")
            button.setText(text)
            button.setToolTip(tooltip)
            # Keep labels whole on narrow windows; the stretch absorbs the spare width.
            button.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Minimum, QtWidgets.QSizePolicy.Policy.Fixed
            )
            button.clicked.connect(
                lambda _checked=False, direction=direction: self.set_view_direction(direction)
            )
            row.addWidget(button)
            self.view_buttons.append(button)
        row.addStretch(1)
        self.save_image_button = QtWidgets.QPushButton("Save Image…")
        self.save_image_button.setObjectName("viewerSaveButton")
        self.save_image_button.setToolTip("Save the current 3D view as a PNG image.")
        self.save_image_button.clicked.connect(self.choose_and_save_image)
        row.addWidget(self.save_image_button)
        return toolbar

    def _sync_toolbar(self) -> None:
        ready = (
            self._plotter is not None and self._model is not None and self._model.vertex_count > 0
        )
        for button in self.view_buttons:
            button.setEnabled(ready)
        self.save_image_button.setEnabled(ready)

    def _reset_actors(self) -> None:
        self._mesh_actor = None
        self._feature_edges_actor = None
        self._base_face_actor = None
        self._newly_exposed_surface_actor = None
        self._vector_actor = None
        self._centroid_actor = None
        self._overlay_actor = None
        self._empty_state_actor = None
        self._grid_actor = None

    def _update_grid(self) -> None:
        if self._plotter is None:
            return
        self._plotter.remove_bounds_axes()
        self._grid_actor = None
        if not self._options.show_grid or self._mesh_polydata is None:
            return
        # Bind to geometry rather than the empty renderer or auxiliary actors.
        # Explicit text settings avoid theme-sized labels and VTK-version defaults.
        self._grid_actor = self._plotter.show_grid(
            mesh=self._mesh_polydata,
            # Axis labels are drawn in render-window pixels without DPI scaling.
            font_size=round(GRID_LABEL_FONT_SIZE * self._device_pixel_ratio()),
            bold=False,
            use_3d_text=False,
            n_xlabels=3,
            n_ylabels=3,
            n_zlabels=3,
        )

    def _configure_lighting(self) -> None:
        if self._plotter is None:
            return
        try:
            self._plotter.remove_all_lights()
            import pyvista as pv

            # Lights follow the camera so projection-aligned and user-orbited views keep the
            # same brightness; scene-fixed lights left back-facing views dark.
            for light in (
                pv.Light(light_type="headlight", intensity=0.8),
                pv.Light(
                    position=(-0.6, 0.8, 1.0),
                    focal_point=(0.0, 0.0, 0.0),
                    light_type="camera light",
                    intensity=0.35,
                ),
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
        if self._options.show_projection_arrow and direction is not None:
            start, vector = projection_arrow_geometry(
                self._model.vertices,
                direction,
                through_point=row_centroid_point(self._row),
            )
            self._vector_actor = self._plotter.add_arrows(
                start.reshape(1, 3),
                vector.reshape(1, 3),
                color="#d04a02",
                ambient=0.45,
                diffuse=0.65,
                specular=0.1,
            )
        self._update_centroid()
        if align_camera and direction is not None:
            position, focal_point, view_up = projection_camera_geometry(
                self._model.vertices, direction
            )
            self._set_camera(position, focal_point, view_up)
        self._update_overlay()
        # PyVista refreshes grid bounds from every actor when overlays are added/removed.
        # Keep projection arrows and highlight offsets out of the coordinate grid.
        if self._grid_actor is not None and self._mesh_polydata is not None:
            self._grid_actor.bounds = self._mesh_polydata.bounds
        self._plotter.render()

    def _projection_direction(self) -> np.ndarray | None:
        if self._row is not None and self._row.direction_x is not None:
            return np.array(
                [self._row.direction_x, self._row.direction_y, self._row.direction_z], dtype=float
            )
        request = self._request
        if request is None:
            # Without a valid request there is no attitude to preview.
            return None
        if request.attitude_mode == "vector":
            try:
                return parse_vector(f"{request.vector_x},{request.vector_y},{request.vector_z}")
            except ValueError:
                # An unfinished vector has no preview; calculation validates it separately.
                return None
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
        self._remove_centroid()
        if not self._options.show_centroid:
            return
        point = row_centroid_point(self._row)
        if point is None or self._model is None:
            return
        import pyvista as pv

        radius = max(float(np.ptp(self._model.vertices, axis=0).max()) * 0.025, 1.0e-6)
        marker = pv.Sphere(
            radius=radius, center=tuple(point), theta_resolution=24, phi_resolution=12
        )
        actor = self._plotter.add_mesh(
            marker,
            color="#ffd400",
            ambient=0.55,
            diffuse=0.55,
            specular=0.0,
            pickable=False,
        )
        self._centroid_actor = actor
        # The projected-area centroid usually lies inside the body and, in a projection-aligned
        # view, directly behind the arrow; draw it in a front layer so it stays visible.
        front = self._ensure_front_renderer()
        if front is not None:
            self._plotter.remove_actor(actor)
            front.AddActor(actor)

    def _ensure_front_renderer(self) -> Any | None:
        if self._plotter is None:
            return None
        try:
            render_window = self._plotter.ren_win
            camera = self._plotter.camera
        except AttributeError:
            return None
        if render_window is None:
            return None
        if self._front_renderer is None:
            from vtkmodules.vtkRenderingCore import vtkRenderer

            renderer = vtkRenderer()
            renderer.SetLayer(1)
            renderer.InteractiveOff()
            render_window.SetNumberOfLayers(max(render_window.GetNumberOfLayers(), 2))
            render_window.AddRenderer(renderer)
            self._front_renderer = renderer
        # PyVista may replace the camera object; keep the front layer on the active one.
        self._front_renderer.SetActiveCamera(camera)
        return self._front_renderer

    def _remove_centroid(self) -> None:
        actor = self._centroid_actor
        if actor is None:
            return
        if self._front_renderer is not None and self._front_renderer.HasViewProp(actor):
            self._front_renderer.RemoveActor(actor)
            self._centroid_actor = None
        else:
            self._remove_actor("_centroid_actor")

    def _update_overlay(self) -> None:
        if self._plotter is None:
            return
        self._remove_actor("_overlay_actor")
        text = (
            overlay_text(
                self._row,
                model=self._model,
                request=self._request,
                detailed=self._options.detailed_overlay,
            )
            if self._options.show_overlay
            else ""
        )
        if not text:
            self._set_overlay_reserve(0.0)
            return
        ratio = self._device_pixel_ratio()
        font_size = self._text_font_size(OVERLAY_FONT_SIZE)
        view_width, view_height = self._view_size()
        max_chars = int(
            view_width * _OVERLAY_MAX_WIDTH_FRACTION / (OVERLAY_FONT_SIZE * _CHARACTER_WIDTH_RATIO)
        )
        text = fit_overlay_text(text, max(max_chars, 24))
        margin = OVERLAY_MARGIN * ratio
        # Indent each line so the background panel has horizontal padding.
        padded = "\n".join(f" {line} " for line in text.splitlines())
        actor = self._plotter.add_text(
            padded,
            position=(margin, view_height * ratio - margin),
            font_size=OVERLAY_FONT_SIZE,
            color=_TEXT_COLOR,
            shadow=False,
        )
        self._overlay_actor = actor
        self._style_text(
            actor,
            font_size=font_size,
            color=_TEXT_COLOR,
            horizontal="left",
            vertical="top",
            panel=True,
        )
        width = self._text_width(actor)
        if width is None:
            longest = max(len(line) for line in text.splitlines()) + 2
            width = longest * OVERLAY_FONT_SIZE * _CHARACTER_WIDTH_RATIO * ratio
        self._set_overlay_reserve(
            overlay_reserved_fraction(
                width + margin * 2,
                view_width * ratio,
                limit=_OVERLAY_MAX_WIDTH_FRACTION + 0.03,
            )
        )

    def _view_size(self) -> tuple[int, int]:
        """Size of the 3D render area in logical pixels, excluding the toolbar."""
        view = self._plotter if isinstance(self._plotter, QtWidgets.QWidget) else self
        return max(view.width(), 1), max(view.height(), 1)

    def _update_empty_state(self) -> None:
        if self._plotter is None:
            return
        self._remove_actor("_empty_state_actor")
        if self._model is not None:
            return
        ratio = self._device_pixel_ratio()
        view_width, view_height = self._view_size()
        actor = self._plotter.add_text(
            EMPTY_STATE_TEXT,
            position=(view_width * ratio / 2, view_height * ratio / 2),
            font_size=EMPTY_STATE_FONT_SIZE,
            color=_MUTED_TEXT_COLOR,
            shadow=False,
        )
        self._empty_state_actor = actor
        self._style_text(
            actor,
            font_size=self._text_font_size(EMPTY_STATE_FONT_SIZE),
            color=_MUTED_TEXT_COLOR,
            horizontal="center",
            vertical="center",
            panel=False,
        )

    def _style_text(
        self,
        actor: Any,
        *,
        font_size: int,
        color: str,
        horizontal: str,
        vertical: str,
        panel: bool,
    ) -> None:
        try:
            prop = actor.GetTextProperty()
        except AttributeError:
            prop = actor.prop
        try:
            from pyvista import Color

            font_file = _ui_font_file()
            if font_file is not None:
                prop.SetFontFamily(4)  # VTK_FONT_FILE
                prop.SetFontFile(font_file)
            else:
                prop.SetFontFamilyToArial()
            prop.SetFontSize(font_size)
            prop.SetColor(Color(color).float_rgb)
            prop.SetLineSpacing(1.2)
            prop.SetJustification({"left": 0, "center": 1, "right": 2}[horizontal])
            prop.SetVerticalJustification({"bottom": 0, "center": 1, "top": 2}[vertical])
            if panel:
                prop.SetBackgroundColor(Color(_PANEL_COLOR).float_rgb)
                prop.SetBackgroundOpacity(0.86)
                prop.SetFrame(True)
                prop.SetFrameColor(Color(_PANEL_BORDER_COLOR).float_rgb)
                prop.SetFrameWidth(max(round(self._device_pixel_ratio()), 1))
        except (AttributeError, ImportError):
            pass

    def _text_width(self, actor: Any) -> float | None:
        if self._plotter is None:
            return None
        try:
            bounds = [0.0, 0.0, 0.0, 0.0]
            actor.GetBoundingBox(self._plotter.renderer, bounds)
        except (AttributeError, TypeError):
            return None
        width = float(bounds[1] - bounds[0])
        return width if width > 0.0 else None

    def _set_overlay_reserve(self, reserve: float) -> None:
        """Shift the scene right so geometry stays clear of the upper-left overlay."""
        previous = self._overlay_reserve
        self._overlay_reserve = reserve
        if self._plotter is None or reserve == previous:
            return
        camera = self._plotter.camera
        try:
            # Keep the apparent model size proportional to the free part of the view.
            camera.parallel_scale = camera.parallel_scale * (1.0 - previous) / (1.0 - reserve)
            camera.SetWindowCenter(-reserve, 0.0)
        except AttributeError:
            pass

    def _device_pixel_ratio(self) -> float:
        try:
            return max(float(self.devicePixelRatioF()), 1.0)
        except (AttributeError, RuntimeError):
            return 1.0

    def _text_font_size(self, size: int) -> int:
        """Convert logical pixels to a VTK text size, which VTK scales by the window DPI."""
        dpi = 72.0
        try:
            dpi = float(self._plotter.ren_win.GetDPI()) if self._plotter is not None else dpi
        except (AttributeError, TypeError):
            pass
        return max(round(size * self._device_pixel_ratio() * 72.0 / max(dpi, 1.0)), 1)

    def _set_camera(
        self, position: np.ndarray, focal_point: np.ndarray, view_up: np.ndarray
    ) -> None:
        if self._plotter is None:
            return
        self._plotter.camera_position = (tuple(position), tuple(focal_point), tuple(view_up))
        if self._front_renderer is not None:
            self._ensure_front_renderer()
        self._plotter.enable_parallel_projection()
        self._plotter.reset_camera()
        # Leave room for grid labels outside the geometry bounds and for the overlay panel.
        self._plotter.camera.zoom(0.9 * (1.0 - self._overlay_reserve))
        try:
            self._plotter.camera.SetWindowCenter(-self._overlay_reserve, 0.0)
        except AttributeError:
            pass
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
