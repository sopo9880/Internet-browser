// Bundled first-run welcome helper. Never installs AdBlock automatically.
// The extension is installed as a test-only Titanium external CRX.
chrome.runtime.onInstalled.addListener(async (details) => {
  if (details.reason !== 'install') return;
  const key = 'welcomeShown';
  const stored = await chrome.storage.local.get(key);
  if (stored[key] === true) return;
  await chrome.storage.local.set({[key]: true});
  await chrome.tabs.create({url: chrome.runtime.getURL('welcome.html')});
});
