const PREFIX = '[DigitalAvatar]';

export function log(...args) {
  console.log(PREFIX, ...args);
}

export function warn(...args) {
  console.warn(PREFIX, ...args);
}

export function error(...args) {
  console.error(PREFIX, ...args);
}
