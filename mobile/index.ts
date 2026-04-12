// Hermes doesn't provide DOMException — polyfill before any packages load.
// Needed by @react-native-async-storage/async-storage 3.x and fetch-based libs
// that call AbortController.abort() or signal DOMException.
if (typeof global.DOMException === "undefined") {
  // @ts-ignore
  global.DOMException = class DOMException extends Error {
    constructor(message = "", name = "Error") {
      super(message);
      this.name = name;
    }
  };
}

import "expo-router/entry";
