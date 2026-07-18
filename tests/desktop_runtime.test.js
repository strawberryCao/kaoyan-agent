"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const {
  installCameraPermissionHandlers,
  isAllowedCameraOrigin,
  resolveWritableConfigEnv,
} = require("../desktop_runtime");

test("camera access is limited to the local Streamlit origin", () => {
  assert.equal(isAllowedCameraOrigin("http://localhost:8501"), true);
  assert.equal(isAllowedCameraOrigin("http://127.0.0.1:8501/focus"), true);
  assert.equal(isAllowedCameraOrigin("http://[::1]:8501"), true);
  assert.equal(isAllowedCameraOrigin("http://localhost:8502"), false);
  assert.equal(isAllowedCameraOrigin("https://example.com:8501"), false);
  assert.equal(isAllowedCameraOrigin("not-a-url"), false);
});

test("Electron permission handlers allow local video and reject other access", () => {
  const handlers = {};
  const electronSession = {
    setPermissionCheckHandler(handler) {
      handlers.check = handler;
    },
    setPermissionRequestHandler(handler) {
      handlers.request = handler;
    },
  };
  const webContents = { getURL: () => "http://localhost:8501" };

  installCameraPermissionHandlers(electronSession);

  assert.equal(
    handlers.check(webContents, "media", "http://localhost:8501", {
      mediaType: "video",
    }),
    true,
  );
  assert.equal(
    handlers.check(webContents, "media", "http://localhost:8501", {
      mediaType: "audio",
    }),
    false,
  );
  assert.equal(
    handlers.check(webContents, "media", "http://192.168.1.20:8501", {
      mediaType: "video",
    }),
    false,
  );

  let granted = null;
  handlers.request(webContents, "media", (value) => {
    granted = value;
  }, {
    requestingUrl: "http://localhost:8501/component/streamlit_webrtc",
    mediaTypes: ["video"],
  });
  assert.equal(granted, true);

  handlers.request(webContents, "media", (value) => {
    granted = value;
  }, {
    requestingUrl: "http://localhost:8501",
    mediaTypes: ["audio"],
  });
  assert.equal(granted, false);
});

test("relative writable paths are anchored in Electron userData", () => {
  const userDataPath = path.resolve("fake-electron-user-data");
  const result = resolveWritableConfigEnv(
    {
      CHROMA_PERSIST_DIR: "data/chroma",
      YOLO_PERSON_WEIGHTS_PATH: "models/person_presence/yolov8n.pt",
    },
    userDataPath,
  );

  assert.equal(
    result.CHROMA_PERSIST_DIR,
    path.join(userDataPath, "data", "chroma"),
  );
  assert.equal(
    result.YOLO_PERSON_WEIGHTS_PATH,
    "models/person_presence/yolov8n.pt",
  );
});
