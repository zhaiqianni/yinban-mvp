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
    routeHighlight: document.getElementById("route-highlight"),
    guideMarker: document.getElementById("guide-marker"),
    mapDescription: document.getElementById("map-description"),
    toast: document.getElementById("toast")
  };

  var activeGuideRouteId = null;
  var guideAvailable = false;
  var guideInProgress = false;
  var currentMode = null;
  var currentRoute = [];
  var currentRoutePoints = [];
  var currentDestinationNames = [];
  var currentGuideProgress = 0;
  var lastProgressUpdateAt = null;
  var listening = false;
  var toastTimer = null;
  var lastRobotState = null;

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

  function renderMap(routePoints, destinationNames) {
    currentRoutePoints = routePoints || [];
    currentDestinationNames = destinationNames || [];
    document.querySelectorAll(".map-node").forEach(function (node) {
      node.classList.remove("on-route", "destination", "current");
    });

    if (!currentRoutePoints.length) {
      elements.routeHighlight.setAttribute("points", "");
      elements.routeHighlight.classList.remove("visible");
      elements.guideMarker.classList.remove("visible");
      elements.mapDescription.textContent = "选择目的地后，这里会按实际道路突出显示路线。";
      return;
    }

    elements.routeHighlight.setAttribute(
      "points",
      currentRoutePoints.map(function (point) {
        return point.x + "," + point.y;
      }).join(" ")
    );
    elements.routeHighlight.classList.add("visible");
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
    setGuideProgress(0, "IDLE");
  }

  function routePosition(progress) {
    if (!currentRoutePoints.length) {
      return null;
    }
    if (currentRoutePoints.length === 1) {
      return {x: currentRoutePoints[0].x, y: currentRoutePoints[0].y, nodeIndex: 0};
    }

    var lengths = [];
    var total = 0;
    for (var index = 1; index < currentRoutePoints.length; index += 1) {
      var previous = currentRoutePoints[index - 1];
      var current = currentRoutePoints[index];
      var length = Math.hypot(current.x - previous.x, current.y - previous.y);
      lengths.push(length);
      total += length;
    }

    var target = Math.max(0, Math.min(1, progress)) * total;
    var travelled = 0;
    for (var segment = 0; segment < lengths.length; segment += 1) {
      var nextTravelled = travelled + lengths[segment];
      if (target <= nextTravelled || segment === lengths.length - 1) {
        var ratio = lengths[segment] === 0
          ? 1
          : (target - travelled) / lengths[segment];
        var start = currentRoutePoints[segment];
        var end = currentRoutePoints[segment + 1];
        return {
          x: start.x + (end.x - start.x) * ratio,
          y: start.y + (end.y - start.y) * ratio,
          nodeIndex: ratio >= 0.98 ? segment + 1 : segment
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
    markRouteProgress(position.nodeIndex, state);
  }

  function renderRoute(
    route,
    destination,
    physicalAvailable,
    destinationNames,
    routePoints,
    canGuide
  ) {
    currentRoute = route || [];
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
      if (index === 0) {
        item.classList.add("active");
      }
      elements.routeSteps.appendChild(item);
    });
    var simulation = currentMode === "simulation" || activeGuideRouteId === "SIMULATION";
    if (guideAvailable && simulation) {
      elements.routeNote.textContent = "此路线支持屏幕模拟导引，点击按钮可查看图标沿实际路线移动。";
    } else if (physicalAvailable) {
      elements.routeNote.textContent = "此路线支持实体小车；地图进度为位置示意。";
    } else {
      elements.routeNote.textContent = "路线已正确显示，但实体小车尚未配置这条路线。";
    }
    renderMap(routePoints, destinationNames);
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
      for (var index = 0; index <= reachedIndex; index += 1) {
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
        result.guide_available
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
      if (status.route_id === "CARDIOLOGY" && currentRoute.length === 0) {
        var restoredRoute = await api("/api/navigation/cardiology");
        activeGuideRouteId = restoredRoute.robot_route_id;
        renderRoute(
          restoredRoute.labels,
          restoredRoute.destination_name,
          restoredRoute.physical_available,
          [restoredRoute.destination_name],
          restoredRoute.points,
          restoredRoute.physical_available
        );
        guideInProgress = status.state !== "IDLE";
      }

      updateStartButton();
      if (guideInProgress && currentRoutePoints.length) {
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
        setGuideProgress(progress, status.state);
        lastProgressUpdateAt = now;
      }
      if (
        guideInProgress &&
        status.state === "ARRIVED" &&
        lastRobotState !== "ARRIVED"
      ) {
        var arrivedAt = currentDestinationNames.length
          ? currentDestinationNames[currentDestinationNames.length - 1]
          : "目的地";
        speak("已经到达" + arrivedAt + "，请留意门牌和现场工作人员指引。");
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
        guideInProgress = false;
      }
    }).catch(function (error) {
      showToast(error.message, true);
    });
  });
  document.getElementById("reset-button").addEventListener("click", function () {
    robotCommand("reset").then(function (result) {
      if (result.accepted) {
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
