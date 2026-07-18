"use strict";

const path = require("path");

const LOOPBACK_HOSTS = new Set(["localhost", "127.0.0.1", "[::1]", "::1"]);
const STREAMLIT_PORT = "8501";

function isAllowedCameraOrigin(rawUrl) {
  if (!rawUrl) {
    return false;
  }
  try {
    const url = new URL(rawUrl);
    return (
      ["http:", "https:"].includes(url.protocol) &&
      LOOPBACK_HOSTS.has(url.hostname.toLowerCase()) &&
      url.port === STREAMLIT_PORT
    );
  } catch {
    return false;
  }
}

function permissionOrigin(webContents, requestingOrigin, details = {}) {
  return (
    details.securityOrigin ||
    details.requestingUrl ||
    requestingOrigin ||
    details.embeddingOrigin ||
    webContents?.getURL?.() ||
    ""
  );
}

function installCameraPermissionHandlers(electronSession) {
  if (
    !electronSession ||
    typeof electronSession.setPermissionCheckHandler !== "function" ||
    typeof electronSession.setPermissionRequestHandler !== "function"
  ) {
    throw new TypeError("A valid Electron session is required.");
  }

  electronSession.setPermissionCheckHandler(
    (webContents, permission, requestingOrigin, details = {}) => {
      if (permission !== "media") {
        return false;
      }
      const mediaType = details.mediaType || "unknown";
      if (!new Set(["video", "unknown"]).has(mediaType)) {
        return false;
      }
      return isAllowedCameraOrigin(
        permissionOrigin(webContents, requestingOrigin, details),
      );
    },
  );

  electronSession.setPermissionRequestHandler(
    (webContents, permission, callback, details = {}) => {
      const mediaTypes = Array.isArray(details.mediaTypes)
        ? details.mediaTypes
        : [];
      const requestsVideo =
        mediaTypes.length === 0 || mediaTypes.includes("video");
      const allowed =
        permission === "media" &&
        requestsVideo &&
        isAllowedCameraOrigin(permissionOrigin(webContents, "", details));
      callback(allowed);
    },
  );
}

function resolveWritableConfigEnv(environment, userDataPath) {
  const resolved = { ...environment };
  const chromaPath = String(resolved.CHROMA_PERSIST_DIR || "").trim();
  if (chromaPath && !path.isAbsolute(chromaPath)) {
    resolved.CHROMA_PERSIST_DIR = path.resolve(userDataPath, chromaPath);
  }
  return resolved;
}

module.exports = {
  installCameraPermissionHandlers,
  isAllowedCameraOrigin,
  permissionOrigin,
  resolveWritableConfigEnv,
};
