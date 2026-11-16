const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const script = fs.readFileSync(path.resolve(__dirname, '../../native/chromium/android/resources/youtube_background.js'), 'utf8');

function page() {
  // Minimal DOM: hidden page whose Document.prototype getters report hidden.
  class Document {}
  for (const [name, value] of [['hidden', true], ['webkitHidden', true], ['visibilityState', 'hidden'], ['webkitVisibilityState', 'hidden']])
    Object.defineProperty(Document.prototype, name, {configurable: true, get: () => value});
  const listeners = [];
  const window = {addEventListener: (type, listener, capture) => listeners.push({type, listener, capture})};
  const context = vm.createContext({Document, window, document: new Document()});
  return {context, listeners};
}

test('YouTube always sees a visible page and never receives visibility changes', () => {
  const {context, listeners} = page();
  vm.runInContext(script, context);
  assert.equal(vm.runInContext('document.hidden', context), false);
  assert.equal(vm.runInContext('document.webkitHidden', context), false);
  assert.equal(vm.runInContext('document.visibilityState', context), 'visible');
  assert.equal(vm.runInContext('document.webkitVisibilityState', context), 'visible');
  assert.deepEqual(listeners.map(({type, capture}) => [type, capture]),
                   [['visibilitychange', true], ['webkitvisibilitychange', true]]);
  let stopped = 0;
  for (const {listener} of listeners) listener({stopImmediatePropagation: () => ++stopped});
  assert.equal(stopped, 2);
});

test('a page that locked the properties does not break the script', () => {
  const {context, listeners} = page();
  vm.runInContext("Object.defineProperty(Document.prototype, 'hidden', {configurable: false, value: true})", context);
  vm.runInContext(script, context);
  assert.equal(vm.runInContext('document.visibilityState', context), 'visible');
  assert.equal(listeners.length, 2);
});
