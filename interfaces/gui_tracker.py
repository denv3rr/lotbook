import json
import time
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import QAbstractTableModel, QTimer, Qt, QModelIndex
from PySide6.QtGui import QColor
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStatusBar,
    QTableView,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from modules.market_data.trackers import GlobalTrackers


_MAP_HTML = """
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="initial-scale=1,maximum-scale=1,user-scalable=no" />
  <title>Lotbook - Global Trackers</title>
  <script src="https://unpkg.com/maplibre-gl@2.4.0/dist/maplibre-gl.js"></script>
  <link href="https://unpkg.com/maplibre-gl@2.4.0/dist/maplibre-gl.css" rel="stylesheet" />
  <style>
    :root {
      color-scheme: dark;
    }
    html, body {
      margin: 0;
      padding: 0;
      height: 100%;
      background: #0b0e13;
      font-family: system-ui, -apple-system, Segoe UI, sans-serif;
    }
    #map {
      position: absolute;
      top: 0;
      bottom: 0;
      width: 100%;
      height: 100%;
    }
    .maplibregl-popup-content {
      background: #0f121a;
      color: #dfe6ef;
      border: 1px solid #1d2433;
      border-radius: 6px;
      box-shadow: 0 10px 40px rgba(0,0,0,0.4);
    }
    .maplibregl-popup-tip {
      border-top-color: #0f121a;
    }
  </style>
</head>
<body>
<div id="map"></div>
<script>
  const map = new maplibregl.Map({
    container: 'map',
    style: 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json',
    center: [0, 20],
    zoom: 1.6,
    pitch: 0,
    bearing: 0,
    attributionControl: false,
  });

  map.addControl(new maplibregl.NavigationControl({visualizePitch: true}), 'top-right');

  let popup = new maplibregl.Popup({ closeButton: true, closeOnClick: true });

  function buildGeoJSON(points) {
    return {
      type: 'FeatureCollection',
      features: points.map(pt => ({
        type: 'Feature',
        geometry: {
          type: 'Point',
          coordinates: [pt.lon, pt.lat],
        },
        properties: pt,
      }))
    };
  }

  function colorForPoint(kind, category) {
    if (kind === 'flight') {
      if (category === 'military') return '#ff4d4d';
      if (category === 'cargo') return '#f7c948';
      if (category === 'private') return '#5cc8ff';
      if (category === 'government') return '#9c7cff';
      if (category === 'commercial') return '#51f19a';
      return '#7287a4';
    }
    if (kind === 'ship') {
      if (category === 'tanker') return '#f48fb1';
      if (category === 'cargo') return '#f7c948';
      if (category === 'passenger') return '#7dd3fc';
      if (category === 'military') return '#ff4d4d';
      if (category === 'fishing') return '#7bdff6';
      if (category === 'pleasure') return '#5b8cff';
      if (category === 'government') return '#9c7cff';
      return '#7287a4';
    }
    return '#7287a4';
  }

  function upsertPoints(points) {
    const sourceId = 'tracker-points';
    const data = buildGeoJSON(points);

    if (map.getSource(sourceId)) {
      map.getSource(sourceId).setData(data);
    } else {
      map.addSource(sourceId, {
        type: 'geojson',
        data: data,
      });

      map.addLayer({
        id: 'tracker-glow',
        type: 'circle',
        source: sourceId,
        paint: {
          'circle-radius': 10,
          'circle-color': ['case', ['has', 'kind'], ['get', 'color'], '#7a8aa0'],
          'circle-opacity': 0.18,
        }
      });

      map.addLayer({
        id: 'tracker-points',
        type: 'circle',
        source: sourceId,
        paint: {
          'circle-radius': 4,
          'circle-color': ['case', ['has', 'kind'], ['get', 'color'], '#7a8aa0'],
          'circle-stroke-color': '#0b0e13',
          'circle-stroke-width': 1,
        }
      });

      map.on('mousemove', 'tracker-points', (e) => {
        map.getCanvas().style.cursor = 'pointer';
      });

      map.on('mouseleave', 'tracker-points', (e) => {
        map.getCanvas().style.cursor = '';
      });

      map.on('click', 'tracker-points', (e) => {
        const feature = e.features[0];
        if (!feature) return;
        const props = feature.properties || {};
        const hasValue = (value) => value !== undefined && value !== null;
        const label = props.label || 'Unknown';
        const kind = props.kind || '-';
        const category = props.category || '-';
        const speed = hasValue(props.speed_kts) ? `${Number(props.speed_kts).toFixed(0)} kts` : 'n/a';
        const speedHeat = hasValue(props.speed_heat) ? `${(Number(props.speed_heat) * 100).toFixed(0)}%` : 'n/a';
        const vol = hasValue(props.speed_vol_kts) ? `${Number(props.speed_vol_kts).toFixed(0)} kts` : 'n/a';
        const volHeat = hasValue(props.vol_heat) ? `${(Number(props.vol_heat) * 100).toFixed(0)}%` : 'n/a';
        const alt = hasValue(props.altitude_ft) ? `${Number(props.altitude_ft).toFixed(0)} ft` : 'n/a';
        const heading = hasValue(props.heading_deg) ? `${Number(props.heading_deg).toFixed(0)} deg` : 'n/a';
        const updated = hasValue(props.updated_ts) ? new Date(Number(props.updated_ts) * 1000).toLocaleTimeString() : 'n/a';
        const content = `
          <div style="font-weight:600; margin-bottom:4px;">${label}</div>
          <div style="opacity:0.7; margin-bottom:8px;">${kind} - ${category}</div>
          <div>Speed: ${speed}</div>
          <div>Speed Heat: ${speedHeat}</div>
          <div>Speed Volatility: ${vol}</div>
          <div>Vol Heat: ${volHeat}</div>
          <div>Altitude: ${alt}</div>
          <div>Heading: ${heading}</div>
          <div>Updated: ${updated}</div>
        `;
        popup.setLngLat(feature.geometry.coordinates).setHTML(content).addTo(map);
      });
    }

    if (map.getSource(sourceId)) {
      const geojson = buildGeoJSON(points.map(pt => ({
        ...pt,
        color: colorForPoint(pt.kind, pt.category),
      })));
      map.getSource(sourceId).setData(geojson);
    }
  }

  window.setTrackerPoints = (payload) => {
    try {
      const data = JSON.parse(payload);
      if (!Array.isArray(data)) return;
      if (!map.isStyleLoaded()) {
        map.once('load', () => upsertPoints(data));
        return;
      }
      upsertPoints(data);
    } catch (err) {
      console.error(err);
    }
  };
</script>
</body>
</html>
"""


