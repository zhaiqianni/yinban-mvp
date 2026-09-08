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
    toast: document.getElementById("toast")
  };

  var activeRobotRouteId = null;
  var currentRoute = [];
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

  function renderRoute(route, destination, physicalAvailable, destinationNames) {
    currentRoute = route || [];
    elements.routeSteps.innerHTML = "";
    if (!currentRoute.length) {
      var empty = document.createElement("li");
      empty.className = "empty-step";
      empty.textContent = "当前问题不需要规划路线。";
      elements.routeSteps.appendChild(empty);
      elements.routeTitle.textContent = "就医流程问询";
      elements.routeNote.textContent = "您可以继续提问或选择一个目的地。";
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
    elements.routeNote.textContent = physicalAvailable
      ? "此路线支持当前实体小车导引。"
      : "此路线当前仅作屏幕展示，实体小车尚未实现。";
  }

  function markRouteProgress(state) {
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
    } else if (state === "MOVING" || state === "BLOCKED") {
      steps[0].classList.add("active");
      if (steps.length > 1) {
        steps[1].classList.add("active");
      }
    } else {
      steps[0].classList.add("active");
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
      activeRobotRouteId = result.robot_route_id;
      elements.startButton.disabled = !result.physical_available;
      var destinationName = result.route.length
        ? result.route[result.route.length - 1]
        : "";
      renderRoute(
        result.route,
        destinationName,
        result.physical_available,
        result.destination_names
      );
      speak(result.answer);
      if (result.intent === "help") {
        showToast("已触发本地求助提醒，请联系现场工作人员。", true);
      }
      if (autoStart && result.physical_available) {
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
    if (!activeRobotRouteId) {
      showToast("请先选择支持实体导引的心内科路线。", true);
      return;
    }
    try {
      await robotCommand("start", {routeId: activeRobotRouteId});
    } catch (error) {
      showToast(error.message, true);
    }
  }

  async function pollRobotStatus() {
    try {
      var status = await api("/api/robot/status");
      elements.connectionDot.classList.toggle("connected", status.connected);
      elements.modeLabel.textContent =
        status.mode === "hardware" ? "真实硬件模式" : "模拟演示模式";
      elements.robotState.textContent = stateLabels[status.state] || status.state;
      var details = [];
      if (status.route_id) {
        details.push("路线：" + status.route_id);
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
        activeRobotRouteId = restoredRoute.robot_route_id;
        elements.startButton.disabled = !restoredRoute.physical_available;
        renderRoute(
          restoredRoute.labels,
          restoredRoute.destination_name,
          restoredRoute.physical_available,
          [restoredRoute.destination_name]
        );
      }
      markRouteProgress(status.state);
      if (status.state === "ARRIVED" && lastRobotState !== "ARRIVED") {
        speak("已经到达心内科，请留意门牌和现场工作人员指引。");
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
    robotCommand("resume").catch(function (error) {
      showToast(error.message, true);
    });
  });
  document.getElementById("stop-button").addEventListener("click", function () {
    robotCommand("stop").catch(function (error) {
      showToast(error.message, true);
    });
  });
  document.getElementById("reset-button").addEventListener("click", function () {
    robotCommand("reset").then(function () {
      activeRobotRouteId = null;
      elements.startButton.disabled = true;
    }).catch(function (error) {
      showToast(error.message, true);
    });
  });

  setupSpeechRecognition();
  pollRobotStatus();
  window.setInterval(pollRobotStatus, 500);
})();
