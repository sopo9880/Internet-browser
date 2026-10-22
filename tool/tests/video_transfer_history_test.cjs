const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const app = fs.readFileSync(path.join(__dirname, '../../native/chromium/windows/resources/app.js'), 'utf8');
const source = app.slice(app.indexOf('const transferHistoryKey ='), app.indexOf('async function clearTransferHistory'));
function history(storage = new Map()) {
  const localStorage = {getItem: key => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value)};
  return {context: vm.createContext({localStorage}), storage, source};
}
function setup(value) {vm.runInContext(source, value.context); return value;}
function evaluate(value, script) {return JSON.parse(JSON.stringify(vm.runInContext(script, value.context)));}
test('only ended progress rows are dismissed, independently or in bulk; hiding survives hub restart', () => {
  const first = setup(history());
  const items = [{guid:'active',state:0},{guid:'done',state:1},{guid:'cancelled',state:2},{guid:'failed',state:3}];
  first.context.items = items;
  evaluate(first, 'dismissTransfers(items, "done"); [...dismissedTransfers()]');
  assert.deepEqual(evaluate(first, '[...dismissedTransfers()]'), ['done']);
  const restarted = setup(history(first.storage)); restarted.context.items = items;
  assert.deepEqual(evaluate(restarted, '[...dismissedTransfers()]'), ['done']);
  assert.deepEqual(evaluate(restarted, 'dismissTransfers(items); [...dismissedTransfers()]'), ['done','cancelled','failed']);
  assert.deepEqual(items, [{guid:'active',state:0},{guid:'done',state:1},{guid:'cancelled',state:2},{guid:'failed',state:3}]);
});
test('malformed stored data is ignored and write errors are not reported as success', () => {
  const state = setup(history(new Map([['video-transfer-dismissed-v1','{broken']])));
  assert.deepEqual(evaluate(state, '[...dismissedTransfers()]'), []);
  state.context.localStorage.setItem = () => {throw new Error('Storage unavailable');};
  assert.throws(() => vm.runInContext('dismissTransfers([{guid:"done",state:1}])', state.context), /Storage unavailable/);
});
