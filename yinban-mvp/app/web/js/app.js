(function () {
  "use strict";

  var elements = {
    modeLabel: document.getElementById("mode-label"),
    connectionDot: document.getElementById("connection-dot"),
    recognizedText: document.getElementById("recognized-text"),
    answerText: document.getElementById("answer-text"),
    routeTitle: document.getElementById("route-title"),
    routeSteps: document.getElementById("route-steps"),
    routeNote: document.getElementById("route-note"),
    robotState: document.getElementById("robot-state"),
    robotDetail: document.getElementById("robot-detail"),
    startButton: document.getElementById("start-button"),
    voiceButton: document.getElementById("voice-button"),
    voiceLabel: document.getElementById("voice-label"),
    queryInput: document.getElementById("query-input"),
    queryForm: document.getElementById("query-form"),
    routeHighlights: document.querySelectorAll(".route-highlight"),
    guideMarker: document.getElementById("guide-marker"),
    mapDescription: document.getElementById("map-description"),
    mapFloors: document.querySelectorAll(".map-floor"),
    floorTabs: document.querySelectorAll(".floor-tab"),
    floorSummary: document.getElementById("floor-summary"),
    elevatorTransition: document.getElementById("elevator-transition"),
    elevatorTransitionTitle: document.getElementById("elevator-transition-title"),
    elevatorTransitionDetail: document.getElementById("elevator-transition-detail"),
    toast: document.getElementById("toast")
  };

  var activeGuideRouteId = null;
  var guideAvailable = false;
  var guideInProgress = false;
  var currentMode = null;
  var currentRoute = [];
  var currentRoutePoints = [];
  var currentDestinationNames = [];
  var currentFloor = 1;
  var currentFloorSequence = [];
  var currentPhysicalHandoffNodeId = null;
  var currentGuideProgress = 0;
  var lastProgressUpdateAt = null;
  var listening = false;
  var toastTimer = null;
  var lastRobotState = null;
  var lastElevatorTransitionKey = null;
  var screenContinuationFrame = null;
  var screenContinuationStarted = false;

  var stateLabels = {
    IDLE: "等待任务",
    MOVING: "正在导引",
    BLOCKED: "前方有障碍，已停车",
    LINE_LOST: "路线丢失，已停车",
    ARRIVED: "已经到达",
    ERROR: "机器人故障"
  };

  async function api(path, options) {
    var response = await fetch(path, options || {});
    var payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "请求失败");
    }
    return payload;
  }

  function showToast(message, isError) {
    window.clearTimeout(toastTimer);
    elements.toast.textContent = message;
    elements.toast.className = "toast visible" + (isError ? " error" : "");
    toastTimer = window.setTimeout(function () {
      elements.toast.className = "toast";
    }, 3200);
  }

  function speak(text) {
    if (!("speechSynthesis" in window) || !text) {
      return;
    }
    window.speechSynthesis.cancel();
    var utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = "zh-CN";
    utterance.rate = 0.82;
    utterance.pitch = 1;
    window.speechSynthesis.speak(utterance);
  }

  function updateStartButton() {
    elements.startButton.disabled = !guideAvailable;
    var simulation = currentMode === "simulation" || activeGuideRouteId === "SIMULATION";
    if (guideAvailable && simulation) {
      elements.startButton.textContent = "开始模拟导引";
    } else if (guideAvailable) {
      elements.startButton.textContent = "开始实体导引";
    } else if (currentRoute.length) {
      elements.startButton.textContent = "该路线暂无实体导引";
    } else {
      elements.startButton.textContent = "开始导引";
    }
  }

  function floorName(floor) {
    var names = {1: "一楼", 2: "二楼", 3: "三楼"};
    return names[Number(floor)] || String(floor) + "楼";
  }

  function floorSequence(routePoints) {
    var floors = [];
    (routePoints || []).forEach(function (point) {
      var floor = Number(point.floor);
      if (!floors.length || floors[floors.length - 1] !== floor) {
        floors.push(floor);
      }
    });
    return floors;
  }

  function updateFloorSummary() {
    var routeText = currentFloorSequence.length
      ? "路线楼层：" + currentFloorSequence.map(floorName).join(" → ") + " · "
      : "";
    elements.floorSummary.textContent = routeText + "当前显示：" + floorName(currentFloor);
  }

  function showFloor(floor) {
    currentFloor = Number(floor) || 1;
    elements.mapFloors.forEach(function (layer) {
      var active = Number(layer.getAttribute("data-floor")) === currentFloor;
      layer.classList.toggle("is-hidden", !active);
      layer.setAttribute("aria-hidden", active ? "false" : "true");
    });
    elements.floorTabs.forEach(function (button) {
      var active = Number(button.getAttribute("data-floor")) === currentFloor;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
    });
    updateFloorSummary();
  }

  function hideElevatorTransition() {
    elements.elevatorTransition.hidden = true;
    lastElevatorTransitionKey = null;
  }

  function showElevatorTransition(fromFloor, toFloor) {
    var direction = Number(toFloor) > Number(fromFloor) ? "前往" : "返回";
    elements.elevatorTransitionTitle.textContent =
      "正在乘坐3号电梯" + direction + floorName(toFloor);
    elements.elevatorTransitionDetail.textContent =
      floorName(fromFloor) + " → " + floorName(toFloor);
    elements.elevatorTransition.hidden = false;
    var transitionKey = String(fromFloor) + "-" + String(toFloor);
    if (lastElevatorTransitionKey !== transitionKey) {
      speak(
        "已进入三号电梯，正在" + direction + floorName(toFloor) + "。"
      );
      lastElevatorTransitionKey = transitionKey;
    }
  }

  function renderMap(routePoints, destinationNames) {
    currentRoutePoints = routePoints || [];
    currentDestinationNames = destinationNames || [];
    currentFloorSequence = floorSequence(currentRoutePoints);
    document.querySelectorAll(".map-node").forEach(function (node) {
      node.classList.remove("on-route", "destination", "current");
    });
    elements.routeHighlights.forEach(function (highlight) {
      highlight.setAttribute("points", "");
      highlight.classList.remove("visible");
    });
    hideElevatorTransition();

    if (!currentRoutePoints.length) {
      elements.guideMarker.classList.remove("visible");
      elements.mapDescription.textContent = "选择目的地后，这里会按实际道路突出显示路线。";
      currentFloorSequence = [];
      showFloor(1);
      return;
    }

    elements.routeHighlights.forEach(function (highlight) {
      var floor = Number(highlight.getAttribute("data-floor"));
      var points = currentRoutePoints.filter(function (point) {
        return Number(point.floor) === floor;
      });
      if (points.length >= 2) {
        highlight.setAttribute(
          "points",
          points.map(function (point) {
            return point.x + "," + point.y;
          }).join(" ")
        );
        highlight.classList.add("visible");
      }
    });
    currentRoutePoints.forEach(function (point) {
      var node = document.querySelector('.map-node[data-node="' + point.node_id + '"]');
      if (node) {
        node.classList.add("on-route");
        if (currentDestinationNames.indexOf(point.label) >= 0) {
          node.classList.add("destination");
        }
      }
    });
    elements.mapDescription.textContent = "当前路线：" + currentRoute.join("，然后前往");
    elements.guideMarker.classList.add("visible");
    showFloor(currentRoutePoints[0].floor);
    setGuideProgress(0, "IDLE");
  }

  function segmentLength(start, end) {
    if (Number(start.floor) !== Number(end.floor)) {
      return 190;
    }
    return Math.max(60, Math.hypot(end.x - start.x, end.y - start.y));
  }

  function routeMetrics() {
    var lengths = [];
    var total = 0;
    for (var index = 1; index < currentRoutePoints.length; index += 1) {
      var length = segmentLength(currentRoutePoints[index - 1], currentRoutePoints[index]);
      lengths.push(length);
      total += length;
    }
    return {lengths: lengths, total: total};
  }

  function stepIndexForPoint(pointIndex) {
    var stepIndex = 0;
    for (var index = 0; index < pointIndex; index += 1) {
      stepIndex += Number(currentRoutePoints[index].floor) !==
        Number(currentRoutePoints[index + 1].floor) ? 2 : 1;
    }
    return stepIndex;
  }

  function progressAtPoint(pointIndex) {
    if (pointIndex <= 0 || currentRoutePoints.length < 2) {
      return 0;
    }
    var metrics = routeMetrics();
    if (!metrics.total) {
      return 0;
    }
    var travelled = metrics.lengths.slice(0, pointIndex).reduce(function (sum, value) {
      return sum + value;
    }, 0);
    return Math.min(1, travelled / metrics.total);
  }

  function routePosition(progress) {
    if (!currentRoutePoints.length) {
      return null;
    }
    if (currentRoutePoints.length === 1) {
      return {
        x: currentRoutePoints[0].x,
        y: currentRoutePoints[0].y,
        floor: currentRoutePoints[0].floor,
        nodeIndex: 0,
        stepIndex: 0,
        transition: null
      };
    }

    var metrics = routeMetrics();
    var target = Math.max(0, Math.min(1, progress)) * metrics.total;
    var travelled = 0;
    for (var segment = 0; segment < metrics.lengths.length; segment += 1) {
      var nextTravelled = travelled + metrics.lengths[segment];
      if (target <= nextTravelled || segment === metrics.lengths.length - 1) {
        var ratio = metrics.lengths[segment] === 0
          ? 1
          : Math.max(0, Math.min(1, (target - travelled) / metrics.lengths[segment]));
        var start = currentRoutePoints[segment];
        var end = currentRoutePoints[segment + 1];
        var changesFloor = Number(start.floor) !== Number(end.floor);
        if (changesFloor) {
          var onTargetFloor = ratio >= 0.5;
          return {
            x: onTargetFloor ? end.x : start.x,
            y: onTargetFloor ? end.y : start.y,
            floor: onTargetFloor ? end.floor : start.floor,
            nodeIndex: ratio >= 0.98 ? segment + 1 : segment,
            stepIndex: stepIndexForPoint(segment) + 1,
            transition: {fromFloor: start.floor, toFloor: end.floor}
          };
        }
        return {
          x: start.x + (end.x - start.x) * ratio,
          y: start.y + (end.y - start.y) * ratio,
          floor: start.floor,
          nodeIndex: ratio >= 0.98 ? segment + 1 : segment,
          stepIndex: ratio >= 0.98
            ? stepIndexForPoint(segment + 1)
            : stepIndexForPoint(segment),
          transition: null
        };
      }
      travelled = nextTravelled;
    }
    return null;
  }

  function setGuideProgress(progress, state) {
    if (!currentRoutePoints.length) {
      return;
    }
    currentGuideProgress = Math.max(0, Math.min(1, Number(progress) || 0));
    var position = routePosition(currentGuideProgress);
    if (!position) {
      return;
    }
    showFloor(position.floor);
    if (position.transition) {
      showElevatorTransition(
        position.transition.fromFloor,
        position.transition.toFloor
      );
    } else {
      hideElevatorTransition();
    }
    elements.guideMarker.style.transform =
      "translate(" + position.x + "px, " + position.y + "px)";
    document.querySelectorAll(".map-node").forEach(function (node) {
      node.classList.remove("current");
    });
    var currentPoint = currentRoutePoints[position.nodeIndex];
    if (currentPoint) {
      var currentNode = document.querySelector(
        '.map-node[data-node="' + currentPoint.node_id + '"]'
      );
      if (currentNode) {
        currentNode.classList.add("current");
      }
    }
    markRouteProgress(position.stepIndex, state);
  }

  function cancelScreenContinuation() {
    if (screenContinuationFrame !== null) {
      window.cancelAnimationFrame(screenContinuationFrame);
    }
    screenContinuationFrame = null;
    screenContinuationStarted = false;
    hideElevatorTransition();
  }

  function beginScreenContinuation() {
    var handoffIndex = currentRoutePoints.findIndex(function (point) {
      return point.node_id === currentPhysicalHandoffNodeId;
    });
    if (handoffIndex < 0 || handoffIndex >= currentRoutePoints.length - 1) {
      return;
    }
    var startProgress = progressAtPoint(handoffIndex);
    var startedAt = null;
    var duration = Math.max(5000, (currentRoutePoints.length - handoffIndex) * 1800);
    screenContinuationStarted = true;
    elements.routeNote.textContent =
      "实体小车已在一楼3号电梯入口停车，后续乘梯和三楼路线正在由屏幕模拟。";
    showToast("已到达电梯交接点，继续屏幕跨楼层导引。", false);
    speak("实体小车已到达三号电梯入口。现在乘坐电梯前往三楼，后续路线由屏幕继续引导。");

    function animate(timestamp) {
      if (startedAt === null) {
        startedAt = timestamp;
      }
      var ratio = Math.min(1, (timestamp - startedAt) / duration);
      var progress = startProgress + (1 - startProgress) * ratio;
      setGuideProgress(progress, ratio >= 1 ? "ARRIVED" : "MOVING");
      if (ratio < 1) {
        screenContinuationFrame = window.requestAnimationFrame(animate);
      } else {
        screenContinuationFrame = null;
        guideInProgress = false;
        hideElevatorTransition();
        var arrivedAt = currentDestinationNames.length
          ? currentDestinationNames[currentDestinationNames.length - 1]
          : "目的地";
        elements.robotState.textContent = "屏幕导引已到达";
        speak("已经到达" + arrivedAt + "，请留意门牌和现场工作人员指引。");
      }
    }

    screenContinuationFrame = window.requestAnimationFrame(animate);
  }

  function renderRoute(
    route,
    destination,
    physicalAvailable,
    destinationNames,
    routePoints,
    canGuide,
    physicalHandoffNodeId
  ) {
    cancelScreenContinuation();
    currentRoute = route || [];
    currentPhysicalHandoffNodeId = physicalHandoffNodeId || null;
    guideAvailable = Boolean(canGuide);
    guideInProgress = false;
    currentGuideProgress = 0;
    lastProgressUpdateAt = null;
    elements.routeSteps.innerHTML = "";
    if (!currentRoute.length) {
      var empty = document.createElement("li");
      empty.className = "empty-step";
      empty.textContent = "当前问题不需要规划路线。";
      elements.routeSteps.appendChild(empty);
      elements.routeTitle.textContent = "就医流程问询";
      elements.routeNote.textContent = "您可以继续提问或选择一个目的地。";
      renderMap([], []);
      updateStartButton();
      return;
    }

    elements.routeTitle.textContent = destinationNames && destinationNames.length > 1
      ? "依次前往：" + destinationNames.join(" → ")
      : "前往" + destination;
    currentRoute.forEach(function (label, index) {
      var item = document.createElement("li");
      item.textContent = label;
      if (label.indexOf("乘坐3号电梯") === 0) {
        item.classList.add("elevator-step");
      }
      if (index === 0) {
        item.classList.add("active");
      }
      elements.routeSteps.appendChild(item);
    });
    renderMap(routePoints, destinationNames);
    var floorText = currentFloorSequence.length > 1
      ? "楼层顺序：" + currentFloorSequence.map(floorName).join(" → ") + "。"
      : "当前路线位于" + floorName(currentFloorSequence[0] || 1) + "。";
    var simulation = currentMode === "simulation" || activeGuideRouteId === "SIMULATION";
    if (guideAvailable && simulation) {
      elements.routeNote.textContent =
        floorText + "点击开始后，地图会在电梯处提示上下楼并自动切换楼层。";
    } else if (physicalAvailable && currentPhysicalHandoffNodeId) {
      elements.routeNote.textContent =
        floorText + "实体小车只运行至一楼电梯入口，乘梯和三楼路线由屏幕继续模拟。";
    } else if (physicalAvailable) {
      elements.routeNote.textContent = floorText + "此路线支持实体小车；地图进度为位置示意。";
    } else {
      elements.routeNote.textContent = floorText + "路线已正确显示，但实体小车尚未配置这条路线。";
    }
    updateStartButton();
  }

  function markRouteProgress(reachedIndex, state) {
    var steps = elements.routeSteps.querySelectorAll("li:not(.empty-step)");
    if (!steps.length) {
      return;
    }
    steps.forEach(function (step) {
      step.classList.remove("active");
    });
    if (state === "ARRIVED") {
      steps.forEach(function (step) {
        step.classList.add("active");
      });
    } else {
      for (var index = 0; index <= Math.min(reachedIndex, steps.length - 1); index += 1) {
        steps[index].classList.add("active");
      }
    }
  }

  async function submitQuery(text, autoStart) {
    var cleanText = (text || "").trim();
    if (!cleanText) {
      showToast("请先说出或输入您的需求。", true);
      return;
    }
    elements.recognizedText.textContent = "您说：“" + cleanText + "”";
    elements.answerText.textContent = "正在查询，请稍候……";
    try {
      var result = await api("/api/dialogue", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({text: cleanText})
      });
      elements.answerText.textContent = result.answer;
      activeGuideRouteId = result.guide_route_id;
      var destinationName = result.route.length
        ? result.route[result.route.length - 1]
        : "";
      renderRoute(
        result.route,
        destinationName,
        result.physical_available,
        result.destination_names,
        result.route_points,
        result.guide_available,
        result.physical_handoff_node_id
      );
      speak(result.answer);
      if (result.intent === "help") {
        showToast("已触发本地求助提醒，请联系现场工作人员。", true);
      }
      if (autoStart && result.guide_available) {
        await startRobot();
      }
    } catch (error) {
      elements.answerText.textContent = "系统暂时无法处理，请使用下方大按钮或联系工作人员。";
      showToast(error.message, true);
    }
  }

  async function robotCommand(action, payload) {
    var options = {method: "POST"};
    if (payload) {
      options.headers = {"Content-Type": "application/json"};
      options.body = JSON.stringify(payload);
    }
    var result = await api("/api/robot/" + action, options);
    showToast(result.message, !result.accepted);
    return result;
  }

  async function startRobot() {
    if (!guideAvailable || !activeGuideRouteId) {
      showToast("请先选择一条可导引路线。", true);
      return;
    }
    try {
      cancelScreenContinuation();
      lastRobotState = null;
      var result = await robotCommand("start", {
        routeId: activeGuideRouteId,
        stepCount: Math.max(2, currentRoutePoints.length)
      });
      if (result.accepted) {
        guideInProgress = true;
        lastProgressUpdateAt = Date.now();
        setGuideProgress(0, "MOVING");
      }
    } catch (error) {
      showToast(error.message, true);
    }
  }

  async function pollRobotStatus() {
    try {
      var status = await api("/api/robot/status");
      currentMode = status.mode;
      elements.connectionDot.classList.toggle("connected", status.connected);
      elements.modeLabel.textContent =
        status.mode === "hardware" ? "真实硬件模式" : "模拟演示模式";
      elements.robotState.textContent = stateLabels[status.state] || status.state;
      var details = [];
      if (status.route_id) {
        details.push(
          status.route_id === "SIMULATION"
            ? "路线：当前屏幕规划"
            : "路线：" + status.route_id
        );
      }
      if (status.distance_cm !== null) {
        details.push("障碍距离：" + status.distance_cm + " cm");
      }
      if (status.error) {
        details.push(status.error);
      }
      elements.robotDetail.textContent =
        details.join(" · ") || "系统已就绪，可以开始导引。";
      if (screenContinuationFrame !== null) {
        elements.robotState.textContent = "屏幕继续导引";
        elements.robotDetail.textContent = "实体小车已在电梯入口停车，正在模拟跨楼层路线。";
      }
      if (status.route_id === "CARDIOLOGY" && currentRoute.length === 0) {
        var restoredRoute = await api("/api/navigation/cardiology");
        activeGuideRouteId = restoredRoute.robot_route_id;
        renderRoute(
          restoredRoute.labels,
          restoredRoute.destination_name,
          restoredRoute.physical_available,
          [restoredRoute.destination_name],
          restoredRoute.points,
          restoredRoute.physical_available,
          restoredRoute.physical_handoff_node_id
        );
        guideInProgress = status.state !== "IDLE";
      }

      updateStartButton();
      if (
        guideInProgress &&
        currentRoutePoints.length &&
        screenContinuationFrame === null
      ) {
        var now = Date.now();
        var progress = status.progress;
        if (progress === null || progress === undefined) {
          if (status.state === "ARRIVED") {
            progress = 1;
          } else if (status.state === "MOVING") {
            var elapsed = lastProgressUpdateAt ? now - lastProgressUpdateAt : 0;
            progress = Math.min(0.92, currentGuideProgress + elapsed / 15000);
          } else {
            progress = currentGuideProgress;
          }
        }
        var displayState = status.state;
        if (currentMode === "hardware" && currentPhysicalHandoffNodeId) {
          var handoffIndex = currentRoutePoints.findIndex(function (point) {
            return point.node_id === currentPhysicalHandoffNodeId;
          });
          if (handoffIndex >= 0) {
            progress *= progressAtPoint(handoffIndex);
            if (status.state === "ARRIVED") {
              displayState = "MOVING";
            }
          }
        }
        setGuideProgress(progress, displayState);
        lastProgressUpdateAt = now;
      }
      if (
        guideInProgress &&
        status.state === "ARRIVED" &&
        lastRobotState !== "ARRIVED"
      ) {
        if (
          currentMode === "hardware" &&
          currentPhysicalHandoffNodeId &&
          !screenContinuationStarted
        ) {
          beginScreenContinuation();
        } else {
          var arrivedAt = currentDestinationNames.length
            ? currentDestinationNames[currentDestinationNames.length - 1]
            : "目的地";
          speak("已经到达" + arrivedAt + "，请留意门牌和现场工作人员指引。");
        }
      }
      lastRobotState = status.state;
    } catch (error) {
      elements.connectionDot.classList.remove("connected");
      elements.modeLabel.textContent = "后端连接失败";
      elements.robotState.textContent = "系统离线";
      elements.robotDetail.textContent = "请确认银伴服务已经启动。";
    }
  }

  function setupSpeechRecognition() {
    var Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Recognition) {
      elements.voiceButton.disabled = true;
      elements.voiceLabel.textContent = "此浏览器不支持语音，请使用按钮或文字";
      return;
    }
    var recognition = new Recognition();
    recognition.lang = "zh-CN";
    recognition.interimResults = false;
    recognition.continuous = false;

    recognition.onstart = function () {
      listening = true;
      elements.voiceButton.classList.add("listening");
      elements.voiceLabel.textContent = "正在听，请说话……";
    };
    recognition.onend = function () {
      listening = false;
      elements.voiceButton.classList.remove("listening");
      elements.voiceLabel.textContent = "按一下，开始说话";
    };
    recognition.onerror = function () {
      showToast("没有听清楚，请再试一次或使用文字输入。", true);
    };
    recognition.onresult = function (event) {
      var text = event.results[0][0].transcript;
      elements.queryInput.value = text;
      submitQuery(text, false);
    };

    elements.voiceButton.addEventListener("click", function () {
      if (listening) {
        recognition.stop();
      } else {
        recognition.start();
      }
    });
  }

  document.querySelectorAll("[data-query]").forEach(function (button) {
    button.addEventListener("click", function () {
      submitQuery(button.getAttribute("data-query"), false);
    });
  });

  elements.floorTabs.forEach(function (button) {
    button.addEventListener("click", function () {
      showFloor(button.getAttribute("data-floor"));
    });
  });

  elements.queryForm.addEventListener("submit", function (event) {
    event.preventDefault();
    submitQuery(elements.queryInput.value, false);
  });

  document.getElementById("demo-button").addEventListener("click", function () {
    submitQuery("我要去心内科", true);
  });
  elements.startButton.addEventListener("click", startRobot);
  document.getElementById("resume-button").addEventListener("click", function () {
    robotCommand("resume").then(function (result) {
      if (result.accepted) {
        guideInProgress = true;
        lastProgressUpdateAt = Date.now();
      }
    }).catch(function (error) {
      showToast(error.message, true);
    });
  });
  document.getElementById("stop-button").addEventListener("click", function () {
    robotCommand("stop").then(function (result) {
      if (result.accepted) {
        cancelScreenContinuation();
        guideInProgress = false;
      }
    }).catch(function (error) {
      showToast(error.message, true);
    });
  });
  document.getElementById("reset-button").addEventListener("click", function () {
    robotCommand("reset").then(function (result) {
      if (result.accepted) {
        cancelScreenContinuation();
        guideInProgress = false;
        lastProgressUpdateAt = null;
        setGuideProgress(0, "IDLE");
        updateStartButton();
      }
    }).catch(function (error) {
      showToast(error.message, true);
    });
  });

  setupSpeechRecognition();
  pollRobotStatus();
  window.setInterval(pollRobotStatus, 500);
})();
