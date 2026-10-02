"""Edicao de um vertice por vez para IngeTrazo (APIs 1 e 2).

Extensoes > Editar vertice: clique no vertice e depois no destino.
"""

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import (
    QAction, QColor, QBrush, QIcon, QPainter, QPen, QPixmap, QVector3D,
)
from PySide6.QtWidgets import QToolBar

from core.history import SnapshotImport
from core.units import fmt_len
from core.axes import axis
from tools.base import Tool


_editor = None
_app = None


def _project_vertices(viewport, vertices):
    """Project in one public API call on API 2; keep the 0.5.5 fallback."""
    if _app.api_version >= 2:
        points = [
            [v.position.x(), v.position.y(), v.position.z()]
            for v in vertices
        ]
        if not points:
            return []
        xs, ys, front = _app.world_to_pixels(points)
        return [
            (float(xs[i]), float(ys[i])) if front[i] else None
            for i in range(len(points))
        ]
    return [viewport._world_to_pixel(v.position) for v in vertices]


def _vertex_icon(window):
    """A small mesh corner with one green vertex, distinct from built-in icons."""
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    ink = window.palette().windowText().color()
    painter.setPen(QPen(ink, 5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    a, b, c = QPointF(13, 14), QPointF(13, 50), QPointF(49, 32)
    painter.drawLine(a, b)
    painter.drawLine(a, c)
    painter.drawLine(b, c)
    painter.setBrush(QBrush(ink))
    painter.drawEllipse(a, 4, 4)
    painter.drawEllipse(b, 4, 4)
    painter.setPen(QPen(QColor(13, 70, 28), 3))
    painter.setBrush(QBrush(QColor(48, 215, 91)))
    painter.drawEllipse(c, 9, 9)
    painter.end()
    return QIcon(pixmap)


def _picked_vertex(viewport, x, y):
    """O pick nativo retorna uma POSICAO, nao um objeto Vertex."""
    position = viewport.pick_vertex(x, y)
    if position is None:
        return None
    return viewport.scene.mesh.vertex_at(position)


def _draw_vertices(viewport, painter):
    tool = _editor
    if tool is None or viewport.active_tool is not tool:
        return

    vertices = list(viewport.scene.mesh.vertices)
    pixels = _project_vertices(viewport, vertices)
    painter.setPen(QPen(QColor(30, 30, 30), 1))
    for vertex, pixel in zip(vertices, pixels):
        if pixel is None:
            continue
        if vertex is tool.selected:
            color, radius = QColor(0, 230, 90), 7.0
        elif vertex is tool.hover:
            color, radius = QColor(255, 220, 0), 6.0
        else:
            color, radius = QColor(255, 60, 60), 4.0
        painter.setBrush(QBrush(color))
        painter.drawEllipse(QPointF(*pixel), radius, radius)


class VertexEditorTool(Tool):
    name = "Editar vertice (2 cliques)"
    shortcut = None
    vcb_label = "Distance"
    prefers_vertical_drag = True
    magnetic_axis_deg = 15.0
    screen_axis_px = 9.0

    def __init__(self):
        global _editor
        _editor = self
        self.selected = None
        self.hover = None
        self.start_point = None
        self.hover_point = None
        self._preview_delta = QVector3D(0, 0, 0)

    def on_activate(self, viewport):
        # O menu de extensoes chama on_activate sem trocar a ferramenta.
        # A primeira chamada faz a troca; a segunda vem de set_active_tool.
        if viewport.active_tool is not self:
            viewport.set_active_tool(self)
            return
        self.on_cancel(viewport)
        viewport.flash_status(
            "Editar vertice: clique num ponto vermelho; depois clique no destino.",
            5000,
        )

    def on_deactivate(self, viewport):
        self.on_cancel(viewport)

    def on_cancel(self, viewport):
        self._revert_preview(viewport)
        self.selected = None
        self.hover = None
        self.start_point = None
        self.hover_point = None
        self._preview_delta = QVector3D(0, 0, 0)
        viewport.update()

    def _revert_preview(self, viewport):
        if (self.selected is not None
                and self.selected in viewport.scene.mesh.vertices
                and self._preview_delta.lengthSquared() > 1e-12):
            viewport.scene.mesh.place_vertex(self.selected, self.start_point)
            viewport.scene.version += 1
        self._preview_delta = QVector3D(0, 0, 0)

    def _apply_preview(self, viewport, target):
        if self.selected not in viewport.scene.mesh.vertices:
            self.on_cancel(viewport)
            return
        desired = QVector3D(target - self.start_point)
        if (target - self.selected.position).lengthSquared() > 1e-12:
            viewport.scene.mesh.place_vertex(self.selected, target)
            viewport.scene.version += 1
            self._preview_delta = desired

    def snap_excluded(self):
        if self.selected is None:
            return None
        return {id(edge) for edge in self.selected.edges}, set()

    def rubber_band_lines(self):
        if self.start_point is None or self.hover_point is None:
            return []
        return [(self.start_point, self.hover_point)]

    def value_label(self):
        if self.start_point is None or self.hover_point is None:
            return None
        return (fmt_len((self.hover_point - self.start_point).length()),
                (self.start_point + self.hover_point) * 0.5)

    def on_hover(self, ctx):
        viewport = ctx.viewport
        if self.selected is None:
            self.hover = _picked_vertex(viewport, ctx.screen.x(), ctx.screen.y())
        else:
            self.hover = None
            self.hover_point = QVector3D(ctx.world)
            self._apply_preview(viewport, self.hover_point)
        viewport.update()

    def on_click(self, ctx):
        viewport = ctx.viewport
        mesh = viewport.scene.mesh
        if self.selected is None:
            vertex = _picked_vertex(viewport, ctx.screen.x(), ctx.screen.y())
            if vertex is None:
                viewport.flash_status("Clique exatamente em um vertice vermelho.", 3000)
                return
            self.selected = vertex
            self.start_point = QVector3D(vertex.position)
            self.hover_point = None
            self._preview_delta = QVector3D(0, 0, 0)
            viewport.flash_status(
                "Mova o mouse; setas travam o eixo. Clique ou digite a medida e Enter; Esc cancela.",
                6500,
            )
            viewport.update()
            return

        self._commit(viewport, QVector3D(ctx.world - self.start_point))

    def on_value(self, viewport, value):
        if self.selected is None or self.start_point is None:
            return False
        if isinstance(value, tuple):
            if len(value) != 3:
                return False
            delta = QVector3D(*value)
        else:
            direction = (self.hover_point - self.start_point
                         if self.hover_point is not None else QVector3D(0, 0, 0))
            if direction.lengthSquared() < 1e-12:
                lock = getattr(viewport, "axis_lock", None)
                if lock in ("x", "y", "z"):
                    direction = axis(lock)
                else:
                    viewport.flash_status("Aponte uma direção com o mouse antes de digitar.", 3500)
                    return False
            delta = direction.normalized() * value
        self._commit(viewport, delta)
        return True

    def _commit(self, viewport, delta):
        if delta.lengthSquared() < 1e-12:
            self._revert_preview(viewport)
            viewport.update()
            viewport.flash_status("O deslocamento é zero.", 3000)
            return
        origin = QVector3D(self.start_point)
        self._revert_preview(viewport)
        mesh = viewport.scene.mesh
        selected = mesh.vertex_at(origin)
        target = origin + delta
        destination = mesh.vertex_at(target)
        welding = (destination is not None and destination is not selected)
        if welding:
            # Use the existing vertex's exact coordinate, not a nearby snap
            # point, so the two vertices reliably become one.
            target = QVector3D(destination.position)
            delta = target - origin

        def mutate(scene):
            active_mesh = scene.mesh
            vertex = active_mesh.vertex_at(origin)
            if vertex is None:
                raise RuntimeError("O vertice mudou antes da operacao; tente novamente.")
            boundary_before = sum(len(edge.faces) == 1 for edge in active_mesh.edges)
            loose_before = sum(len(edge.faces) == 0 for edge in active_mesh.edges)
            nonmanifold_before = sum(len(edge.faces) > 2 for edge in active_mesh.edges)
            active_mesh.place_vertex(vertex, target)
            if welding:
                active_mesh.weld_coincident()
                active_mesh.prune_orphan_vertices()
                if any(len(set(loop)) != len(loop)
                       for face in active_mesh.faces
                       for loop in (face.loop, *face.hole_loops)):
                    raise ValueError("A fusão deixaria uma face inválida")
                if (sum(len(edge.faces) == 1 for edge in active_mesh.edges)
                        > boundary_before
                        or sum(len(edge.faces) == 0 for edge in active_mesh.edges)
                        > loose_before
                        or sum(len(edge.faces) > 2 for edge in active_mesh.edges)
                        > nonmanifold_before):
                    raise ValueError("A fusão abriria a malha; escolha outro vértice")

        viewport.history.execute(SnapshotImport(mutate))
        error = viewport.history.last_error
        self.on_cancel(viewport)
        viewport.notify_scene_changed()
        if error:
            viewport.flash_status(f"Movimento não aplicado: {error}", 7000)
            return
        viewport.flash_status(
            "Vértices unidos e malha limpa. Ctrl+Z desfaz."
            if welding else "Vértice movido. Ctrl+Z desfaz.", 4500
        )


def setup(app):
    global _app
    if app.api_version not in (1, 2):
        raise RuntimeError(f"Plugin suporta APIs 1 e 2; encontrada API {app.api_version}")
    _app = app
    app.add_overlay(_draw_vertices)
    if app.api_version >= 2:
        app.on_document_changed(
            lambda: _editor.on_cancel(app.viewport)
            if _editor.selected is not None
            and _editor.selected not in app.viewport.scene.mesh.vertices
            else None
        )

    # A separate movable toolbar, following IngeTrazo's toolbar layout.
    toolbar = QToolBar("Vertex", app.window)
    toolbar.setObjectName("vertex_editor_toolbar")
    toolbar.setMovable(True)
    toolbar.setFloatable(True)
    toolbar.setAllowedAreas(Qt.AllToolBarAreas)
    reference = next((tb for tb in app.window.findChildren(QToolBar)
                      if tb is not toolbar), None)
    if reference is not None:
        toolbar.setIconSize(reference.iconSize())
    toolbar.setToolButtonStyle(Qt.ToolButtonIconOnly)
    app.window.addToolBar(Qt.TopToolBarArea, toolbar)
    action = QAction(_vertex_icon(app.window), "Editar vertice", app.window)
    action.setToolTip("Mover um vértice: arraste com o mouse, trave eixo ou digite distância")
    action.triggered.connect(lambda _checked=False: _editor.on_activate(app.viewport))
    toolbar.addAction(action)