class TrackerTableModel(QAbstractTableModel):
    HEADERS = [
        "Type",
        "Category",
        "Label",
        "Country",
        "Lat",
        "Lon",
        "Alt(ft)",
        "Spd(kts)",
        "Spd Heat",
        "Vol(kts)",
        "Vol Heat",
        "Hdg",
        "Age",
        "Industry",
    ]

    def __init__(self):
        super().__init__()
        self._rows: List[Dict[str, object]] = []
        self._last_refresh_ts: Optional[int] = None

    @staticmethod
    def _heat_color(value: Optional[float]) -> Optional[QColor]:
        if value is None:
            return None
        try:
            v = float(value)
        except Exception:
            return None
        if v >= 0.85:
            color = QColor("#c62828")
        elif v >= 0.70:
            color = QColor("#d84315")
        elif v >= 0.50:
            color = QColor("#f9a825")
        elif v >= 0.30:
            color = QColor("#2e7d32")
        elif v >= 0.15:
            color = QColor("#00838f")
        else:
            color = QColor("#263238")
        color.setAlpha(140)
        return color

    def update_rows(self, rows: List[Dict[str, object]], refresh_ts: Optional[int]) -> None:
        self.beginResetModel()
        self._rows = rows
        self._last_refresh_ts = refresh_ts
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self.HEADERS)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        col = index.column()
        now = int(time.time())

        if role == Qt.DisplayRole:
            if col == 0:
                return row.get("kind", "-")
            if col == 1:
                return row.get("category", "-")
            if col == 2:
                return row.get("label", "-")
            if col == 3:
                return row.get("country", "-")
            if col == 4:
                return f"{row.get('lat', 0.0):.2f}"
            if col == 5:
                return f"{row.get('lon', 0.0):.2f}"
            if col == 6:
                alt = row.get("altitude_ft")
                return "-" if alt is None else f"{alt:,.0f}"
            if col == 7:
                spd = row.get("speed_kts")
                return "-" if spd is None else f"{spd:,.0f}"
            if col == 8:
                heat = row.get("speed_heat")
                return "-" if heat is None else f"{float(heat) * 100:.0f}%"
            if col == 9:
                vol = row.get("speed_vol_kts")
                return "-" if vol is None else f"{float(vol):,.0f}"
            if col == 10:
                heat = row.get("vol_heat")
                return "-" if heat is None else f"{float(heat) * 100:.0f}%"
            if col == 11:
                hdg = row.get("heading_deg")
                return "-" if hdg is None else f"{hdg:,.0f}"
            if col == 12:
                updated = row.get("updated_ts")
                if updated:
                    try:
                        return str(max(0, now - int(updated)))
                    except Exception:
                        return "-"
                return "-"
            if col == 13:
                return row.get("industry", "-")

        if role == Qt.TextAlignmentRole:
            if col in (4, 5, 6, 7, 9, 11, 12):
                return Qt.AlignRight | Qt.AlignVCenter
            if col in (8, 10):
                return Qt.AlignCenter
            return Qt.AlignLeft | Qt.AlignVCenter

        if role == Qt.ForegroundRole:
            if col == 0:
                kind = str(row.get("kind", ""))
                if kind == "flight":
                    return QColor("#7dd3fc")
                if kind == "ship":
                    return QColor("#f7c948")
            return QColor("#d3d8e3")

        if role == Qt.BackgroundRole:
            if col == 8:
                return self._heat_color(row.get("speed_heat"))
            if col == 10:
                return self._heat_color(row.get("vol_heat"))

        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            if 0 <= section < len(self.HEADERS):
                return self.HEADERS[section]
        return None


