import QtQuick
import QtQuick.Controls
import Quickshell
import Quickshell.Wayland
import Quickshell.Io

// Interactive bar panel built as a layer-shell PanelWindow, NOT a PopupWindow.
// xdg-popups (PopupWindow) do not receive pointer input on their own in this
// compositor setup; Omarchy's own interactive widgets (see Ui/KeyboardPanel.qml)
// use a full-screen Overlay layer with the card positioned inside. That is the
// pattern copied here.
Item {
  id: root
  implicitWidth: 30
  implicitHeight: 30

  readonly property string cdailyApi: "http://127.0.0.1:8090"
  property int unreadCount: 0
  property var articles: []
  property bool opened: false
  property bool loading: false
  property string loadError: ""
  property int articleRequest: 0
  property var thumbnailSources: ({})
  property var thumbnailQueue: []
  property string thumbnailBatch: "[]"

  function queueThumbnails(items) {
    var urls = []
    for (var i = 0; i < items.length; i++) {
      var url = items[i].image_url
      if (url && !Object.prototype.hasOwnProperty.call(root.thumbnailSources, url) && urls.indexOf(url) < 0)
        urls.push(url)
    }
    root.thumbnailQueue = urls
    startThumbnails()
  }

  function startThumbnails() {
    if (thumbnails.running || !root.thumbnailQueue.length) return
    var pending = root.thumbnailQueue.filter(function(u) {
      return !Object.prototype.hasOwnProperty.call(root.thumbnailSources, u)
    })
    root.thumbnailQueue = []
    if (!pending.length) return
    root.thumbnailBatch = JSON.stringify(pending)
    thumbnails.running = true
  }

  // Remote TLS runs outside the desktop shell: Qt only decodes cached files.
  Process {
    id: thumbnails
    command: ["/usr/bin/python", Qt.resolvedUrl("thumbnail_cache.py").toString().replace(/^file:\/\//, ""), root.thumbnailBatch]
    stdout: StdioCollector {
      onStreamFinished: {
        try {
          var found = JSON.parse(text)
          root.thumbnailSources = Object.assign({}, root.thumbnailSources, found)
        } catch (e) {
          console.warn("CDaily thumbnail worker:", e)
        }
      }
    }
    onExited: Qt.callLater(root.startThumbnails)
  }
  property string activeCategory: ""   // "" = All

  // Category palette — mirrors cdaily's web app (static/css/style.css).
  readonly property var catColors: ({
    "news":     "#f59e0b",
    "tech":     "#3b82f6",
    "science":  "#10b981",
    "business": "#8b5cf6",
    "culture":  "#ef4444",
    "security": "#06b6d4"
  })
  readonly property var catLabels: ({
    "news": "News", "tech": "Tech", "science": "Science",
    "business": "Biz", "culture": "Culture", "security": "Sec"
  })
  // Static row order so pills never jump between fetches.
  readonly property var catOrder: ["news", "tech", "science", "business", "culture", "security"]
  property var stats: ({})

  function catColor(key) { return root.catColors[key] || "#6b7280" }

  // ── HTTP helpers (plain XMLHttpRequest, QML-local) ───────────────────────

  function httpGet(url, onOk, onError) {
    var xhr = new XMLHttpRequest()
    xhr.open("GET", url)
    var done = false
    var deadline = Date.now() + 15000
    function fail(message) {
      if (done) return
      done = true
      if (onError) onError(message)
    }
    // QML XHR has no browser-style timeout property. Reuse our watchdog timer.
    root.httpPending = root.httpPending.concat([{ xhr: xhr, deadline: deadline, fail: fail, done: function() { return done } }])
    xhr.onreadystatechange = function() {
      if (xhr.readyState !== XMLHttpRequest.DONE || done) return
      if (xhr.status !== 200) { fail("CDaily no responde (HTTP " + xhr.status + ")"); return }
      var data
      try { data = JSON.parse(xhr.responseText) }
      catch (e) { fail("Respuesta inválida de CDaily"); return }
      done = true
      onOk(data)
    }
    xhr.send()
  }

  property var httpPending: []
  Timer {
    interval: 1000; running: root.httpPending.length > 0; repeat: true
    onTriggered: {
      var remaining = []
      var now = Date.now()
      for (var i = 0; i < root.httpPending.length; i++) {
        var request = root.httpPending[i]
        if (request.done()) continue
        if (now > request.deadline) { request.fail("Tiempo de espera agotado"); request.xhr.abort() }
        else remaining.push(request)
      }
      root.httpPending = remaining
    }
  }

  function httpPost(url, onOk, onError) {
    var xhr = new XMLHttpRequest()
    xhr.open("POST", url)
    var done = false
    function fail(message) {
      if (done) return
      done = true
      if (onError) onError(message)
    }
    // Summaries may take longer than article lists; still bound the wait.
    root.httpPending = root.httpPending.concat([{ xhr: xhr, deadline: Date.now() + 120000, fail: fail, done: function() { return done } }])
    xhr.onreadystatechange = function() {
      if (xhr.readyState !== XMLHttpRequest.DONE || done) return
      if (xhr.status !== 200) { fail("CDaily no disponible (HTTP " + xhr.status + ")"); return }
      var data
      try { data = JSON.parse(xhr.responseText) }
      catch (e) { fail("Respuesta inválida de CDaily"); return }
      done = true
      if (onOk) onOk(data)
    }
    xhr.send()
  }

  function refresh() {
    httpGet(cdailyApi + "/api/stats", function(d) {
      root.stats = d || {}
      root.unreadCount = (d && d.total != null) ? d.total : 0
    })
  }

  function fetchArticles() {
    var request = ++root.articleRequest
    root.loading = true
    root.loadError = ""
    var url = cdailyApi + "/api/articles?limit=40&unread=1"
    if (root.activeCategory) url += "&cat=" + root.activeCategory
    httpGet(url, function(d) {
      if (request !== root.articleRequest) return
      root.loading = false
      if (!d || !d.articles) return
      var now = new Date()
      for (var i = 0; i < d.articles.length; i++) {
        d.articles[i].timeLabel = root.relTime(d.articles[i].published_date, now)
        d.articles[i].imageLoaded = false
        d.articles[i].imageFailed = false
      }
      root.articles = d.articles
      root.queueThumbnails(d.articles)
    }, function(message) {
      if (request !== root.articleRequest) return
      root.loading = false
      root.loadError = message
    })
  }

  function relTime(iso, now) {
    if (!iso) return ""
    var then = new Date(iso)
    var mins = Math.floor((now - then) / 60000)
    if (mins < 1) return "ahora"
    if (mins < 60) return mins + " min"
    var hrs = Math.floor(mins / 60)
    if (hrs < 24) return hrs + " h"
    return Math.floor(hrs / 24) + " d"
  }

  function setCategory(cat) {
    if (root.activeCategory === cat) return
    root.activeCategory = cat
    root.fetchArticles()
  }

  function openUrl(url) {
    // Quickshell.openUrl bypasses xdg-open's session env and lands on the
    // wrong browser under Wayland. Run xdg-open through a login shell like
    // Omarchy's Util.execArgv so the session PATH and WAYLAND_DISPLAY apply.
    if (!url) return
    Quickshell.execDetached(["bash", "-lc", 'exec "$@"', "bash", "xdg-open", url])
  }

  function articleAction(id, kind, modelData) {
    httpPost(cdailyApi + "/api/articles/" + id + "/" + kind, function() {
      if (kind === "read" || kind === "unread") {
        root.fetchArticles()
        root.refresh()
      } else if (kind === "star") {
        var arr = []
        for (var i = 0; i < root.articles.length; i++) {
          var a = root.articles[i]
          arr.push(a.id === id ? Object.assign({}, a, { is_starred: !a.is_starred }) : a)
        }
        root.articles = arr
      }
    })
  }

  function summarize(id, container) {
    if (container.busy) return
    container.busy = true
    if (container.text && container.text.length) { container.text = ""; container.busy = false; return }
    container.text = "✨ resumiendo…"
    httpPost(cdailyApi + "/api/articles/" + id + "/summarize", function(d) {
      container.busy = false
      container.text = (d && d.summary) ? d.summary : ((d && d.error) ? ("⚠ " + d.error) : "sin resumen")
    }, function(message) {
      container.busy = false
      container.text = "⚠ " + message
    })
  }

  // Omarchy's ModuleSlot owns pointer gestures and distinguishes drag from click.
  // Expose its click contract so this widget is reorderable like built-ins.
  function open() {
    root.resizedX = -1; root.resizedY = -1
    root.opened = true
    root.refresh()
    root.fetchArticles()
  }

  function close() { root.opened = false }

  function triggerPress(mouseButton) {
    if (mouseButton === Qt.RightButton) refresh()
    else if (root.opened) close()
    else open()
  }

  Timer {
    interval: 30000
    running: true
    repeat: true
    onTriggered: refresh()
  }

  readonly property var btnWindow: button.QsWindow ? button.QsWindow.window : null
  // Screen + dims come from the ANCHOR window (the bar), not from the panel:
  // a freshly-created PanelWindow that hasn't mapped yet has screen == null,
  // which silently zeroes the clamp math and drops the card to the fallback.
  // This mirrors Ui/KeyboardPanel.qml (`screen: anchorWindow ? ... : null`).
  readonly property var anchorScreen: btnWindow ? btnWindow.screen : null
  readonly property real screenW: anchorScreen ? anchorScreen.width : 0
  readonly property real screenH: anchorScreen ? anchorScreen.height : 0
  // Bar thickness: read the bar window's height when available.
  readonly property real barH: btnWindow ? btnWindow.height : 38
  readonly property real gap: 8

  property real preferredW: 640
  property real preferredH: 720
  readonly property real maxCardW: Math.max(1, screenW - 2 * gap)
  readonly property real maxCardH: Math.max(1, screenH - barH - 2 * gap)
  readonly property real minCardW: Math.min(480, maxCardW)
  readonly property real minCardH: Math.min(300, maxCardH)
  readonly property real cardW: Math.max(minCardW, Math.min(preferredW, maxCardW))
  readonly property real cardH: Math.max(minCardH, Math.min(preferredH, maxCardH))
  property real resizedX: -1
  property real resizedY: -1
  property var resizeStart: null
  property bool geometryLoaded: false
  FileView {
    id: geometryFile
    path: root.anchorScreen ? Quickshell.env("HOME") + "/.config/omarchy/cdaily-size-" + encodeURIComponent(root.anchorScreen.name) + ".json" : ""
    atomicWrites: true
    watchChanges: false
    printErrors: false
    onLoaded: {
      if (root.geometryLoaded) return
      root.geometryLoaded = true
      try {
        var d = JSON.parse(text())
        if (typeof d.width === "number" && isFinite(d.width) && d.width > 0) root.preferredW = d.width
        if (typeof d.height === "number" && isFinite(d.height) && d.height > 0) root.preferredH = d.height
      } catch (e) { /* Invalid/missing preferences fall back to 640 × 720. */ }
    }
  }
  function saveSize() {
    if (root.anchorScreen) geometryFile.setText(JSON.stringify({version: 1, width: cardW, height: cardH}) + "\n")
  }
  function resetSize() {
    preferredW = 640; preferredH = 720
    resizedX = -1; resizedY = -1
    saveSize()
  }
  function beginResize(edge, px, py) {
    resizeStart = {edge: edge, px: px, py: py, x: cardX, y: cardY, w: cardW, h: cardH}
  }
  function updateResize(px, py) {
    var s = resizeStart
    if (!s) return
    var dx = px - s.px, dy = py - s.py
    var left = s.x, right = s.x + s.w, top = s.y, bottom = s.y + s.h
    if (s.edge.indexOf("l") >= 0) left = Math.max(gap, Math.min(s.x + dx, right - minCardW))
    if (s.edge.indexOf("r") >= 0) right = Math.min(screenW - gap, Math.max(s.x + s.w + dx, left + minCardW))
    if (s.edge.indexOf("t") >= 0) top = Math.max(gap, Math.min(s.y + dy, bottom - minCardH))
    if (s.edge.indexOf("b") >= 0) bottom = Math.min(screenH - barH - gap, Math.max(s.y + s.h + dy, top + minCardH))
    preferredW = right - left; preferredH = bottom - top
    resizedX = left; resizedY = top
  }
  function finishResize() {
    resizeStart = null
    saveSize()
  }

  // Icon position within the bar's content surface. mapToItem inside a
  // property binding IS reactive to layout changes in QML, matching
  // Ui/KeyboardPanel.qml's anchorScreenPos pattern.
  readonly property real iconScreenX: {
    if (!btnWindow) return -1
    var p = button.mapToItem(btnWindow.contentItem, 0, 0)
    return p.x
  }

  // Card hangs just above the bottom bar (bar sits at the screen's bottom
  // edge — confirmed via `hyprctl layers`: bar y=1414 on a 1440px screen).
  // Horizontal: icon lands ~90px into the card; true centering clamps off-screen
  // because the icon is at the bar's far-left. Clamped to stay on-screen.
  readonly property real cardX: {
    if (resizedX >= 0) return Math.max(gap, Math.min(resizedX, screenW - cardW - gap))
    if (iconScreenX < 0) return gap
    var x = iconScreenX + button.width / 2 - 90
    return Math.max(root.gap, Math.min(x, root.screenW - root.cardW - root.gap))
  }
  readonly property real cardY: {
    if (resizedY >= 0) return Math.max(gap, Math.min(resizedY, screenH - barH - cardH - gap))
    if (iconScreenX < 0) return gap
    var y = root.screenH - root.barH - root.cardH - root.gap
    return Math.max(root.gap, y)
  }

  // ── The panel itself: layer-shell Overlay, full screen ────────────────────
  PanelWindow {
    id: panel
    visible: root.opened
    color: "transparent"
    exclusionMode: ExclusionMode.Ignore

    WlrLayershell.namespace: "cdaily-panel"
    WlrLayershell.layer: WlrLayer.Overlay
    // OnDemand lets the surface take focus when mapped and releases
    // compositor-wide pointer routing so clicks still reach the bar/apps.
    WlrLayershell.keyboardFocus: root.opened ? WlrKeyboardFocus.OnDemand : WlrKeyboardFocus.None

    screen: root.btnWindow && root.btnWindow.screen ? root.btnWindow.screen : null

    anchors {
      top: true
      bottom: true
      left: true
      right: true
    }

    // Dismiss on any click outside the card. The card swallows its own clicks
    // via its MouseArea below (matching Ui/KeyboardPanel.qml).
    MouseArea {
      anchors.fill: parent
      acceptedButtons: Qt.AllButtons
      onClicked: root.opened = false
    }

    // ── The card ─────────────────────────────────────────────────────────
    Rectangle {
      id: panelCard
      objectName: "cdailyCard"
      x: root.cardX
      y: root.cardY
      width: root.cardW
      height: root.cardH
      color: "#0b0d14"
      radius: 12
      border.width: 1
      border.color: "#1f2430"

      // Subtle app-like top glow. Declared FIRST so everything below paints
      // above it — sibling paint order is declaration order in QML.
      Rectangle {
        anchors.left: parent.left; anchors.right: parent.right
        anchors.top: parent.top
        height: 90; radius: 12
        gradient: Gradient {
          GradientStop { position: 0.0; color: Qt.rgba(0.16, 0.22, 0.40, 0.35) }
          GradientStop { position: 1.0; color: "transparent" }
        }
      }

      // Swallow clicks on the card so they don't reach the dismiss area.
      // Interactive children (MouseAreas inside) still get their own events.
      MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.AllButtons
      }

      Column {
        id: contentColumn
        x: 16; y: 14
        width: parent.width - 32
        spacing: 10
        z: 2   // above the swallow-area MouseArea (z beats declaration order)

        // ── Header ──────────────────────────────────────────────────────
        Row {
          width: parent.width
          spacing: 8
          Text {
            text: "📰 CDaily"
            font.pixelSize: 17
            font.bold: true
            color: "#f8fafc"
            anchors.verticalCenter: parent.verticalCenter
          }
          Text {
            id: statusLabel
            width: Math.max(40, parent.width - 230)
            elide: Text.ElideRight
            text: root.loading ? "cargando…" : (root.loadError || ((root.stats.total || 0) + " sin leer"))
            font.pixelSize: 11
            color: "#94a3b8"
            anchors.verticalCenter: parent.verticalCenter
          }
          Item { width: 24; height: 1 }
          Rectangle {
            width: 24; height: 24; radius: 12
            color: resetMA.containsMouse ? "#2b3242" : "#1f2430"
            Text { anchors.centerIn: parent; text: "↺"; color: "#f8fafc"; font.pixelSize: 13 }
            MouseArea {
              id: resetMA
              anchors.fill: parent; hoverEnabled: true
              onClicked: root.resetSize()
              ToolTip.visible: containsMouse
              ToolTip.text: "Restaurar tamaño (640 × 720)"
            }
          }
          Rectangle {
            width: 24; height: 24; radius: 12
            color: refreshMA.containsMouse ? "#2b3242" : "#1f2430"
            anchors.verticalCenter: parent.verticalCenter
            Text { anchors.centerIn: parent; text: "⟳"; font.pixelSize: 13; color: "#f8fafc" }
            MouseArea {
              id: refreshMA
              anchors.fill: parent
              hoverEnabled: true
              onClicked: { root.refresh(); root.fetchArticles() }
            }
          }
        }

        // Category pills wrap when the panel is narrowed.
        Flow {
          width: parent.width
          spacing: 6
          Repeater {
            model: [""].concat(root.catOrder)
            Rectangle {
              width: pillText.width + 16
              height: 24
              radius: 12
              property string catKey: modelData
              property bool active: root.activeCategory === catKey
              property int count: catKey ? ((root.stats.by_category || {})[catKey] || 0)
                                         : (root.stats.total || 0)
              color: active ? root.catColor(catKey) : (pillMA.containsMouse ? "#2b3242" : "#1a1f2b")
              border.width: active ? 0 : 1
              border.color: "#2b3242"
              Text {
                id: pillText
                anchors.centerIn: parent
                text: (catKey ? (root.catLabels[catKey] || catKey) : "Todo")
                      + (count > 0 ? "  " + count : "")
                font.pixelSize: 11
                font.bold: active
                color: active ? "#0b0d14" : "#94a3b8"
              }
              MouseArea {
                id: pillMA
                anchors.fill: parent
                hoverEnabled: true
                onClicked: root.setCategory(catKey)
              }
            }
          }
        }

        Rectangle { width: parent.width; height: 1; color: "#1f2430" }

        // ── Article cards (preview + summary + tags + actions) ───────────
        ListView {
          id: list
          width: parent.width
          objectName: "cdailyArticles"
          height: Math.max(0, root.cardH - contentColumn.y - y - 16)
          clip: true
          spacing: 8
          model: root.articles
          currentIndex: -1
          boundsBehavior: Flickable.StopAtBounds
          property int hoverIndex: -1
          flickableDirection: Flickable.VerticalFlick
          ScrollBar.vertical: ScrollBar {
            policy: ScrollBar.AsNeeded
            width: 6
            contentItem: Rectangle { radius: 3; color: "#2b3242" }
          }
          HoverHandler {
            id: listHover
          }
          // HoverHandler exposes `point` but `contains` is not a signal in
          // this Qt version; when the pointer leaves, onPointChanged fires a
          // final time with a point outside the list, which we map to -1.
          Connections {
            target: listHover
            function onPointChanged() {
              var py = listHover.point.position.y
              var idx = list.indexAt(0, py + list.contentY)
              list.hoverIndex = (idx >= 0 && idx < list.count && py >= 0 && py <= list.height) ? idx : -1
            }
          }

          delegate: Rectangle {
            width: list.width
            height: Math.max(cardCol.height + 16, 96)
            radius: 10
            color: list.hoverIndex === index ? "#171b26" : "#12151d"
            border.width: 1
            border.color: list.hoverIndex === index ? "#2b3242" : "#1f2430"

            // Left accent stripe — category color, app-style.
            Rectangle {
              width: 3; height: parent.height - 12; radius: 2
              anchors.left: parent.left
              anchors.leftMargin: 6
              anchors.verticalCenter: parent.verticalCenter
              color: root.catColor(modelData.category)
              opacity: modelData.is_read ? 0.35 : 1.0
            }

            Row {
              id: cardCol
              x: 18; y: 8
              width: parent.width - 36
              spacing: 10

              // Preview thumbnail (16:9, placeholder until loaded).
              Rectangle {
                width: 116; height: 66
                radius: 6
                anchors.verticalCenter: parent.verticalCenter
                color: "#1a1f2b"
                clip: true
                Image {
                  id: thumbnail
                  anchors.fill: parent
                  visible: status === Image.Ready
                  source: root.thumbnailSources[modelData.image_url] || ""
                  fillMode: Image.PreserveAspectCrop
                  asynchronous: true
                  cache: true
                  sourceSize.width: 116
                  sourceSize.height: 66
                }
                Text {
                  anchors.centerIn: parent
                  visible: thumbnail.status !== Image.Ready
                  text: modelData.emoji || "📰"
                  font.pixelSize: 22
                }
                MouseArea {
                  anchors.fill: parent
                  cursorShape: Qt.PointingHandCursor
                  onClicked: {
                    root.articleAction(modelData.id, "read", modelData)
                    root.openUrl(modelData.url)
                  }
                }
              }

              Column {
                width: cardCol.width - 116 - 10 - 34   // thumb + gap + star col
                spacing: 3
                anchors.verticalCenter: parent.verticalCenter

                Row {
                  spacing: 5
                  Text {
                    text: modelData.blog_name || ""
                    font.pixelSize: 10
                    color: root.catColor(modelData.category)
                    font.bold: true
                    elide: Text.ElideRight
                    maximumLineCount: 1
                    anchors.verticalCenter: parent.verticalCenter
                  }
                  Text {
                    text: "· " + (modelData.timeLabel || "")
                    font.pixelSize: 10
                    color: "#64748b"
                    anchors.verticalCenter: parent.verticalCenter
                  }
                  Rectangle {
                    width: 3; height: 3; radius: 2
                    color: "#64748b"
                    anchors.verticalCenter: parent.verticalCenter
                  }
                  Text {
                    text: "★".repeat(modelData.user_rating || 0)
                    font.pixelSize: 9
                    color: "#f9e2af"
                    visible: modelData.user_rating > 0
                    anchors.verticalCenter: parent.verticalCenter
                  }
                }

                Text {
                  width: parent.width
                  text: modelData.title || ""
                  font.pixelSize: 13
                  font.bold: true
                  color: modelData.is_read ? "#94a3b8" : "#f8fafc"
                  wrapMode: Text.Wrap
                  maximumLineCount: 2
                  elide: Text.ElideRight
                  MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                      root.articleAction(modelData.id, "read", modelData)
                      root.openUrl(modelData.url)
                    }
                  }
                }

                // Inline AI summary slot (shared across delegates — no nested delegates).
                Item {
                  id: summaryBox
                  width: parent.width
                  implicitHeight: summaryText.implicitHeight + 10
                  height: (summaryBox.text || summaryBox.busy) ? summaryBox.implicitHeight + 6 : 0
                  clip: true
                  visible: height > 0
                  Behavior on height { NumberAnimation { duration: 140; easing.type: Easing.OutQuad } }
                  property alias text: summaryText.text
                  property alias busy: summaryText.busy
                  Rectangle {
                    anchors.fill: parent
                    anchors.topMargin: 3
                    color: "#0e1118"
                    radius: 6
                    border.width: 1
                    border.color: "#1f2430"
                    Text {
                      id: summaryText
                      property bool busy: false
                      x: 8; y: 5
                      width: parent.width - 16
                      text: ""
                      font.pixelSize: 11
                      color: "#a6e3a1"
                      wrapMode: Text.Wrap
                      maximumLineCount: 4
                      elide: Text.ElideRight
                    }
                  }
                }

                // Topic tags (first 3, app-style).
                Row {
                  visible: modelData.categories && modelData.categories.length > 0
                  spacing: 4
                  Repeater {
                    model: (modelData.categories || []).slice(0, 3)
                    Rectangle {
                      height: 16; radius: 8
                      width: tagText.width + 10
                      color: Qt.rgba(0.42, 0.45, 0.55, 0.25)
                      Text {
                        id: tagText
                        anchors.centerIn: parent
                        text: modelData
                        font.pixelSize: 9
                        color: "#94a3b8"
                      }
                    }
                  }
                }
              }

              // Action column: ✨ summarize · ★ star · ✕ read
              Column {
                spacing: 4
                anchors.verticalCenter: parent.verticalCenter
                Text {
                  text: "✨"
                  font.pixelSize: 13
                  color: sumMA.containsMouse ? "#a6e3a1" : "#64748b"
                  opacity: modelData.summary ? 1.0 : 0.8
                  MouseArea {
                    id: sumMA
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.summarize(modelData.id, summaryBox)
                  }
                }
                Text {
                  text: "★"
                  font.pixelSize: 13
                  color: modelData.is_starred ? "#f9e2af" : (starMA.containsMouse ? "#94a3b8" : "#64748b")
                  MouseArea {
                    id: starMA
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.articleAction(modelData.id, "star", modelData)
                  }
                }
                Text {
                  text: "✕"
                  font.pixelSize: 11
                  color: modelData.is_read ? "#64748b" : (doneMA.containsMouse ? "#f38ba8" : "#475569")
                  MouseArea {
                    id: doneMA
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.articleAction(modelData.id,
                                                  modelData.is_read ? "unread" : "read", modelData)
                  }
                }
              }
            }

            // NO full-card MouseArea here: a delegate-sized MouseArea captures
            // the wheel event before the Flickable sees it and the list cannot
            // scroll. Hover feedback comes from the ListView's HoverHandler
            // (hoverIndex) instead; clicks go to the inner MouseAreas only.
          }

          // Empty state
          Text {
            anchors.centerIn: parent
            visible: root.articles.length === 0 && !root.loading
            text: root.loadError || "Todo al día 🌿"
            font.pixelSize: 13
            color: "#64748b"
          }
        }
      }
      // Thin border-only hit areas: never intercept article wheel/clicks.
      Repeater {
        model: ["l", "r", "t", "b", "lt", "rt", "lb", "rb"]
        MouseArea {
          required property string modelData
          readonly property bool corner: modelData.length === 2
          readonly property bool horizontal: modelData === "t" || modelData === "b"
          x: modelData.indexOf("r") >= 0 ? panelCard.width - width : (horizontal ? 16 : 0)
          y: modelData.indexOf("b") >= 0 ? panelCard.height - height : (!corner && !horizontal ? 16 : 0)
          width: corner ? 16 : (horizontal ? panelCard.width - 32 : 8)
          height: corner ? 16 : (horizontal ? 8 : panelCard.height - 32)
          z: 20
          hoverEnabled: true
          acceptedButtons: Qt.LeftButton
          preventStealing: true
          cursorShape: corner ? ((modelData === "lt" || modelData === "rb") ? Qt.SizeFDiagCursor : Qt.SizeBDiagCursor) : (horizontal ? Qt.SizeVerCursor : Qt.SizeHorCursor)
          onPressed: function(mouse) {
            var p = mapToItem(panel.contentItem, mouse.x, mouse.y)
            root.beginResize(modelData, p.x, p.y)
          }
          onPositionChanged: function(mouse) {
            if (!pressed) return
            var p = mapToItem(panel.contentItem, mouse.x, mouse.y)
            root.updateResize(p.x, p.y)
          }
          onReleased: root.finishResize()
          onCanceled: root.finishResize()
          onDoubleClicked: root.resetSize()
          ToolTip.visible: containsMouse && !pressed
          ToolTip.delay: 600
          ToolTip.text: "Arrastra para cambiar tamaño · doble clic para restaurar"
        }
      }
      Text {
        anchors.right: parent.right; anchors.top: parent.top
        anchors.rightMargin: 5; anchors.topMargin: 2
        text: "◥"; color: "#64748b"; font.pixelSize: 11
      }
    }
  }

  Rectangle {
    id: button
    anchors.fill: parent
    radius: 6
    property bool hovered: false
    color: button.hovered ? Qt.rgba(1, 1, 1, 0.08) : "transparent"

    Text {
      anchors.centerIn: parent
      text: "📰"
      font.pixelSize: 14
      color: root.opened ? "#f9e2af" : "#cdd6f4"
    }

    Rectangle {
      x: parent.width - 12
      y: -2
      width: badgeText.width + 8
      height: 16
      radius: 8
      visible: root.unreadCount > 0
      color: "#f38ba8"
      Text {
        id: badgeText
        anchors.centerIn: parent
        text: root.unreadCount > 99 ? "99+" : root.unreadCount
        font.pixelSize: 9
        font.bold: true
        color: "#0b0d14"
      }
    }

    HoverHandler {
      onHoveredChanged: button.hovered = hovered
    }
  }

  Component.onCompleted: refresh()
}
