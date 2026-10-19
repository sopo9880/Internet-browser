document.getElementById('welcome-complete').addEventListener('click', async () => {
  // Stay in THIS Chromium browser. Do not dispatch an Android Intent.
  const tab = await chrome.tabs.getCurrent();
  if (tab && tab.id !== undefined) {
    await chrome.tabs.update(tab.id, {url: 'chrome://newtab/'});
  } else {
    window.close();
  }
});