class TrackerGuiWindow(QMainWindow):
    def __init__(self, refresh_seconds: int = 10, start_paused: bool = False):
        super().__init__()
        self.setWindowTitle("Lotbook - Global Trackers")
        self.resize(1400, 800)
        self.setStyleSheet(self._build_stylesheet())

        self.trackers = GlobalTrackers()
        self.refresh_seconds = max(5, int(refresh_seconds))
        self._snapshot: Dict[str, object] = {}
        self._mode = "combined"
        self._category_filter = "all"

        self._init_ui()
        self._init_timer()
        if start_paused:
            self._toggle_pause()
        self._refresh()

    def _build_stylesheet(self) -> str:
        return """
            QMainWindow {
                background-color: #0b0e13;
            }
            QToolBar {
                background-color: #0f121a;
                border: 1px solid #161b26;
                spacing: 8px;
            }
            QLabel {
                color: #dfe6ef;
            }
            QPushButton {
                background-color: #141a26;
                color: #dfe6ef;
                border: 1px solid #1d2433;
                padding: 6px 12px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #1b2332;
            }
            QComboBox {
                background-color: #141a26;
                color: #dfe6ef;
                border: 1px solid #1d2433;
                padding: 4px 10px;
            }
            QStatusBar {
                background-color: #0f121a;
                color: #8f9bb3;
                border-top: 1px solid #161b26;
            }
            QTableView {
                background-color: #0f121a;
                color: #d3d8e3;
                gridline-color: #1d2433;
                selection-background-color: #1c2433;
                selection-color: #f8fafc;
            }
            QHeaderView::section {
                background-color: #111826;
                color: #9fb0c7;
                padding: 6px;
                border: 1px solid #1d2433;
            }
        """

    def _init_ui(self) -> None:
        toolbar = QToolBar("Controls")
        toolbar.setMovable(False)

        mode_label = QLabel("Mode")
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["combined", "flights", "ships"])
        self.mode_combo.currentTextChanged.connect(self._on_mode_change)

        filter_label = QLabel("Filter")
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["all"])
        self.filter_combo.currentTextChanged.connect(self._on_filter_change)

        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self._force_refresh)

        pause_button = QPushButton("Pause")
        pause_button.clicked.connect(self._toggle_pause)
        self.pause_button = pause_button
        self._paused = False

        toolbar.addWidget(mode_label)
        toolbar.addWidget(self.mode_combo)
        toolbar.addSeparator()
        toolbar.addWidget(filter_label)
        toolbar.addWidget(self.filter_combo)
        toolbar.addSeparator()
        toolbar.addWidget(refresh_button)
        toolbar.addWidget(pause_button)

        self.addToolBar(toolbar)

        splitter = QSplitter(Qt.Horizontal)

        self.map_view = QWebEngineView()
        self.map_view.setHtml(_MAP_HTML, baseUrl=Path.cwd().as_uri())
        self.map_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.table_model = TrackerTableModel()
        self.table_view = QTableView()
        self.table_view.setModel(self.table_model)
        self.table_view.setSortingEnabled(False)
        self.table_view.verticalHeader().setVisible(False)
        self.table_view.horizontalHeader().setStretchLastSection(True)
        self.table_view.setAlternatingRowColors(True)

        splitter.addWidget(self.map_view)
        splitter.addWidget(self.table_view)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)

        self.setCentralWidget(container)

        status = QStatusBar()
        self.status_label = QLabel("Tracker ready.")
        status.addWidget(self.status_label)
        self.setStatusBar(status)

    def _init_timer(self) -> None:
        self.timer = QTimer(self)
        self.timer.setInterval(self.refresh_seconds * 1000)
        self.timer.timeout.connect(self._refresh)
        self.timer.start()

    def _toggle_pause(self) -> None:
        self._paused = not self._paused
        if self._paused:
            self.timer.stop()
            self.pause_button.setText("Resume")
            self.status_label.setText("Paused.")
        else:
            self.timer.start()
            self.pause_button.setText("Pause")
            self._refresh()

    def _force_refresh(self) -> None:
        self._refresh(force=True)

    def _on_mode_change(self, value: str) -> None:
        self._mode = value
        self._refresh(force=True)

    def _on_filter_change(self, value: str) -> None:
        self._category_filter = value
        self._render_snapshot()

    def _refresh(self, force: bool = False) -> None:
        if self._paused:
            return
        snapshot = self.trackers.get_snapshot(mode=self._mode)
        self._snapshot = snapshot
        self._update_filters(snapshot)
        self._render_snapshot()

    def _update_filters(self, snapshot: Dict[str, object]) -> None:
        categories = sorted({str(pt.get("category", "")).lower() for pt in snapshot.get("points", []) if pt.get("category")})
        options = ["all"] + categories
        current = self._category_filter if self._category_filter in options else "all"

        self.filter_combo.blockSignals(True)
        self.filter_combo.clear()
        self.filter_combo.addItems(options)
        self.filter_combo.setCurrentText(current)
        self.filter_combo.blockSignals(False)

    def _render_snapshot(self) -> None:
        snapshot = self._snapshot or {}
        if self._category_filter and self._category_filter != "all":
            snapshot = GlobalTrackers.apply_category_filter(snapshot, self._category_filter)
        rows = snapshot.get("points", [])

        self.table_model.update_rows(rows, int(time.time()))

        payload = json.dumps(rows)
        self.map_view.page().runJavaScript(f"window.setTrackerPoints({json.dumps(payload)});")

        meta = snapshot.get("meta", {}) if isinstance(snapshot.get("meta"), dict) else {}
        warning_list = list(snapshot.get("warnings", []) or [])
        warning_list.extend(meta.get("warnings", []) or [])
        warn = " | ".join(dict.fromkeys(warning_list)[:2])
        last = time.strftime("%H:%M:%S", time.localtime(time.time()))
        count = snapshot.get("count", len(rows))
        status = f"Mode: {self._mode} | Filter: {self._category_filter} | Points: {count} | Updated: {last}"
        if warn:
            status += f" | {warn}"
        self.status_label.setText(status)


def launch_tracker_gui(refresh_seconds: int = 10, start_paused: bool = False):
    app = QApplication.instance() or QApplication([])
    window = TrackerGuiWindow(refresh_seconds=refresh_seconds, start_paused=start_paused)
    window.show()
    app.exec()
